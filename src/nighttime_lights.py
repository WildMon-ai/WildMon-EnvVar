import logging
from typing import Dict, Optional, Tuple

import ee
import pandas as pd

from src.sampling import build_variable_extractor, merge_ee_sampling_results

NIGHTTIME_LIGHTS_COLLECTION_ID = "NOAA/VIIRS/DNB/ANNUAL_V22"
NIGHTTIME_LIGHTS_SOURCE_BAND = "average"
NIGHTTIME_LIGHTS_BAND = "nighttime_lights"
DEFAULT_SCALE = 464  # meters (VIIRS annual composite ~463.83m)
AVAILABLE_YEARS = list(range(2012, 2023)) # 2012-2022

LATEST_YEAR = AVAILABLE_YEARS[-1]

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_nighttime_lights(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    year: int = LATEST_YEAR,
    scale: int = DEFAULT_SCALE,
) -> Tuple[pd.DataFrame, ee.Image]:
    """
    Extract nighttime lights statistics (mean/stdDev) for buffered sampling units.
    Available years: 2012-2022.

    Args:
        df: DataFrame aligned with the buffered feature collection.
        aoi: ee.Geometry defining the area of interest to clip the VIIRS image.
        points_feature_collection: ee.FeatureCollection of buffered sampling units.
        year: Target year for the annual VIIRS composite. Available years: 2012-2022.
        scale: Sampling scale in meters (VIIRS annual composite native resolution ~464m).

    Returns:
        (result_df, nightlights_image):
            result_df: DataFrame with nightlights_mean/nightlights_std columns.
            nightlights_image: ee.Image used for the extraction.
    """
    logger.info(f"Processing {len(df)} points for nighttime lights extraction...")
    logger.info(f"Requested year: {year}")
    logger.info(f"Scale: {scale}m")

    logger.info("Loading VIIRS annual nighttime lights image...")
    nightlights_image = _load_nighttime_lights_image(aoi, year)

    logger.info("Extracting nighttime lights statistics...")
    compute_lights_stats = build_variable_extractor(
        nightlights_image, [NIGHTTIME_LIGHTS_BAND], scale
    )
    fc_stats = points_feature_collection.map(compute_lights_stats)

    logger.info("Fetching nighttime lights results from Earth Engine...")
    results = _fetch_nighttime_light_results(fc_stats)

    logger.info("Merging nighttime lights results into dataframe...")
    result_df = _merge_nighttime_light_results(df, results)

    _log_extraction_summary(result_df)
    return result_df, nightlights_image


def _load_nighttime_lights_image(
    aoi: ee.Geometry,
    requested_year: int,
) -> ee.Image:
    """Load the VIIRS annual composite for the requested year, falling back to latest if missing."""
    if requested_year not in AVAILABLE_YEARS:
        logger.warning(
            f"Requested year {requested_year} not available for VIIRS nighttime lights. "
            f"Using most recent year {LATEST_YEAR} instead."
        )
        target_year = LATEST_YEAR
    else:
        target_year = requested_year

    start_date = f"{target_year}-01-01"
    end_date = f"{target_year}-12-31"

    collection = (
        ee.ImageCollection(NIGHTTIME_LIGHTS_COLLECTION_ID)
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .select(NIGHTTIME_LIGHTS_SOURCE_BAND)
    )

    size = collection.size()
    if size.getInfo() == 0:
        raise ValueError(
            "No VIIRS nighttime lights imagery found for the specified AOI and year."
        )

    image = collection.sort("system:time_start", False).first()
    return ee.Image(image).rename(NIGHTTIME_LIGHTS_BAND).clip(aoi)


def _fetch_nighttime_light_results(
    fc_stats: ee.FeatureCollection,
) -> Optional[Dict]:
    """Fetch sampled nighttime lights values from Earth Engine."""
    try:
        return fc_stats.getInfo()
    except Exception as exc:  # pragma: no cover - EE failure path
        logger.error(f"Failed to fetch nighttime lights statistics: {exc}")
        raise


def _merge_nighttime_light_results(
    df: pd.DataFrame,
    results: Optional[Dict],
) -> pd.DataFrame:
    """Merge nighttime lights sampling output into a dataframe copy."""
    column_map = {
        "nightlights_mean": f"{NIGHTTIME_LIGHTS_BAND}_mean",
        "nightlights_std": f"{NIGHTTIME_LIGHTS_BAND}_stdDev",
    }
    return merge_ee_sampling_results(df, results, column_map)


def _log_extraction_summary(result_df: pd.DataFrame) -> None:
    """Log summary statistics for the extracted nighttime lights values."""
    total_points = len(result_df)
    valid_mask = result_df["nightlights_mean"].notna()
    valid_points = valid_mask.sum()

    logger.info(
        f"Successfully processed {valid_points}/{total_points} points with nighttime lights data"
    )

    if valid_points == 0:
        return

    values = result_df.loc[valid_mask, "nightlights_mean"]
    logger.info(
        "Nighttime lights mean: "
        f"{values.mean():.2f} ± {values.std():.2f} "
        f"(range {values.min():.2f}-{values.max():.2f})"
    )
