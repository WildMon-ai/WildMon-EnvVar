import logging
from typing import Dict, Literal, Optional, Tuple

import ee
import pandas as pd

from eii.client import get_layers
from eii.compute.integrity import combine_components
from sampling import build_variable_extractor, merge_ee_sampling_results

# EII asset and configuration
BII_ASSET_PATH = "projects/ebx-data/assets/earthblox/IO/BIOINTACT"
DEFAULT_SCALE = 300
DEFAULT_BII_YEAR_START = 2020
DEFAULT_BII_YEAR_END = 2025

# Standard band names we will enforce
EII_BAND = "eii"
FUNCTIONAL_BAND = "functional_integrity"
STRUCTURAL_BAND = "structural_integrity"
COMPOSITIONAL_BAND = "compositional_integrity"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def extract_eii(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    layers: str = "all",
    aggregation_method: Literal["min_fuzzy_logic", "minimum", "product", "geometric_mean"] = "min_fuzzy_logic",
    bii_year_start: int = DEFAULT_BII_YEAR_START,
    bii_year_end: int = DEFAULT_BII_YEAR_END,
    scale: int = DEFAULT_SCALE,
    include_seasonality: bool = True,
) -> Tuple[pd.DataFrame, ee.Image]:
    """
    Extract EII and/or component stats for buffered sampling units.

    Implements:
      A) Multi-year BII mean with fallback if date range is empty
      B) Single stacked image sampling (one map/getInfo total)
      C) Consistent band naming across outputs
    """
    logger.info("-----------------------------------------------")
    logger.info("Starting --Ecosystem Integrity Index (EII)-- extraction...")
    logger.info(f"Layers: {layers}")
    logger.info(f"Aggregation method: {aggregation_method}")
    logger.info(f"BII temporal range: {bii_year_start}-{bii_year_end}")
    logger.info(f"Scale: {scale}m")

    # 1) Load layers (functional/structural precomputed + compositional multiyear)
    layer_images = _load_eii_layers(
        aoi=aoi,
        layers=layers,
        aggregation_method=aggregation_method,
        bii_year_start=bii_year_start,
        bii_year_end=bii_year_end,
        include_seasonality=include_seasonality,
    )

    # 2) Build a single image stack (B)
    # Keep a deterministic band order (optional but nice)
    desired_order = []
    if layers in ("eii", "all"):
        desired_order.append(EII_BAND)
    if layers in ("components", "all"):
        desired_order.extend([FUNCTIONAL_BAND, STRUCTURAL_BAND, COMPOSITIONAL_BAND])

    # Stack only what we have (safe)
    band_images = []
    for name in desired_order:
        if name in layer_images:
            band_images.append(layer_images[name].rename(name))

    if not band_images:
        raise ValueError("No layers were loaded; check your 'layers' parameter and assets.")

    image_stack = ee.Image.cat(band_images).clip(aoi)

    # Fetch band names once (avoid per-layer getInfo)
    band_names = list(image_stack.bandNames().getInfo())

    logger.info(f"Sampling bands: {band_names}")

    # 3) Sample all bands in one pass (B)
    compute_stats = build_variable_extractor(image_stack, band_names, scale)
    fc_stats = points_feature_collection.map(compute_stats)

    results = _fetch_results(fc_stats, "EII_STACK")

    # 4) Merge once into df (B + C)
    result_df = df.copy()
    result_df = _merge_stack_results(result_df, results, band_names)

    _log_extraction_summary(result_df, band_names)
    return result_df, image_stack


def _load_eii_layers(
    aoi: ee.Geometry,
    layers: str = "all",
    aggregation_method: Literal["min_fuzzy_logic", "minimum", "product", "geometric_mean"] = "min_fuzzy_logic",
    bii_year_start: int = DEFAULT_BII_YEAR_START,
    bii_year_end: int = DEFAULT_BII_YEAR_END,
    include_seasonality: bool = True,
) -> Dict[str, ee.Image]:
    """
    Load EII layers with multi-year BII temporal averaging.

    C) Enforces consistent band naming:
       functional_integrity, structural_integrity, compositional_integrity, eii
    """
    # Precomputed functional & structural
    precomputed = get_layers(
        layers="components",
        compute_mode="precomputed",
        # geometry is ignored in precomputed mode; we keep it out to avoid confusion
        include_seasonality=include_seasonality,
    )

    functional = precomputed["functional"].rename(FUNCTIONAL_BAND)
    structural = precomputed["structural"].rename(STRUCTURAL_BAND)

    # A) Multi-year compositional (BII mean) with fallback
    compositional = _compute_multiyear_bii_with_fallback(
        aoi=aoi,
        year_start=bii_year_start,
        year_end=bii_year_end,
    ).rename(COMPOSITIONAL_BAND)

    out: Dict[str, ee.Image] = {}

    if layers in ("components", "all"):
        out[FUNCTIONAL_BAND] = functional
        out[STRUCTURAL_BAND] = structural
        out[COMPOSITIONAL_BAND] = compositional

    if layers in ("eii", "all"):
        eii = combine_components(
            functional=functional,
            structural=structural,
            compositional=compositional,
            method=aggregation_method,
        ).rename(EII_BAND)
        out[EII_BAND] = eii

    return out


def _compute_multiyear_bii_with_fallback(
    aoi: ee.Geometry,
    year_start: int,
    year_end: int,
) -> ee.Image:
    """
    A) Compute multi-year BII mean; if no images exist in range, fallback to most recent.
    Returns a single-band image clipped to AOI.
    """
    bii_collection = ee.ImageCollection(BII_ASSET_PATH)

    start_date = f"{year_start}-01-01"
    end_date = f"{year_end}-12-31"

    filtered = bii_collection.filterDate(start_date, end_date)
    most_recent = bii_collection.sort("system:time_start", False).first()

    bii_image = ee.Image(
        ee.Algorithms.If(
            filtered.size().gt(0),
            filtered.mean(),
            most_recent,
        )
    )

    # Clip here to keep things lighter downstream
    return bii_image.clip(aoi)


def _fetch_results(fc_stats: ee.FeatureCollection, label: str) -> Optional[Dict]:
    """Fetch sampled values from Earth Engine."""
    try:
        return fc_stats.getInfo()
    except Exception as exc:
        logger.error(f"Failed to fetch {label} statistics from Earth Engine: {exc}")
        raise


def _merge_stack_results(
    df: pd.DataFrame,
    results: Optional[Dict],
    band_names: list[str],
) -> pd.DataFrame:
    """
    Merge EE sampling results into df for all bands.

    We standardize output columns to:
      - {band}_mean
      - {band}_std

    And map them from EE properties (typical):
      - {band}_mean
      - {band}_stdDev
    """
    # dest_col -> source_property
    column_map: Dict[str, str] = {}
    for band in band_names:
        column_map[f"{band}_mean"] = f"{band}_mean"
        column_map[f"{band}_std"] = f"{band}_stdDev"

    return merge_ee_sampling_results(df, results, column_map)


def _log_extraction_summary(result_df: pd.DataFrame, band_names: list[str]) -> None:
    """Log summary statistics for extracted EII layers (means)."""
    for band in band_names:
        mean_col = f"{band}_mean"
        if mean_col not in result_df.columns:
            logger.warning(f"Column {mean_col} not found in results")
            continue

        valid = result_df[mean_col].notna()
        if valid.sum() == 0:
            continue

        values = result_df.loc[valid, mean_col]
        logger.info(
            f"{band.upper()} mean: "
            f"{values.mean():.3f} ± {values.std():.3f} "
            f"(range {values.min():.3f}-{values.max():.3f})"
        )
