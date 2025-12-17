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

NDVI_COLLECTION_ID = "LANDSAT/LC09/C02/T1_L2"
WATER_MASK_COLLECTION_ID = "GLCF/GLS_WATER"
NDVI_BAND = "ndvi"


def extract_ndvi(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    start_date: str = "2021-11-01",
    end_date: str = "2024-12-31",
    mask_water: bool = True,
    cloud_cover_threshold: int = 50,
    scale: int = 30,
) -> tuple[pd.DataFrame, ee.Image]:
    """
    Batch-extract NDVI statistics (mean and sd) for buffered point locations.
    Args:
        df: Pandas DataFrame containing point locations.
        aoi: ee.Geometry defining the area of interest to crop the collection and reduce processing.
        points_feature_collection: ee.FeatureCollection of buffered points to extract the values.
        start_date: Start date for Landsat imagery (YYYY-MM-DD).
        end_date: End date for Landsat imagery (YYYY-MM-DD).
        mask_water: Whether to apply water masking using GLCF dataset.
        cloud_cover_threshold: Maximum cloud cover percentage to filter Landsat images.
        scale: Scale (in meters) for sampling NDVI values.
    Returns:
        Tuple[pd.DataFrame, ee.Image]: 
            result_df: pd.DataFrame: DataFrame with NDVI_mean and NDVI_std columns added.
            ndvi_composite: ee.Image: The NDVI composite image used for extraction.

    """
    logger.info("-----------------------------------------------")
    logger.info(f"Starting --NDVI-- extraction...")
    logger.info(f"Processing {len(df)} points...")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Scale: {scale}m")
    logger.info(f"Water masking: {mask_water}")

    logger.info("Creating Landsat composite for study area...")
    ndvi_composite = _build_ndvi_composite(aoi, start_date, end_date, mask_water, cloud_cover_threshold)
    
    logger.info("Extracting NDVI statistics for each sampling unit...")
    extract_ndvi_stats = build_variable_extractor(ndvi_composite, [NDVI_BAND], scale)
    ndvi_results = points_feature_collection.map(extract_ndvi_stats)

    logger.info("Fetching results from Earth Engine...")
    results = ndvi_results.getInfo()

    logger.info("Parsing results...")
    result_df = _merge_ndvi_results(df, results)

    _log_extraction_summary(result_df)
    
    return result_df, ee.Image(ndvi_composite)

def _build_ndvi_composite(
    aoi: ee.Geometry,
    start_date: str = "2021-11-01",
    end_date: str = "2024-12-31",
    mask_water: bool = True,
    cloud_cover_threshold: int = 50,
) -> ee.Image:
    """
    Create a single composite for the entire AOI by doing a series of processing operations.
    The composite will be filtered by date and cloud cover, masked for clouds and optionally water,
    converted to surface reflectance, and have NDVI calculated and appended as a band.

    In the ends, each pixel will return a single value for NDVI,
    based on the median value across all images.

    Args:
        aoi: ee.Geometry defining the area of interest to crop the collection and reduce processing.
        start_date: Start date for Landsat imagery (YYYY-MM-DD).
        end_date: End date for Landsat imagery (YYYY-MM-DD).
        mask_water: Whether to apply water masking using GLCF dataset.
        cloud_cover_threshold: Maximum cloud cover percentage to filter Landsat images.

    Returns:
        ee.Image containing NDVI band.
    """
    collection = _load_and_filter_landsat_collection(aoi,
                                                     start_date,
                                                     end_date,
                                                     cloud_cover_threshold)
    base_projection = collection.first().projection()

    glcf_water, osm_water = load_water_layers(aoi=aoi)
    water_mask = build_combined_water_mask(glcf_water=glcf_water,
                                           osm_water=osm_water,
                                           aoi=aoi)

    composite = collection.map(
        lambda img: _process_landsat_image(img,
                                           mask_water,
                                           water_mask)
    ).median()

    if mask_water and water_mask is not None:
        composite = composite.updateMask(water_mask)

    return composite.select([NDVI_BAND]).reproject(base_projection).clip(aoi)


def _load_and_filter_landsat_collection(
    aoi: ee.Geometry,  
    start_date: str,  
    end_date: str,
    cloud_cover_threshold: int = 50,
) -> ee.ImageCollection:
    """Load Landsat imagery filtered by AOI, date, and cloud cover.

    Args:
        aoi: ee.Geometry defining the area of interest to crop the collection and reduce processing.
        start_date: str, Start date for Landsat imagery (YYYY-MM-DD).
        end_date: str, End date for Landsat imagery (YYYY-MM-DD).

    Returns:
        ee.ImageCollection containing Landsat 9 L2 imagery filtered by date and cloud cover.
    """
    collection = (
        ee.ImageCollection(NDVI_COLLECTION_ID)
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUD_COVER", cloud_cover_threshold))  # Cloud cover < 50%
    )

    size = collection.size().getInfo()
    logger.info(f"Found {size} Landsat-9 images for study area")
    if size == 0:
        raise ValueError("No Landsat-9 images found, try adjusting the date range or cloud cover threshold.")

    return collection


def _load_water_mask(
    aoi: ee.Geometry,
    base_projection: ee.Projection,
) -> Optional[ee.Image]:
    """
    Fetch the GLCF water mask mosaicked over the AOI.

    Args:
        aoi: ee.Geometry defining the area of interest to crop the collection and reduce processing.
        base_projection: ee.Projection, The projection to reproject the water mask to.

    Returns:
        ee.Image containing the GLCF water mask or None if the water mask cannot be loaded.
    """
    try:
        logger.info("Loading GLCF water mask...")
        water_collection = ee.ImageCollection(WATER_MASK_COLLECTION_ID)
        water_dataset = water_collection.filterBounds(aoi).mosaic()
        return water_dataset.neq(2).reproject(base_projection)  # 1 = non water, 0 = water
    except Exception as exc:  # pragma: no cover - Earth Engine failure path
        logger.warning(f"Could not load GLCF water mask: {exc}")
        return None


def _process_landsat_image(
    image: ee.Image, 
    mask_water: bool, 
    water_mask: Optional[ee.Image]
) -> ee.Image:
    """Process the Landsat image by applying cloud and water masks (if custom water shape is not provided),
    then convert values to reflectance and calculate NDVI.

    Args:
        image: ee.Image representing the Landsat image.
        mask_water: bool, Whether to mask water or not.
        water_mask: Optional[ee.Image], The GLCF water mask to use for masking water.

    Returns:
        ee.Image containing the masked QA bands, converted to reflectance, and NDVI band.
    """
    masked_image = _apply_cloud_and_optionally_water_masks(image, mask_water, water_mask)
    # Converts raw integer Digital Numbers (DN) to floating-point Surface Reflectance (0.0 to 1.0).
    optical = masked_image.select("SR_B.").toFloat().multiply(0.0000275).add(-0.2)
    ndvi = _calculate_ndvi(optical)
    return masked_image.addBands([optical, ndvi])

def _apply_cloud_and_optionally_water_masks(
    image: ee.Image, 
    mask_water: bool, 
    water_mask: Optional[ee.Image]
) -> ee.Image:
    """
    Apply QA-based cloud masking and optional water masking.
    Landsat images contain a QA_PIXEL band that encodes information about clouds, cloud shadows,
    and water using bitwise flags.
    This function creates a mask to exclude cloudy pixels and, if specified, water pixels.
    
    More information on:
    Landsat 9 QA band information: https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands

    Args:
        image: ee.Image representing the Landsat image to be masked.
        mask_water: bool, Whether to mask water or not.
        water_mask: Optional[ee.Image], The GLCF water mask to use for masking water.
        If None, water masking is perfomed using the QA band instead.

    Returns:
        ee.Image containing the masked QA bands, with cloud and water pixels removed.
    """
    qa_band = image.select("QA_PIXEL")
    cloud_mask = qa_band.bitwiseAnd(1 << 1).eq(0).And(qa_band.bitwiseAnd(1 << 3).eq(0))

    # Apply qa water mask if a custom water shape is not provided
    if mask_water and water_mask is None:
        qa_water_mask = qa_band.bitwiseAnd(1 << 7).eq(0)
        cloud_mask = cloud_mask.And(qa_water_mask)

    return image.updateMask(cloud_mask)


def _calculate_ndvi(
    optical_image: ee.Image
) -> ee.Image:
    """
    Compute NDVI using optical reflectance bands and mask invalid pixels.
    NDVI = (NIR - RED) / (NIR + RED)

    Args:
        optical_image: ee.Image containing the optical reflectance bands (SR_B4 and SR_B5)

    Returns:
        ee.Image containing the NDVI band, with invalid pixels (denominator == 0 or NDVI < -1 or NDVI > 1) masked out.
    """
    nir = optical_image.select("SR_B5")
    red = optical_image.select("SR_B4")

    ndvi_raw = nir.subtract(red).divide(nir.add(red))
    denom = nir.add(red)
    valid_denom = denom.abs().gt(1e-6)
    valid_range = ndvi_raw.gte(-1).And(ndvi_raw.lte(1))
    ndvi_mask = valid_denom.And(valid_range)

    return ndvi_raw.updateMask(ndvi_mask).rename(NDVI_BAND)

def _merge_ndvi_results(
    df: pd.DataFrame,
    results: Optional[Dict],
) -> pd.DataFrame:
    """
    Merge NDVI sampling output into a dataframe copy.
    Expects EE properties 'NDVI_mean' and 'NDVI_std'.
    """
    column_map = {
        "NDVI_mean": f"{NDVI_BAND}_mean",
        "NDVI_std": f"{NDVI_BAND}_stdDev",
    }
    return merge_ee_sampling_results(df, results, column_map)


def _log_extraction_summary(
    result_df: pd.DataFrame
) -> None:
    """Helper function to log how many points produced NDVI values and summary stats.

    Args:
        result_df: pd.DataFrame, The dataframe containing the extracted NDVI values.

    Returns:
        None
    """
    valid_points = result_df["NDVI_mean"].notna().sum()
    logger.info(f"Successfully processed {valid_points}/{len(result_df)} points")

    if valid_points == 0:
        return

    valid_means = result_df["NDVI_mean"].dropna()
    logger.info(f"NDVI range: {valid_means.min():.3f} to {valid_means.max():.3f}")
    logger.info(f"NDVI mean: {valid_means.mean():.3f} ± {valid_means.std():.3f}")
