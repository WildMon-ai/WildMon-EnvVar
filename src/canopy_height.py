import logging
from typing import Dict, Optional, Tuple

import ee
import pandas as pd

from src.sampling import merge_ee_sampling_results, build_variable_extractor

CANOPY_DATASET_ID = "users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1"
CANOPY_SOURCE_BAND = "b1"
CANOPY_BAND = "canopy_height"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_canopy_height(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    scale: int = 10,
) -> Tuple[pd.DataFrame, ee.Image]:
    """
    Extract canopy height statistics (mean and standard deviation) for buffered points.

    Args:
        df: DataFrame with coordinates.
        aoi: ee.Geometry defining the area of interest used to crop the canopy height image.
        points_feature_collection: ee.FeatureCollection of buffered sampling units.
        scale: Scale (in meters) for sampling.

    Returns:
        (result_df, canopy_height_image):
            result_df: Original DataFrame with canopy_height_mean/std columns.
            canopy_height_image: ee.Image used for sampling.
    """
    logger.info(f"Processing {len(df)} points...")
    logger.info(f"Scale: {scale}m")

    logger.info("Loading ETH Global Canopy Height dataset...")
    canopy_height_image = _load_canopy_height_image(aoi)

    logger.info("Extracting canopy height statistics...")
    compute_canopy_stats = build_variable_extractor(
        canopy_height_image, [CANOPY_BAND], scale
    )
    fc_stats = points_feature_collection.map(compute_canopy_stats)

    logger.info("Fetching results from Earth Engine...")
    results = _fetch_canopy_height_results(fc_stats)

    logger.info("Merging canopy height values into dataframe...")
    result_df = _merge_canopy_height_results(df, results)

    _log_extraction_summary(result_df)
    return result_df, canopy_height_image


def _load_canopy_height_image(aoi: ee.Geometry) -> ee.Image:
    """
    Load the Canopy Height dataset, selecting the band of interest and clipping to the given AOIs.

    Args:
        aoi: ee.Geometry defining the area of interest to crop the dataset and reduce processing.
    Returns:
        ee.Image containing the canopy height data for the given AOIs.
    """
    return (
        ee.Image(CANOPY_DATASET_ID)
        .select(CANOPY_SOURCE_BAND)
        .rename(CANOPY_BAND)
        .clip(aoi)
    )


def _fetch_canopy_height_results(
    fc_stats: ee.FeatureCollection,
) -> Optional[Dict]:
    """Fetch canopy sampling results from Earth Engine."""
    try:
        return fc_stats.getInfo()
    except Exception as exc:  # pragma: no cover - Earth Engine failure path
        logger.error(f"Failed to fetch canopy height stats from Earth Engine: {exc}")
        raise


def _merge_canopy_height_results(
    df: pd.DataFrame,
    results: Optional[Dict],
) -> pd.DataFrame:
    """Merge canopy height sampling output into a dataframe copy."""
    column_map = {
        "canopy_height_mean": f"{CANOPY_BAND}_mean",
        "canopy_height_std": f"{CANOPY_BAND}_stdDev",
    }
    return merge_ee_sampling_results(df, results, column_map)


def _log_extraction_summary(result_df: pd.DataFrame) -> None:
    """Log summary statistics for the extracted canopy height values."""
    total_points = len(result_df)
    valid_points = result_df["canopy_height_mean"].notna().sum()

    logger.info(
        f"Successfully processed {valid_points}/{total_points} points with canopy data"
    )

    if valid_points == 0:
        return

    canopy_values = result_df["canopy_height_mean"].dropna()
    logger.info(
        "Canopy height mean: "
        f"{canopy_values.mean():.2f} ± {canopy_values.std():.2f} m "
        f"(range {canopy_values.min():.2f}-{canopy_values.max():.2f} m)"
    )
