import logging
from typing import Dict, Optional, Tuple

import ee
import pandas as pd
import math
from sampling import merge_ee_sampling_results, build_variable_extractor

ELEVATION_COLLECTION_ID = "COPERNICUS/DEM/GLO30"
ELEVATION_SOURCE_BAND = "DEM"
ELEVATION_BAND = "elevation"
SLOPE_BAND = "slope_percent"
ELEVATION_BANDS = [ELEVATION_BAND, SLOPE_BAND]
DEG_TO_RAD = math.pi / 180.0


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_elevation(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    scale: int = 30,
) -> Tuple[pd.DataFrame, ee.Image]: 
    """
    Extract elevation and slope statistics (mean and standard deviation)
    for buffered points using the COPERNICUS/DEM/GLO30 dataset.
    
    https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30

    For each buffered point, computes:
        - elevation_mean: mean elevation (m) within the buffer
        - elevation_std:  std. dev. of elevation (m)
        - slope_mean:     mean slope (degrees)
        - slope_std:      std. dev. of slope (degrees)

    Args:
        df: DataFrame with coordinates.
        aoi: ee.Geometry defining area of interest for clipping the DEM.
        points_feature_collection: ee.FeatureCollection of buffered points.
        scale: Scale (in meters) to use for reduction.

    Returns:
        (result_df, elev_slope_image):
            result_df: original DataFrame with added elevation/slope columns.
            elev_slope_image: elevation and slope ee.Image used for the computation.
    """
    logger.info("-----------------------------------------------")
    logger.info(f"Starting --Elevation & Slope-- extraction...")
    logger.info(f"Scale: {scale}m")

    logger.info("Loading SRTM elevation dataset...")
    elevation_slope_image = _load_elevation_slope_composite(aoi)

    logger.info("Extracting elevation and slope statistics...")
    compute_elev_stats = build_variable_extractor(elevation_slope_image,
                                                  ELEVATION_BANDS,
                                                  scale)

    fc_stats = points_feature_collection.map(compute_elev_stats)

    logger.info("Fetching results from Earth Engine...")
    results = _fetch_elevation_results(fc_stats)

    logger.info("Merging elevation and slope values into dataframe...")
    result_df = _merge_elevation_results(df, results)

    _log_extraction_summary(result_df)
    return result_df, elevation_slope_image

def _load_elevation_slope_composite(aoi: ee.Geometry) -> ee.Image:
    """
    Load COPERNICUS GLO30 DEM and derive slope, clipped to AOI.

    Returns an ee.Image with bands:
        - 'elevation'      (meters above sea level)
        - 'slope_percent'  (percent rise/run)
    """
    dem_ic = (
        ee.ImageCollection(ELEVATION_COLLECTION_ID)
        .filterBounds(aoi)
        .select(ELEVATION_SOURCE_BAND)
    )

    elevation = dem_ic.median().rename(ELEVATION_BAND).toFloat()

    # I haven't fully understood why a map is necessary to compute slope here,
    # but it doesnt work correctly otherwise.
    slope_ic = dem_ic.map(_per_tile_slope_percent)
    slope = slope_ic.median().toFloat()

    return elevation.addBands(slope).clip(aoi)

def _per_tile_slope_percent(img: ee.Image) -> ee.Image:
    """
    Compute slope in percent for a single DEM tile.
    Input: DEM heights in meters.
    Output band name: 'slope_percent'.
    """
    slope_deg = ee.Terrain.slope(img)           
    slope_pct = _slope_deg_to_percent(slope_deg)
    return slope_pct.rename(SLOPE_BAND)

def _slope_deg_to_percent(slope_deg: ee.Image) -> ee.Image:
    """Convert slope from degrees to percent (rise/run * 100)."""
    return (
        slope_deg
        .multiply(DEG_TO_RAD)
        .tan()
        .multiply(100.0)
   )


def _fetch_elevation_results(
    fc_stats: ee.FeatureCollection,
) -> Optional[Dict]:
    """Fetch sampled values from Earth Engine."""
    try:
        return fc_stats.getInfo()
    except Exception as exc:  # pragma: no cover - Earth Engine failure path
        logger.error(f"Failed to fetch elevation stats from Earth Engine: {exc}")
        raise


def _merge_elevation_results(
    df: pd.DataFrame,
    results: Optional[Dict],
) -> pd.DataFrame:
    """
    Merge elevation/slope sampling output into a dataframe copy.
    Expects EE properties:
        - elevation_mean
        - elevation_stdDev
        - slope_mean
        - slope_stdDev
    """
    column_map = {
        "elevation_mean": f"{ELEVATION_BAND}_mean",
        "elevation_std": f"{ELEVATION_BAND}_stdDev",
        "slope_percent_mean": f"{SLOPE_BAND}_mean",
        "slope_percent_std": f"{SLOPE_BAND}_stdDev",
    }
    
    return merge_ee_sampling_results(df, results, column_map)


def _log_extraction_summary(result_df: pd.DataFrame) -> None:
    """Log summary statistics for the extracted elevation and slope values."""
    total_points = len(result_df)
    valid_elevation = result_df["elevation_mean"].notna().sum()
    valid_slope = result_df["slope_percent_mean"].notna().sum()

    logger.info(
        f"Successfully processed {valid_elevation}/{total_points} points with elevation data"
    )
    logger.info(
        f"Successfully processed {valid_slope}/{total_points} points with slope data"
    )

    if valid_elevation > 0:
        elev_values = result_df["elevation_mean"].dropna()
        logger.info(
            f"Elevation mean: {elev_values.mean():.2f} ± {elev_values.std():.2f} m "
            f"(range {elev_values.min():.2f}-{elev_values.max():.2f} m)"
        )

    if valid_slope > 0:
        slope_values = result_df["slope_percent_mean"].dropna()
        logger.info(
            "Slope mean: "
            f"{slope_values.mean():.2f} ± {slope_values.std():.2f} deg "
            f"(range {slope_values.min():.2f}-{slope_values.max():.2f} deg)"
        )
