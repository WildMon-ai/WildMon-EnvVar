import logging
import ee
import pandas as pd
from variables.water import load_water_layers, build_combined_water_mask
from sampling import merge_ee_sampling_results, build_variable_extractor
from typing import Optional, Dict

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

LANDSAT_COLLECTION_ID = "LANDSAT/LC09/C02/T1_L2"

NDVI_BAND = "ndvi"
NDWI_BAND = "ndwi"
MNDWI_BAND = "mndwi"
KNDVI_BAND = "kndvi"


ALL_BANDS = [NDVI_BAND, NDWI_BAND, MNDWI_BAND, KNDVI_BAND]


def extract_landsat_indices(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    start_date: str = "2021-11-01",
    end_date: str = "2024-12-31",
    enabled: Optional[Dict[str, bool]] = None,
    mask_water: bool = True,
    cloud_cover_threshold: int = 50,
    scale: int = 30,
) -> tuple[pd.DataFrame, Dict[str, ee.Image]]:
    """
    Batch-extract Landsat-derived index statistics (mean and stdDev) for buffered point locations.

    Computes NDVI, NDWI, MNDWI, and kNDVI from a single Landsat 9 C02 L2 composite.
    Water masking is applied only to NDVI and kNDVI (vegetation indices); NDWI and MNDWI
    are water indices and should retain water pixels.

    Args:
        df: DataFrame containing point locations.
        aoi: ee.Geometry defining the area of interest.
        points_feature_collection: ee.FeatureCollection of buffered points.
        start_date: Start date for Landsat imagery (YYYY-MM-DD).
        end_date: End date for Landsat imagery (YYYY-MM-DD).
        enabled: Dict of {band_name: bool} controlling which indices to extract.
                 Defaults to all enabled if None.
        mask_water: Whether to apply water masking to vegetation indices (NDVI, kNDVI).
        cloud_cover_threshold: Maximum cloud cover percentage to filter Landsat images.
        scale: Scale in meters for sampling.

    Returns:
        Tuple of:
            - df with mean/stdDev columns added for each enabled index.
            - Dict mapping band name to its ee.Image composite.
    """
    if enabled is None:
        enabled = {b: True for b in ALL_BANDS}

    active_bands = [b for b in ALL_BANDS if enabled.get(b, False)]
    if not active_bands:
        return df, {}

    logger.info("-----------------------------------------------")
    logger.info("Starting --Landsat Indices-- extraction...")
    logger.info(f"Indices: {active_bands}")
    logger.info(f"Processing {len(df)} points...")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Scale: {scale}m | Water masking: {mask_water}")

    composite = _build_indices_composite(aoi, start_date, end_date, mask_water, cloud_cover_threshold)

    extract_stats = build_variable_extractor(composite.select(active_bands), active_bands, scale)
    results = points_feature_collection.map(extract_stats).getInfo()

    column_map = _build_column_map(active_bands)
    result_df = merge_ee_sampling_results(df, results, column_map)

    _log_extraction_summary(result_df, active_bands)

    images = {band: composite.select([band]).clip(aoi) for band in active_bands}
    return result_df, images


def _build_indices_composite(
    aoi: ee.Geometry,
    start_date: str,
    end_date: str,
    mask_water: bool,
    cloud_cover_threshold: int,
) -> ee.Image:
    """
    Build a median Landsat composite with NDVI, NDWI, MNDWI, and kNDVI bands.

    Water masking is applied selectively: NDVI and kNDVI bands are masked; NDWI and MNDWI are not.
    """
    collection = _load_and_filter_collection(aoi, start_date, end_date, cloud_cover_threshold)

    glcf_water, osm_water = load_water_layers(aoi=aoi)
    water_mask = build_combined_water_mask(
        glcf_water=glcf_water, osm_water=osm_water, aoi=aoi
    )

    composite = collection.map(lambda img: _process_image(img)).median()

    ndvi = composite.select(NDVI_BAND)
    kndvi = composite.select(KNDVI_BAND)
    ndwi = composite.select(NDWI_BAND)
    mndwi = composite.select(MNDWI_BAND)

    if mask_water and water_mask is not None:
        ndvi = ndvi.updateMask(water_mask)
        kndvi = kndvi.updateMask(water_mask)

    return (
        ndvi.addBands([ndwi, mndwi, kndvi])
        .clip(aoi)
    )


def _load_and_filter_collection(
    aoi: ee.Geometry,
    start_date: str,
    end_date: str,
    cloud_cover_threshold: int,
) -> ee.ImageCollection:
    collection = (
        ee.ImageCollection(LANDSAT_COLLECTION_ID)
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUD_COVER", cloud_cover_threshold))
    )
    size = collection.size().getInfo()
    logger.info(f"Found {size} Landsat-9 images for study area")
    if size == 0:
        raise ValueError(
            "No Landsat-9 images found, try adjusting the date range or cloud cover threshold."
        )
    return collection


def _process_image(image: ee.Image) -> ee.Image:
    """Apply cloud mask, scale optical bands, and compute all four indices."""
    qa = image.select("QA_PIXEL")
    cloud_mask = qa.bitwiseAnd(1 << 1).eq(0).And(qa.bitwiseAnd(1 << 3).eq(0))
    masked = image.updateMask(cloud_mask)

    optical = masked.select("SR_B.").toFloat().multiply(0.0000275).add(-0.2)

    ndvi = _calc_ndvi(optical)
    ndwi = _calc_ndwi(optical)
    mndwi = _calc_mndwi(optical)
    kndvi = _calc_kndvi(ndvi)

    return masked.addBands([optical, ndvi, ndwi, mndwi, kndvi])


def _calc_ndvi(optical: ee.Image) -> ee.Image:
    """NDVI = (NIR - Red) / (NIR + Red). Invalid pixels masked."""
    nir = optical.select("SR_B5")
    red = optical.select("SR_B4")
    raw = nir.subtract(red).divide(nir.add(red))
    valid = nir.add(red).abs().gt(1e-6).And(raw.gte(-1)).And(raw.lte(1))
    return raw.updateMask(valid).rename(NDVI_BAND)


def _calc_ndwi(optical: ee.Image) -> ee.Image:
    """NDWI = (Green - NIR) / (Green + NIR)."""
    green = optical.select("SR_B3")
    nir = optical.select("SR_B5")
    denom = green.add(nir)
    raw = green.subtract(nir).divide(denom)
    valid = denom.abs().gt(1e-6).And(raw.gte(-1)).And(raw.lte(1))
    return raw.updateMask(valid).rename(NDWI_BAND)


def _calc_mndwi(optical: ee.Image) -> ee.Image:
    """MNDWI = (Green - SWIR1) / (Green + SWIR1). Reduces built-up noise vs NDWI."""
    green = optical.select("SR_B3")
    swir1 = optical.select("SR_B6")
    denom = green.add(swir1)
    raw = green.subtract(swir1).divide(denom)
    valid = denom.abs().gt(1e-6).And(raw.gte(-1)).And(raw.lte(1))
    return raw.updateMask(valid).rename(MNDWI_BAND)


def _calc_kndvi(ndvi: ee.Image) -> ee.Image:
    """kNDVI = tanh(NDVI^2). Camps-Valls et al. 2021, eq. 3 (sigma = 0.5*(NIR+Red))."""
    return ndvi.pow(2).tanh().rename(KNDVI_BAND)


def _build_column_map(active_bands: list[str]) -> Dict[str, str]:
    """Build column_map {df_column: ee_property} for active bands."""
    column_map = {}
    for band in active_bands:
        prefix = band.upper() if band != KNDVI_BAND else "kNDVI"
        column_map[f"{prefix}_mean"] = f"{band}_mean"
        column_map[f"{prefix}_std"] = f"{band}_stdDev"
    return column_map


def _log_extraction_summary(result_df: pd.DataFrame, active_bands: list[str]) -> None:
    for band in active_bands:
        prefix = band.upper() if band != KNDVI_BAND else "kNDVI"
        col = f"{prefix}_mean"
        if col not in result_df.columns:
            continue
        valid = result_df[col].notna().sum()
        logger.info(f"{col}: {valid}/{len(result_df)} valid points")
        if valid > 0:
            vals = result_df[col].dropna()
            logger.info(f"  range [{vals.min():.3f}, {vals.max():.3f}], mean {vals.mean():.3f}")
