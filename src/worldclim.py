import logging
from typing import Dict, List, Optional, Tuple

import ee
import pandas as pd

from src.sampling import merge_ee_sampling_results, build_variable_extractor

DATASET_ID = "WORLDCLIM/V1/BIO"
SCALE = 1000

SCALE_FACTORS: Dict[str, float] = {
    "bio01": 0.1,  # Annual Mean Temperature (°C)
    "bio02": 0.1,  # Mean Diurnal Range (°C)
    "bio03": 1.0,  # Isothermality (%)
    "bio04": 0.1,  # Temperature Seasonality (°C)
    "bio05": 0.1,  # Max Temperature of Warmest Month (°C)
    "bio06": 0.1,  # Min Temperature of Coldest Month (°C)
    "bio07": 0.1,  # Temperature Annual Range (°C)
    "bio08": 0.1,  # Mean Temperature of Wettest Quarter (°C)
    "bio09": 0.1,  # Mean Temperature of Driest Quarter (°C)
    "bio10": 0.1,  # Mean Temperature of Warmest Quarter (°C)
    "bio11": 0.1,  # Mean Temperature of Coldest Quarter (°C)
    "bio12": 1.0,  # Annual Precipitation (mm)
    "bio13": 1.0,  # Precipitation of Wettest Month (mm)
    "bio14": 1.0,  # Precipitation of Driest Month (mm)
    "bio15": 1.0,  # Precipitation Seasonality (CV)
    "bio16": 1.0,  # Precipitation of Wettest Quarter (mm)
    "bio17": 1.0,  # Precipitation of Driest Quarter (mm)
    "bio18": 1.0,  # Precipitation of Warmest Quarter (mm)
    "bio19": 1.0,  # Precipitation of Coldest Quarter (mm)
}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_worldclim(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    variables: Optional[List[str]] = None,
    scale: int = SCALE,
) -> Tuple[pd.DataFrame, ee.Image]:
    """
    Extract WorldClim bioclimatic variables for buffered sampling units.

    Args:
        df: DataFrame with coordinates corresponding to the buffered features.
        aoi: ee.Geometry defining the area of interest for clipping the WorldClim image.
        points_feature_collection: ee.FeatureCollection of buffered sampling units.
        variables: List of WorldClim bands to extract (defaults to all 19).
        scale: Scale in meters for the sampling reducer.

    Returns:
        (result_df, worldclim_image):
            result_df: DataFrame with {variable}_mean/std columns.
            worldclim_image: ee.Image used for extraction.
    """
    selected_variables = _resolve_variables(variables)

    logger.info(f"Processing {len(df)} points...")
    logger.info(f"Variables: {', '.join(selected_variables)}")
    logger.info(f"Scale: {scale}m")

    logger.info("Loading WorldClim image for study area...")
    worldclim_image = _load_worldclim_image(aoi, selected_variables)

    logger.info("Extracting bioclimatic statistics...")
    compute_bioclim_stats = build_variable_extractor(worldclim_image,
                                                     selected_variables,
                                                     scale)
    
    fc_stats = points_feature_collection.map(compute_bioclim_stats)

    logger.info("Fetching results from Earth Engine...")
    results = _fetch_worldclim_results(fc_stats)

    logger.info("Merging WorldClim results into dataframe...")
    result_df = _merge_worldclim_results(df, results, selected_variables)

    _log_extraction_summary(result_df, selected_variables)
    return result_df, worldclim_image


def _resolve_variables(variables: Optional[List[str]]) -> List[str]:
    """Return a validated list of WorldClim variables to extract."""
    selected = list(SCALE_FACTORS.keys()) if variables is None else list(variables)
    if not selected:
        raise ValueError("At least one WorldClim variable must be specified.")

    invalid = [var for var in selected if var not in SCALE_FACTORS]
    if invalid:
        raise ValueError(
            f"Invalid variables: {invalid}. Valid options: {list(SCALE_FACTORS.keys())}"
        )
    return selected


def _load_worldclim_image(aoi: ee.Geometry, variables: List[str]) -> ee.Image:
    """Load the WorldClim image, scale the bands, and clip it to the AOI."""
    base_image = ee.Image(DATASET_ID)
    scaled_bands = [
        base_image.select(var).multiply(SCALE_FACTORS[var]).rename(var)
        for var in variables
    ]
    return ee.Image.cat(scaled_bands).clip(aoi)

def _fetch_worldclim_results(
    fc_stats: ee.FeatureCollection,
) -> Optional[Dict]:
    """Fetch WorldClim sampling results from Earth Engine."""
    try:
        return fc_stats.getInfo()
    except Exception as exc:  # pragma: no cover - Earth Engine failure path
        logger.error(f"Failed to fetch WorldClim statistics from Earth Engine: {exc}")
        raise


def _merge_worldclim_results(
    df: pd.DataFrame,
    results: Optional[Dict],
    variables: List[str],
) -> pd.DataFrame:
    """Merge WorldClim sampling output into a dataframe copy."""
    column_map: Dict[str, str] = {}
    for var in variables:
        column_map[f"{var}_mean"] = f"{var}_mean"
        column_map[f"{var}_stdDev"] = f"{var}_stdDev"
    return merge_ee_sampling_results(df, results, column_map)


def _log_extraction_summary(
    result_df: pd.DataFrame,
    variables: List[str],
) -> None:
    """Log summary statistics for the extracted WorldClim values."""
    total_points = len(result_df)
    reference_col = f"{variables[0]}_mean"
    valid_points = result_df[reference_col].notna().sum()

    logger.info(
        f"Successfully processed {valid_points}/{total_points} points with WorldClim data"
    )

    if valid_points == 0:
        return

    if "bio01_mean" in result_df.columns and "bio01" in variables:
        temps = result_df["bio01_mean"].dropna()
        if not temps.empty:
            logger.info(
                "Annual Mean Temperature (bio01): "
                f"{temps.min():.1f}°C to {temps.max():.1f}°C "
                f"(mean {temps.mean():.1f}°C)"
            )

    if "bio12_mean" in result_df.columns and "bio12" in variables:
        precip = result_df["bio12_mean"].dropna()
        if not precip.empty:
            logger.info(
                "Annual Precipitation (bio12): "
                f"{precip.min():.0f}mm to {precip.max():.0f}mm "
                f"(mean {precip.mean():.0f}mm)"
            )
