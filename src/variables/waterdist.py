import logging
from typing import Dict, Optional, Tuple

import ee
import pandas as pd

from sampling import merge_ee_sampling_results

GLCF_WATER_COLLECTION_ID = "GLCF/GLS_WATER"
OSM_WATER_DATASET_ID = "projects/sat-io/open-datasets/OSM_waterLayer"
DISTANCE_BAND_NAME = "distance_to_water_m"
GLCF_CLASS_BAND = "glcf_water_class"
OSM_CLASS_BAND = "osm_water_class"
COMBINED_WATER_BAND = "water_mask"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)



def extract_distance_to_water(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    scale: int = 30,
    max_search_distance: int = 5_000,
) -> Tuple[pd.DataFrame, ee.Image]:
    """
    Compute the distance (in meters) from each sampling point to the nearest water body
    by combining the GLCF water mask with the OSM water layer and using fastDistanceTransform.
    The distance search has a maximum search distance to limit computation. If no water is found
    within this distance, the distance value is set to (max_search_distance + 1).
    Also because the image is based in meters, the image is projected into a metric CRS (Web Mercator, EPSG:3857).
    
    """

    logger.info("-----------------------------------------------")
    logger.info(f"Starting --Distance to Water-- extraction...")
    logger.info(f"Sampling scale: {scale}m")
    logger.info(f"Max search distance: {max_search_distance}m, pixels beyond this will be set to {max_search_distance + 1}m")

    logger.info("Loading water datasets at native resolution...")
    glcf_water = _load_water_layer(aoi=aoi,
                                   image_collection_id=GLCF_WATER_COLLECTION_ID)
    
    osm_water = _load_water_layer(aoi=aoi,
                                  image_collection_id=OSM_WATER_DATASET_ID,
                                  projection_object=glcf_water.projection())

    logger.info("Combining water layers...")
    combined_mask = _prepare_water_layers(glcf_water, osm_water, aoi)

    logger.info("Building distance surface using FDT...")
    distance_image = _build_distance_image_fdt(
        combined_mask,
        aoi,
        max_search_distance_m=max_search_distance,
    )

    logger.info("Sampling distance values at sampling point centroids...")
    compute_distance = _build_distance_extractor(distance_image, scale)
    fc_stats = points_feature_collection.map(compute_distance)

    logger.info("Fetching distance results...")
    results = _fetch_distance_results(fc_stats)

    logger.info("Merging distances into dataframe...")
    result_df = _merge_distance_results(df, results)

    water_and_distance_bands = combined_mask.addBands(distance_image)

    _log_extraction_summary(result_df)
    return result_df, water_and_distance_bands


def _load_water_layer(aoi: ee.Geometry,
                     image_collection_id: str,
                     projection_object: Optional[ee.Projection] = None) -> ee.Image:
        
        """
        Load a water layer image at native resolution or provided projection, filtered by the area of interest (AOI).

        Args:
            aoi: ee.Geometry defining the area of interest.
            image_collection_id: str, ID of the Earth Engine image collection to load.
            projection_object: Optional[ee.Projection], Projection to reproject the loaded image to.

        Returns:
            ee.Image, Water layer image at native or provided resolution,
            filtered by the AOIs and reprojected to the specified projection if provided.
            It seems like after doing mosaic, the resolution changes so we need to reproject again.
        """
        ic = ee.ImageCollection(image_collection_id).filterBounds(aoi)
        
        if projection_object is None:
            projection_object = ic.first().projection()
        return (
            ic.mosaic()
            .reproject(projection_object)
            .clip(aoi)
        )

def _prepare_water_layers(
    glcf_water: ee.Image,
    osm_water: ee.Image,
    aoi: ee.Geometry,
    scale: int = 30,
) -> ee.Image:
    """
    Combine GLCF + OSM binary masks, then convert into metric CRS suitable for distance FDT.
    """

    # GLCF: 2 = Water
    glcf_mask = glcf_water.eq(2)

    # OSM: classes 1..5 = Water
    osm_mask = osm_water.gt(0).And(osm_water.lt(6))

    combined = glcf_mask.Or(osm_mask).rename(COMBINED_WATER_BAND)

    # Project into metric CRS (Web Mercator) once for distance calculation
    combined_metric = (
        combined
        .unmask(0)
        .reproject(crs="EPSG:3857", scale=scale)
        .selfMask()
        .clip(aoi)
    )

    return combined_metric


def _build_distance_image_fdt(
    water_mask: ee.Image,
    aoi: ee.Geometry,
    max_search_distance_m: int = 5000,
) -> ee.Image:
    """
    Compute distance-to-water (meters) using fastDistanceTransform.
    
    Args:
        water_mask: ee.Image, Binary water mask (1 = water, 0 = non-water)
        aoi: ee.Geometry, Area of interest for clipping the output distance image
        max_search_distance_m: int, Maximum search distance to water in meters
    Returns:
        ee.Image, Distance-to-water image in meters.

    Pixels with no water within the search distance are assigned a distance of (max_search_distance_m + 1)
    """

    proj = water_mask.projection()
    pixel_size_m = proj.nominalScale()

    water = (
        water_mask
        .gt(0)
        .unmask(0)
        .toByte()
        .reproject(proj)
        .clip(aoi)
    )

    max_m = ee.Number(max_search_distance_m)

    neighborhood_px = (
        max_m
        .divide(pixel_size_m)
        .ceil()
    )

    sqdist_px2 = water.fastDistanceTransform(
        neighborhood=neighborhood_px,
        units="pixels",
        metric="squared_euclidean",
    )

    dist_px = sqdist_px2.sqrt()

    saturated = dist_px.gt(neighborhood_px)

    dist_m = (
        dist_px
        .min(neighborhood_px)            # clamp
        .multiply(pixel_size_m)
        .rename(DISTANCE_BAND_NAME)
        .reproject(proj)
        .clip(aoi)
    )

    return dist_m.where(saturated,max_m.add(1)) # fill distances beyond max with max + 1


def _build_distance_extractor(
    distance_image: ee.Image,
    scale: int,
):
    """Return a reducer function that samples the distance image at point centroids."""

    def extract(feature: ee.Feature) -> ee.Element:
        centroid = feature.geometry().centroid()
        stats = distance_image.reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=centroid,
            scale=scale,
            maxPixels=1_000_000_000,
            bestEffort=True
        )
        return feature.set(stats)

    return extract


def _fetch_distance_results(
    fc_stats: ee.FeatureCollection,
) -> Optional[Dict]:
    """Fetch sampled values from Earth Engine."""
    try:
        return fc_stats.getInfo()
    except Exception as exc:  # pragma: no cover - EE failure path
        logger.error(f"Failed to fetch distance-to-water statistics: {exc}")
        raise


def _merge_distance_results(
    df: pd.DataFrame,
    results: Optional[Dict],
) -> pd.DataFrame:
    """Merge distance sampling output into a dataframe copy."""
    column_map = {
        DISTANCE_BAND_NAME: DISTANCE_BAND_NAME,
    }
    merged = merge_ee_sampling_results(df, results, column_map)
    return merged


def _log_extraction_summary(result_df: pd.DataFrame) -> None:
    """Log summary statistics for the extracted distance-to-water values."""
    total_points = len(result_df)
    column = DISTANCE_BAND_NAME
    if column not in result_df.columns:
        logger.warning("distance_to_water column not found; skipping summary.")
        return

    valid_mask = result_df[column].notna()
    valid_points = valid_mask.sum()

    logger.info(
        f"Successfully processed {valid_points}/{total_points} points with distance-to-water data"
    )

    if valid_points == 0:
        return

    values = result_df.loc[valid_mask, column]
    logger.info(
        "Distance to water: "
        f"mean {values.mean():.1f} m "
        f"(min {values.min():.1f} m, max {values.max():.1f} m)"
    )

