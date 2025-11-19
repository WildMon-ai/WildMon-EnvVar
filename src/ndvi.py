import logging

import ee
import numpy as np
import pandas as pd

from typing import Optional, Callable, List, Dict

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

NDVI_COLLECTION_ID = "LANDSAT/LC09/C02/T1_L2"
WATER_MASK_COLLECTION_ID = "GLCF/GLS_WATER"


def extract_ndvi(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    start_date: str = "2021-11-01",
    end_date: str = "2024-12-31",
    mask_water: bool = True,
    scale: int = 30,
) -> pd.DataFrame:
    """
    Batch-extract NDVI statistics (mean and sd) for buffered point locations.
    Args:
        df: Pandas DataFrame containing point locations.
        aoi: ee.Geometry defining the area of interest to crop the collection and reduce processing.
        points_feature_collection: ee.FeatureCollection of buffered points to extract the values.
        start_date: Start date for Landsat imagery (YYYY-MM-DD).
        end_date: End date for Landsat imagery (YYYY-MM-DD).
        mask_water: Whether to apply water masking using GLCF dataset.
        scale: Scale (in meters) for sampling NDVI values.
    Returns:
        pd.DataFrame: DataFrame with NDVI_mean and NDVI_std columns added.
    """
    logger.info(f"Processing {len(df)} points...")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Scale: {scale}m")
    logger.info(f"Water masking: {mask_water}")

    logger.info("Creating Landsat composite for study area...")
    composite = _build_ndvi_composite(aoi, start_date, end_date, mask_water)
    
    logger.info("Extracting NDVI statistics for each sampling unit...")
    extract_ndvi_stats = _build_ndvi_extractor(composite, scale)
    ndvi_results = points_feature_collection.map(extract_ndvi_stats)

    logger.info("Fetching results from Earth Engine...")
    results = ndvi_results.getInfo()

    logger.info("Parsing results...")
    result_df = _merge_ndvi_results(df, results)

    _log_extraction_summary(result_df)
    return result_df, composite

def _build_ndvi_composite(
    aoi: ee.Geometry,
    start_date: str = "2021-11-01",
    end_date: str = "2024-12-31",
    mask_water: bool = True,
) -> ee.Image:
    """
    Create a single composite for the entire AOI by doing a series of processing operations.
    The composite will be filtered by date and cloud cover, masked for clouds and optionally water,
    converted to surface reflectance, and have NDVI calculated and appended as a band.

    In the ends, each pixel will return a single value for SR_B5, SR_B4,
    and NDVI based on the most recent observation (.mosaic()).

    Args:
        aoi: ee.Geometry defining the area of interest to crop the collection and reduce processing.
        start_date: Start date for Landsat imagery (YYYY-MM-DD).
        end_date: End date for Landsat imagery (YYYY-MM-DD).
        mask_water: Whether to apply water masking using GLCF dataset.

    Returns:
        ee.Image containing SR_B5, SR_B4, and NDVI bands.
    """
    collection = _load_and_filter_landsat_collection(aoi, start_date, end_date)
    water_mask = _load_water_mask(aoi) if mask_water else None

    composite = collection.map(
        lambda img: _process_landsat_image(img, mask_water, water_mask)
    ).mosaic() # consider changing to .median() to reduce noise

    if mask_water and water_mask is not None:
        composite = composite.updateMask(water_mask)

    return composite.select(["SR_B5", "SR_B4", "NDVI"])


def _load_and_filter_landsat_collection(
    aoi: ee.Geometry,  
    start_date: str,  
    end_date: str,
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
        .filter(ee.Filter.lt("CLOUD_COVER", 50))  # Cloud cover < 50%
    )

    size = collection.size().getInfo()
    logger.info(f"Found {size} Landsat 9 images for study area")
    if size == 0:
        raise ValueError("No Landsat 9 images found")

    return collection


def _load_water_mask(
    aoi: ee.Geometry
) -> Optional[ee.Image]:
    """
    Fetch the GLCF water mask mosaicked over the AOI.

    Args:
        aoi: ee.Geometry defining the area of interest to crop the collection and reduce processing.

    Returns:
        ee.Image containing the GLCF water mask or None if the water mask cannot be loaded.
    """
    try:
        logger.info("Loading GLCF water mask...")
        water_collection = ee.ImageCollection(WATER_MASK_COLLECTION_ID)
        water_dataset = water_collection.filterBounds(aoi).mosaic()
        return water_dataset.neq(2)  # 1 = non water, 0 = water
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

    return ndvi_raw.updateMask(ndvi_mask).rename("NDVI")


def _build_ndvi_extractor(
    composite: ee.Image, 
    scale: float
) -> Callable[[ee.Feature], ee.Feature]:
    """
    Return a function that samples NDVI mean/stdDev for a feature geometry.
    In this case the feature is expected to be a buffered sampling points.

    Args:
        composite: ee.Image containing the NDVI band.
        scale: float, The scale at which the sampling will be done.

    Returns:
        Callable[[ee.Feature], ee.Feature], A function that takes an ee.Feature,
        and returns the same feature with the NDVI mean and standard deviation added as properties.
    """

    def extract_ndvi_stats(feature: ee.Feature) -> ee.Feature:
        stats = composite.select("NDVI").reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
            geometry=feature.geometry(),
            scale=scale,
            maxPixels=1e9,
            bestEffort=True,
        )
        return feature.set(
            {"NDVI_mean": stats.get("NDVI_mean"), "NDVI_std": stats.get("NDVI_stdDev")}
        )

    return extract_ndvi_stats

def _merge_ndvi_results(
    df: pd.DataFrame, 
    results: Optional[List[Dict]]
) -> pd.DataFrame:
    """
    Merge Earth Engine sampling output into a dataframe copy.

    Args:
        df: pd.DataFrame, The dataframe to merge the results into.
        results: Optional[List[Dict]], The list of features returned from the Earth Engine.

    Returns:
        pd.DataFrame, The dataframe with the merged results.
    """
    merged = df.copy()
    merged["NDVI_mean"] = np.nan
    merged["NDVI_std"] = np.nan

    if not results:
        return merged

    features = results.get("features", [])
    if not features:
        return merged

    parsed = {
        f["properties"]["index"]: {
            "NDVI_mean": f["properties"].get("NDVI_mean"),
            "NDVI_std": f["properties"].get("NDVI_std"),
        }
        for f in features
    }

    if parsed:
        series_mean = pd.Series({k: v["NDVI_mean"] for k, v in parsed.items()})
        series_std = pd.Series({k: v["NDVI_std"] for k, v in parsed.items()})
        merged.loc[series_mean.index, "NDVI_mean"] = series_mean.values
        merged.loc[series_std.index, "NDVI_std"] = series_std.values

    return merged


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
