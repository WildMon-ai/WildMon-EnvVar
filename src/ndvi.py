import ee
import pandas as pd
import numpy as np
from typing import Optional, List
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_landsat_composite(
    aoi,
    start_date="2021-11-01",
    end_date="2024-12-31",
    mask_water=True
):
    """Create a single Landsat 9 composite for the entire study area."""
    
    # Load collection once
    collection = (
        ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUD_COVER", 50))
    )
    
    size = collection.size().getInfo()
    logger.info(f"Found {size} Landsat 9 images for study area")
    
    if size == 0:
        raise ValueError("No Landsat 9 images found")
    
    # Load water mask ONCE if needed
    water_mask = None
    if mask_water:
        try:
            logger.info("Loading GLCF water mask...")
            water_collection = ee.ImageCollection("GLCF/GLS_WATER")
            water_dataset = water_collection.filterBounds(aoi).mosaic()
            water_mask = water_dataset.neq(2)
        except Exception as e:
            logger.warning(f"Could not load GLCF water mask: {e}")
    
    def process_image(image):
        """Apply cloud mask and calculate NDVI."""
        qa = image.select("QA_PIXEL")
        cloud_mask = qa.bitwiseAnd(1 << 1).eq(0).And(qa.bitwiseAnd(1 << 3).eq(0))
        
        if mask_water and water_mask is None:
            qa_water_mask = qa.bitwiseAnd(1 << 7).eq(0)
            cloud_mask = cloud_mask.And(qa_water_mask)
        
        image = image.updateMask(cloud_mask)
        
        optical = image.select("SR_B.").toFloat().multiply(0.0000275).add(-0.2)
        nir = optical.select("SR_B5")
        red = optical.select("SR_B4")
        
        # Raw NDVI
        ndvi_raw = nir.subtract(red).divide(nir.add(red))

        # Non-zero denominator mask
        denom = nir.add(red)
        valid_denom = denom.abs().gt(1e-6)

        # Physical range mask [-1, 1]
        valid_range = ndvi_raw.gte(-1).And(ndvi_raw.lte(1))

        # Combine the masks
        ndvi_mask = valid_denom.And(valid_range)

        # Apply mask → bad pixels are masked.
        ndvi = ndvi_raw.updateMask(ndvi_mask).rename("NDVI")

        return image.addBands([optical, ndvi])
    
    composite = collection.map(process_image).mosaic()
    
    if mask_water and water_mask is not None:
        composite = composite.updateMask(water_mask)
    
    return composite.select(["SR_B5", "SR_B4", "NDVI"])


def extract_ndvi(
    df,
    aoi,
    lat_col="latitude",
    lon_col="longitude",
    buffer_meters=200,
    start_date="2021-11-01",
    end_date="2024-12-31",
    mask_water=True,
    scale=30,
) -> pd.DataFrame:
    """
    Extract NDVI values for coordinates using batch processing.

    """
    
    # Validate inputs
    if lat_col not in df.columns or lon_col not in df.columns:
        raise ValueError(f"Columns '{lat_col}' and/or '{lon_col}' not found")
    
    if df.empty:
        raise ValueError("DataFrame is empty")
    
    # Remove invalid coordinates (vectorized)
    valid_mask = (
        df[lat_col].between(-90, 90) & 
        df[lon_col].between(-180, 180)
    )
    df_clean = df[valid_mask].copy()
    
    invalid_count = len(df) - len(df_clean)
    if invalid_count > 0:
        logger.warning(f"Removed {invalid_count} points with invalid coordinates")
    
    logger.info(f"Processing {len(df_clean)} points...")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Buffer: {buffer_meters}m, Scale: {scale}m")
    logger.info(f"Water masking: {mask_water}")
    
    logger.info("Creating Landsat composite for study area...")
    composite = create_landsat_composite(aoi, start_date, end_date, mask_water)
    
    # Create FeatureCollection WITHOUT iterrows - using list comprehension with numpy arrays
    logger.info("Preparing points for batch processing...")
    
    # Extract coordinates as numpy arrays (much faster)
    lons = df_clean[lon_col].values
    lats = df_clean[lat_col].values
    indices = df_clean.index.values
    
    # Create features using list comprehension with zip
    features = [
        ee.Feature(
            ee.Geometry.Point([float(lon), float(lat)]).buffer(buffer_meters),
            {'index': int(idx)}
        )
        for lon, lat, idx in zip(lons, lats, indices)
    ]
    
    points_fc = ee.FeatureCollection(features)
    
    logger.info("Extracting NDVI statistics (batch operation)...")
    
    def sample_ndvi(feature):
        """Sample NDVI statistics for each buffered point."""
        
        #stats = composite.select("NDVI").reduceRegion(
        #    reducer=ee.Reducer.mean().unweighted().combine(
        #        ee.Reducer.stdDev().unweighted(),
        #        sharedInputs=True
        #),
        #geometry=feature.geometry(),
        #scale=scale,
        #maxPixels=1e9,
        #bestEffort=True,
        #)

        stats = composite.select("NDVI").reduceRegion(
            reducer=ee.Reducer.mean().combine(
                ee.Reducer.stdDev(), 
                sharedInputs=True
            ),
            geometry=feature.geometry(),
            scale=scale,
            maxPixels=1e9,
            bestEffort=True,
        )
        
        return feature.set({
            'NDVI_mean': stats.get('NDVI_mean'),
            'NDVI_std': stats.get('NDVI_stdDev')
        })
    
    results_fc = points_fc.map(sample_ndvi)
    
    logger.info("Fetching results from Earth Engine...")
    results = results_fc.getInfo()
    
    # Parse results WITHOUT iterrows - using dictionary comprehension
    logger.info("Parsing results...")
    
    # Extract all results at once
    results_dict = {
        feature['properties']['index']: {
            'NDVI_mean': feature['properties'].get('NDVI_mean'),
            'NDVI_std': feature['properties'].get('NDVI_std')
        }
        for feature in results['features']
    }
    
    # Create result using vectorized operations
    result_df = df.copy()
    
    # Initialize columns with NaN
    result_df['NDVI_mean'] = np.nan
    result_df['NDVI_std'] = np.nan
    
    # Update values using map (much faster than iterrows)
    # Convert results_dict to Series and merge/update
    if results_dict:
        results_series_mean = pd.Series({k: v['NDVI_mean'] for k, v in results_dict.items()})
        results_series_std = pd.Series({k: v['NDVI_std'] for k, v in results_dict.items()})
        
        result_df.loc[results_series_mean.index, 'NDVI_mean'] = results_series_mean.values
        result_df.loc[results_series_std.index, 'NDVI_std'] = results_series_std.values
    
    # Log summary (vectorized)
    valid_points = result_df['NDVI_mean'].notna().sum()
    logger.info(f"Successfully processed {valid_points}/{len(df)} points")
    
    if valid_points > 0:
        valid_means = result_df['NDVI_mean'].dropna()
        logger.info(f"NDVI range: {valid_means.min():.3f} to {valid_means.max():.3f}")
        logger.info(f"NDVI mean: {valid_means.mean():.3f} ± {valid_means.std():.3f}")
    
    return result_df, composite