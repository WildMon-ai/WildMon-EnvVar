import logging
from typing import Callable, Dict, Optional, Tuple

import ee
import numpy as np
import pandas as pd
from src.sampling import merge_ee_sampling_results

ELEVATION_COLLECTION_ID = "COPERNICUS/DEM/GLO30"

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
    logger.info(f"Processing {len(df)} points...")
    logger.info(f"Scale: {scale}m")

    logger.info("Loading SRTM elevation dataset...")
    elevation_slope_image = _load_elevation_slope_composite(aoi)

    logger.info("Extracting elevation and slope statistics...")
    compute_elev_stats = _build_elevation_extractor(elevation_slope_image, scale)
    fc_stats = points_feature_collection.map(compute_elev_stats)

    logger.info("Fetching results from Earth Engine...")
    results = _fetch_elevation_results(fc_stats)

    logger.info("Merging elevation and slope values into dataframe...")
    result_df = _merge_elevation_results(df, results)

    _log_extraction_summary(result_df)
    return result_df, elevation_slope_image

def _load_elevation_slope_composite(aoi: ee.Geometry) -> ee.Image:
    """
    Load COPERNICUS GLO30 DEM and slope, clipped to AOI.
    Returns an image with bands: 'elevation', 'slope'.
    """
    dem_ic = (
        ee.ImageCollection(ELEVATION_COLLECTION_ID)
        .filterBounds(aoi)
        .select("DEM")
    )

    elevation = dem_ic.mosaic().clip(aoi).rename("elevation")

    slope_ic = dem_ic.map(lambda img: ee.Terrain.slope(img).rename("slope"))
    slope = slope_ic.mosaic().clip(aoi)

    return elevation.addBands(slope)


def _build_elevation_extractor(
    elev_slope_image: ee.Image, scale: int
) -> Callable[[ee.Feature], ee.Element]:
    """Return a function that samples elevation and slope statistics for a feature."""

    def extract_elevation_stats(feature: ee.Feature) -> ee.Element:
        stats = elev_slope_image.reduceRegion(
            reducer=ee.Reducer.mean().combine(
                reducer2=ee.Reducer.stdDev(), sharedInputs=True
            ),
            geometry=feature.geometry(),
            scale=scale,
            maxPixels=1_000_000_000,
            bestEffort=True,
        )
        return feature.set(stats)

    return extract_elevation_stats


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
        "elevation_mean": "elevation_mean",
        "elevation_std": "elevation_stdDev",
        "slope_mean": "slope_mean",
        "slope_std": "slope_stdDev",
    }
    return merge_ee_sampling_results(df, results, column_map)


def _log_extraction_summary(result_df: pd.DataFrame) -> None:
    """Log summary statistics for the extracted elevation and slope values."""
    total_points = len(result_df)
    valid_elevation = result_df["elevation_mean"].notna().sum()
    valid_slope = result_df["slope_mean"].notna().sum()

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
        slope_values = result_df["slope_mean"].dropna()
        logger.info(
            "Slope mean: "
            f"{slope_values.mean():.2f} ± {slope_values.std():.2f} deg "
            f"(range {slope_values.min():.2f}-{slope_values.max():.2f} deg)"
        )
