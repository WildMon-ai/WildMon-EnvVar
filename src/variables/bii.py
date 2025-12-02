import logging
from typing import Dict, Optional, Tuple

import ee
import pandas as pd

from sampling import build_variable_extractor, merge_ee_sampling_results

BII_COLLECTION_ID = "projects/ebx-data/assets/earthblox/IO/BIOINTACT"
BII_SOURCE_BAND = "BioIntactness"
BII_BAND = BII_SOURCE_BAND.lower()
DEFAULT_SCALE = 100
AVAILABLE_YEARS = [2017, 2018, 2019, 2020]
LATEST_YEAR = AVAILABLE_YEARS[-1]

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_bii(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    year: int = LATEST_YEAR,
    scale: int = DEFAULT_SCALE,
) -> Tuple[pd.DataFrame, ee.Image]:
    """
    Extract Biodiversity Intactness Index (BII) statistics for buffered sampling units.

    Args:
        df: DataFrame aligned with the buffered feature collection.
        aoi: ee.Geometry defining the area of interest to clip the BII image.
        points_feature_collection: ee.FeatureCollection of buffered sampling units.
        year: Target year (2017-2020). Falls back to the latest available if out of range.
        scale: Sampling scale in meters (dataset native resolution is 100 m).

    Returns:
        (result_df, bii_image):
            result_df: DataFrame with biointactness_mean/biointactness_std columns.
            bii_image: ee.Image used for the extraction.
    """
    logger.info("-----------------------------------------------")
    logger.info(f"Starting --Biodiversity Intactness Index-- extraction...")
    logger.info(f"Requested year: {year}")
    logger.info(f"Scale: {scale}m")

    logger.info("Loading BII image...")
    bii_image = _load_bii_image(aoi, year)

    logger.info("Extracting BII statistics...")
    compute_bii_stats = build_variable_extractor(bii_image, [BII_BAND], scale)
    fc_stats = points_feature_collection.map(compute_bii_stats)

    logger.info("Fetching BII results from Earth Engine...")
    results = _fetch_bii_results(fc_stats)

    logger.info("Merging BII results into dataframe...")
    result_df = _merge_bii_results(df, results)

    _log_extraction_summary(result_df)
    return result_df, bii_image


def _load_bii_image(aoi: ee.Geometry, requested_year: int) -> ee.Image:
    """Load the BII image for the requested year, falling back to the latest available."""
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
        ee.ImageCollection(BII_COLLECTION_ID)
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .select(BII_SOURCE_BAND)
    )

    size = collection.size()
    if size.getInfo() == 0:
        raise ValueError(
            "No BII imagery found for the specified AOI and date range."
        )

    image = collection.median()
    return ee.Image(image).rename(BII_BAND).clip(aoi)


def _fetch_bii_results(
    fc_stats: ee.FeatureCollection,
) -> Optional[Dict]:
    """Fetch sampled BII values from Earth Engine."""
    try:
        return fc_stats.getInfo()
    except Exception as exc:  # pragma: no cover - EE failure path
        logger.error(f"Failed to fetch BII statistics from Earth Engine: {exc}")
        raise


def _merge_bii_results(
    df: pd.DataFrame,
    results: Optional[Dict],
) -> pd.DataFrame:
    """Merge BII sampling output into a dataframe copy."""
    column_map = {
        "biointactness_mean": f"{BII_BAND}_mean",
        "biointactness_std": f"{BII_BAND}_stdDev",
    }
    return merge_ee_sampling_results(df, results, column_map)


def _log_extraction_summary(result_df: pd.DataFrame) -> None:
    """Log summary statistics for the extracted BII values."""
    total_points = len(result_df)
    valid_mask = result_df["biointactness_mean"].notna()
    valid_points = valid_mask.sum()

    logger.info(
        f"Successfully processed {valid_points}/{total_points} points with BII data"
    )

    if valid_points == 0:
        return

    values = result_df.loc[valid_mask, "biointactness_mean"]
    logger.info(
        "BII mean: "
        f"{values.mean():.2f} ± {values.std():.2f} "
        f"(range {values.min():.2f}-{values.max():.2f})"
    )
