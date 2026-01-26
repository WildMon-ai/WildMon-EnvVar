import logging
from typing import Dict, Literal, Optional, Tuple

import ee
import pandas as pd

from eii.client import get_layers
from eii.compute.integrity import combine_components
from sampling import build_variable_extractor, merge_ee_sampling_results

# EII asset and configuration
BII_ASSET_PATH = "projects/ebx-data/assets/earthblox/IO/BIOINTACT"
DEFAULT_SCALE = 300  # EII recommended resolution for zonal statistics (base data is 10m)
DEFAULT_BII_YEAR_START = 2020  # First year for BII temporal averaging (available: 2016-2019)
DEFAULT_BII_YEAR_END = 2022    # Last year for BII temporal averaging

# EII component band names (as returned by eii package)
EII_BAND = "eii"
FUNCTIONAL_BAND = "functional_integrity"
STRUCTURAL_BAND = "structural_integrity"
COMPOSITIONAL_BAND = "compositional_integrity"
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
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
    Extract Ecosystem Integrity Index (EII) and component statistics for buffered sampling units.

    Uses multi-year temporal averaging for BII (compositional integrity) to reduce interannual
    variability and provide a more robust biodiversity baseline.

    Args:
        df: DataFrame aligned with the buffered feature collection.
        aoi: ee.Geometry defining the area of interest to clip the EII images.
        points_feature_collection: ee.FeatureCollection of buffered sampling units.
        layers: Which layers to extract: "eii", "components", or "all" (default).
        aggregation_method: EII aggregation method (default: "min_fuzzy_logic").
        bii_year_start: First year for BII temporal averaging (2016-2019 available).
        bii_year_end: Last year for BII temporal averaging (2016-2019 available).
        scale: Sampling scale in meters (default: 300m).
        include_seasonality: Include seasonality in functional integrity (default: True).

    Returns:
        (result_df, eii_image_stack):
            result_df: DataFrame with eii_mean/std and component_mean/std columns.
            eii_image_stack: ee.Image containing all extracted layers.
    """
    logger.info("-----------------------------------------------")
    logger.info(f"Starting --Ecosystem Integrity Index (EII)-- extraction...")
    logger.info(f"Layers: {layers}")
    logger.info(f"Aggregation method: {aggregation_method}")
    logger.info(f"BII temporal range: {bii_year_start}-{bii_year_end}")
    logger.info(f"Scale: {scale}m")

    logger.info("Loading EII layers from Earth Engine...")
    layer_images = _load_eii_layers(
        aoi=aoi,
        layers=layers,
        aggregation_method=aggregation_method,
        bii_year_start=bii_year_start,
        bii_year_end=bii_year_end,
        include_seasonality=include_seasonality,
    )

    logger.info("Creating image stack and extracting statistics...")
    result_df = df.copy()

    # Extract statistics for each available layer
    logger.info(f"Extract statistics for each available band")
    images_to_stack = []
    for layer_name, image in layer_images.items():
        

        # Clip to AOI
        clipped_image = image.clip(aoi)
        images_to_stack.append(clipped_image)

        # Get the actual band names from the image
        band_names_info = clipped_image.bandNames().getInfo()
        if not band_names_info:
            logger.warning(f"No bands found for {layer_name}, skipping...")
            continue

        band_names = list(band_names_info) if isinstance(band_names_info, (list, tuple)) else [str(band_names_info)]

        # Extract statistics using actual band names
        compute_stats = build_variable_extractor(clipped_image, band_names, scale)
        fc_stats = points_feature_collection.map(compute_stats)

        results = _fetch_results(fc_stats, layer_name)

        result_df = _merge_layer_results(result_df, results, layer_name, band_names)
        
    # Create image stack for export
    if len(images_to_stack) == 1:
        image_stack = images_to_stack[0]
    else:
        image_stack = ee.Image.cat(images_to_stack)

    _log_extraction_summary(result_df, list(layer_images.keys()))
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

    Computes compositional integrity from multi-year BII average (2016-2019 available),
    while functional and structural components use precomputed datasets from the eii package.

    Args:
        aoi: Area of interest geometry.
        layers: Which layers to load: "eii", "components", or "all".
        aggregation_method: EII aggregation method ("min_fuzzy_logic", "minimum", "product", "geometric_mean").
        bii_year_start: First year for BII temporal averaging (2016-2019).
        bii_year_end: Last year for BII temporal averaging (2016-2019).
        include_seasonality: Include seasonality in functional integrity.

    Returns:
        Dictionary mapping layer names to ee.Image objects.
    """
    try:

        # Compute multi-year BII temporal average for compositional integrity
        compositional_image = _compute_multiyear_bii(
            aoi=aoi,
            year_start=bii_year_start,
            year_end=bii_year_end
        )

        # Get precomputed functional and structural components from eii package
        precomputed_layers = get_layers(
            layers="components",  # Get only component layers (not final EII)
            compute_mode="precomputed",
            geometry=aoi,
            include_seasonality=include_seasonality,
        )

        # Build layer dictionary - Note: get_layers returns 'functional', 'structural', 'compositional' keys
        # but we rename them to match our expected band naming convention
        layer_dict = {
            'functional_integrity': precomputed_layers['functional'].rename('functional_integrity'),
            'structural_integrity': precomputed_layers['structural'].rename('structural_integrity'),
            'compositional_integrity': compositional_image
        }

        # Compute EII if requested
        if layers in ("eii", "all"):
            eii_image = combine_components(
                functional=layer_dict['functional_integrity'],
                structural=layer_dict['structural_integrity'],
                compositional=layer_dict['compositional_integrity'],
                method=aggregation_method
            ).rename('eii')
            layer_dict['eii'] = eii_image

        # Filter to requested layers
        if layers == "eii":
            layer_dict = {'eii': layer_dict['eii']}
        elif layers == "components":
            layer_dict = {k: v for k, v in layer_dict.items() if k != 'eii'}

        return layer_dict

    except Exception as exc:
        logger.error(
            f"Failed to load EII layers: {exc}\n"
            "Verify:\n"
            "  1. Earth Engine is initialized (ee.Initialize())\n"
            "  2. GCP project has access to landler-open-data assets\n"
            "  3. Geometry is valid and within supported regions\n"
            "  4. BII year range (2016-2019) is valid"
        )
        raise


def _compute_multiyear_bii(
    aoi: ee.Geometry,
    year_start: int,
    year_end: int
) -> ee.Image:
    """
    Compute multi-year temporal average of Biodiversity Intactness Index.

    Args:
        aoi: Area of interest geometry.
        year_start: First year for temporal averaging (2016-2019).
        year_end: Last year for temporal averaging (2016-2019).

    Returns:
        ee.Image with single band 'compositional_integrity' containing multi-year BII average.
    """
    bii_collection = ee.ImageCollection(BII_ASSET_PATH)

    # Filter to temporal range and compute mean
    start_date = f"{year_start}-01-01"
    end_date = f"{year_end}-12-31"

    multi_year_bii = bii_collection.filterDate(start_date, end_date).mean()

    # Rename to match EII component naming convention
    compositional_image = multi_year_bii.rename('compositional_integrity').clip(aoi)

    return compositional_image


def _fetch_results(
    fc_stats: ee.FeatureCollection,
    layer_name: str,
) -> Optional[Dict]:
    """Fetch sampled values from Earth Engine."""
    try:
        return fc_stats.getInfo()
    except Exception as exc:  # pragma: no cover - EE failure path
        logger.error(f"Failed to fetch {layer_name} statistics from Earth Engine: {exc}")
        raise


def _merge_layer_results(
    df: pd.DataFrame,
    results: Optional[Dict],
    layer_name: str,
    band_names: list[str],
) -> pd.DataFrame:
    """Merge layer sampling output into a dataframe."""
    # Use the actual band name (first band if multiple)
    actual_band_name = band_names[0] if band_names else layer_name

    column_map = {
        f"{layer_name}_mean": f"{actual_band_name}_mean",
        f"{layer_name}_std": f"{actual_band_name}_stdDev",
    }
    return merge_ee_sampling_results(df, results, column_map)


def _log_extraction_summary(result_df: pd.DataFrame, layer_names: list[str]) -> None:
    """Log summary statistics for all extracted EII layers."""
    total_points = len(result_df)

    for layer_name in layer_names:
        mean_col = f"{layer_name}_mean"

        if mean_col not in result_df.columns:
            logger.warning(f"Column {mean_col} not found in results")
            continue

        valid_mask = result_df[mean_col].notna()
        valid_points = valid_mask.sum()

        if valid_points == 0:
            continue

        values = result_df.loc[valid_mask, mean_col]
        logger.info(
            f"{layer_name.upper()} mean: "
            f"{values.mean():.3f} ± {values.std():.3f} "
            f"(range {values.min():.3f}-{values.max():.3f})"
        )
