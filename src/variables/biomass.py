import logging
from typing import Dict, Optional, Tuple

import ee
import pandas as pd

from sampling import build_variable_extractor, merge_ee_sampling_results

BIOMASS_COLLECTION_ID = "projects/sat-io/open-datasets/ESA/ESA_CCI_AGB"
BIOMASS_SOURCE_BAND = "AGB"
BIOMASS_BAND = BIOMASS_SOURCE_BAND.lower()
DEFAULT_SCALE = 100
AVAILABLE_YEARS = [
    2007,
    2010,
    2015,
    2016,
    2017,
    2018,
    2019,
    2020,
    2021,
    2022,
]
LATEST_YEAR = AVAILABLE_YEARS[-1]

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_biomass(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    year: int = LATEST_YEAR,
    scale: int = DEFAULT_SCALE,
) -> Tuple[pd.DataFrame, ee.Image]:
    """
    Extract above-ground biomass statistics (mean/stdDev) for buffered sampling units.

    Args:
        df: DataFrame aligned with the buffered feature collection.
        aoi: ee.Geometry defining the area of interest to clip the biomass image.
        points_feature_collection: ee.FeatureCollection of buffered sampling units.
        year: Target year for the ESA CCI AGB dataset.
        scale: Sampling scale in meters (dataset native resolution is 100m).

    Returns:
        (result_df, biomass_image):
            result_df: DataFrame with biomass_mean/biomass_std columns.
            biomass_image: ee.Image used for the extraction.
    """
    logger.info("-----------------------------------------------")
    logger.info(f"Starting --Biomass (AGB)-- extraction...")
    logger.info(f"Requested year: {year}")
    logger.info(f"Scale: {scale}m")

    logger.info("Loading ESA CCI AGB image...")
    biomass_image = _load_biomass_image(aoi, year)

    logger.info("Extracting biomass statistics...")
    compute_biomass_stats = build_variable_extractor(
        biomass_image, [BIOMASS_BAND], scale
    )
    fc_stats = points_feature_collection.map(compute_biomass_stats)

    logger.info("Fetching biomass results from Earth Engine...")
    results = _fetch_biomass_results(fc_stats)

    logger.info("Merging biomass results into dataframe...")
    result_df = _merge_biomass_results(df, results)

    _log_extraction_summary(result_df)
    return result_df, biomass_image


def _load_biomass_image(
    aoi: ee.Geometry,
    requested_year: int,
) -> ee.Image:
    """Load the ESA CCI AGB image for the requested year, with fallback to latest."""
    if requested_year not in AVAILABLE_YEARS:
        logger.warning(
            f"Requested year {requested_year} is not available. "
            f"Using most recent year {LATEST_YEAR} instead."
        )
        target_year = LATEST_YEAR
    else:
        target_year = requested_year

    start_date = f"{target_year}-01-01"
    end_date = f"{target_year}-12-31"

    collection = (
        ee.ImageCollection(BIOMASS_COLLECTION_ID)
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .select(BIOMASS_SOURCE_BAND)
    )

    size = collection.size()
    if size.getInfo() == 0:
        raise ValueError(
            "No ESA CCI AGB imagery found for the specified AOI and date range."
        )

    image = collection.sort("system:time_start", False).first()
    return ee.Image(image).rename(BIOMASS_BAND).clip(aoi)


def _fetch_biomass_results(
    fc_stats: ee.FeatureCollection,
) -> Optional[Dict]:
    """Fetch sampled biomass values from Earth Engine."""
    try:
        return fc_stats.getInfo()
    except Exception as exc:  # pragma: no cover - EE failure path
        logger.error(f"Failed to fetch biomass statistics from Earth Engine: {exc}")
        raise


def _merge_biomass_results(
    df: pd.DataFrame,
    results: Optional[Dict],
) -> pd.DataFrame:
    """Merge biomass sampling output into a dataframe copy."""
    column_map = {
        "biomass_mean": f"{BIOMASS_BAND}_mean",
        "biomass_std": f"{BIOMASS_BAND}_stdDev",
    }
    return merge_ee_sampling_results(df, results, column_map)


def _log_extraction_summary(result_df: pd.DataFrame) -> None:
    """Log summary statistics for the extracted biomass values."""
    total_points = len(result_df)
    valid_mask = result_df["biomass_mean"].notna()
    valid_points = valid_mask.sum()

    logger.info(
        f"Successfully processed {valid_points}/{total_points} points with biomass data"
    )

    if valid_points == 0:
        return

    values = result_df.loc[valid_mask, "biomass_mean"]
    logger.info(
        "Biomass mean: "
        f"{values.mean():.2f} ± {values.std():.2f} t/ha "
        f"(range {values.min():.2f}-{values.max():.2f} t/ha)"
    )
