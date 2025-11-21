import logging
from typing import Dict, Optional, Tuple

import ee
import pandas as pd

from src.sampling import merge_ee_sampling_results

WATER_MASK_COLLECTION_ID = "GLCF/GLS_WATER"
DISTANCE_BAND_NAME = "distance_to_water_m"

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
    Compute the distance (in meters) from each sampling point to the nearest water body.

    Args:
        df: DataFrame aligned with the provided feature collection.
        aoi: ee.Geometry describing the area of interest to clip the water dataset.
        points_feature_collection: ee.FeatureCollection containing the sampling points
            (buffered geometries are accepted; sampling uses centroids).
        scale: Sampling scale in meters.
        max_search_distance: Maximum distance (meters) to search for water pixels when
            building the distance transform.

    Returns:
        (result_df, distance_image):
            result_df: DataFrame with a `distance_to_water_m` column appended.
            distance_image: ee.Image containing the distance-to-water surface.
    """
    logger.info(f"Processing {len(df)} points for distance-to-water calculation...")
    logger.info(f"Sampling scale: {scale}m")
    logger.info(f"Max search distance: {max_search_distance}m")

    logger.info("Loading water mask imagery...")
    water_mask = _load_water_mask(aoi)

    logger.info("Building distance-to-water surface...")
    distance_image = _build_distance_image(
        water_mask, aoi, max_search_distance
    )

    logger.info("Sampling distance values at point centroids...")
    compute_distance = _build_distance_extractor(distance_image, scale)
    fc_stats = points_feature_collection.map(compute_distance)

    logger.info("Fetching distance results from Earth Engine...")
    results = _fetch_distance_results(fc_stats)

    logger.info("Merging distance values into dataframe...")
    result_df = _merge_distance_results(df, results)

    _log_extraction_summary(result_df)
    return result_df, distance_image


def _load_water_mask(aoi: ee.Geometry) -> ee.Image:
    """Load the GLCF water mask mosaic covering the AOI."""
    collection = ee.ImageCollection(WATER_MASK_COLLECTION_ID).filterBounds(aoi)
    return collection.mosaic()


def _build_distance_image(
    water_dataset: ee.Image,
    aoi: ee.Geometry,
    max_search_distance: int,
) -> ee.Image:
    """
    Create a distance-to-water image (in meters) from the GLCF water mask.

    The dataset encodes land/water classes; pixels equal to 2 correspond to water.
    """
    water_dataset = water_dataset.clip(aoi)
    water_pixels = water_dataset.eq(2)
    distance = water_pixels.distance(
        ee.Kernel.euclidean(max_search_distance, "meters")
    )
    return distance.rename(DISTANCE_BAND_NAME)


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
            bestEffort=True,
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
        f"median {values.median():.1f} m "
        f"(min {values.min():.1f} m, max {values.max():.1f} m)"
    )
