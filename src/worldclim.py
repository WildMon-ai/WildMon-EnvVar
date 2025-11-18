import ee
import pandas as pd
import numpy as np
from typing import List, Optional, Dict
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


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


def _validate_inputs(
    df: pd.DataFrame,
    lat_col: str,
    lon_col: str,
    variables: List[str]
) -> None:
    """Validate input parameters."""
    if lat_col not in df.columns:
        raise ValueError(f"Latitude column '{lat_col}' not found in DataFrame")
    
    if lon_col not in df.columns:
        raise ValueError(f"Longitude column '{lon_col}' not found in DataFrame")
    
    if df.empty:
        raise ValueError("DataFrame is empty")
    
    invalid_vars = [v for v in variables if v not in SCALE_FACTORS]
    if invalid_vars:
        raise ValueError(f"Invalid variables: {invalid_vars}. Valid options: {list(SCALE_FACTORS.keys())}")


def _filter_valid_coordinates(
    df: pd.DataFrame,
    lat_col: str,
    lon_col: str
) -> pd.DataFrame:
    """Filter out invalid coordinates and return clean DataFrame."""
    valid_mask = (
        df[lat_col].between(-90, 90) & 
        df[lon_col].between(-180, 180) &
        df[lat_col].notna() &
        df[lon_col].notna()
    )
    
    df_clean = df[valid_mask].copy()
    
    invalid_count = len(df) - len(df_clean)
    if invalid_count > 0:
        logger.warning(f"Removed {invalid_count} points with invalid coordinates")
    
    if df_clean.empty:
        raise ValueError("No valid coordinates remaining after filtering")
    
    return df_clean


def _prepare_worldclim_image(variables: List[str]) -> ee.Image:
    """
    Prepare WorldClim image with scaled variables.
    
    Args:
        variables: List of bio variables to include
        
    Returns:
        Earth Engine Image with scaled bands
    """
    image = ee.Image(DATASET_ID)
    
    # Scale and rename all bands at once
    scaled_bands = [
        image.select(var).multiply(SCALE_FACTORS[var]).rename(var)
        for var in variables
    ]
    
    return ee.Image.cat(scaled_bands)


def _create_point_features(
    df: pd.DataFrame,
    lat_col: str,
    lon_col: str,
    buffer_meters: int
) -> ee.FeatureCollection:
    """
    Create Earth Engine FeatureCollection from DataFrame coordinates.
    
    Args:
        df: DataFrame with coordinates
        lat_col: Latitude column name
        lon_col: Longitude column name
        buffer_meters: Buffer radius in meters
        
    Returns:
        Earth Engine FeatureCollection
    """
    # Extract as numpy arrays for speed
    lons = df[lon_col].values
    lats = df[lat_col].values
    indices = df.index.values
    
    # Create features with list comprehension
    features = [
        ee.Feature(
            ee.Geometry.Point([float(lon), float(lat)]).buffer(buffer_meters),
            {'index': int(idx)}
        )
        for lon, lat, idx in zip(lons, lats, indices)
    ]
    
    return ee.FeatureCollection(features)


def _sample_points(
    points_fc: ee.FeatureCollection,
    image: ee.Image,
    variables: List[str],
    scale: int
) -> dict:
    """
    Sample image values at all points in batch.
    
    Args:
        points_fc: FeatureCollection of points
        image: Image to sample
        variables: List of variable names
        scale: Scale in meters
        
    Returns:
        Dictionary mapping indices to variable values
    """
    def sample_at_point(feature):
        """Sample statistics for a single buffered point."""
        reducer = ee.Reducer.mean().combine(
            reducer2=ee.Reducer.stdDev(),
            sharedInputs=True
        )
        
        stats = image.reduceRegion(
            reducer=reducer,
            geometry=feature.geometry(),
            scale=scale,
            maxPixels=1e9,
            bestEffort=True,
        )
        
        # Build property dictionary for all variables
        props = {'index': feature.get('index')}
        for var in variables:
            props[f'{var}_mean'] = stats.get(f'{var}_mean')
            props[f'{var}_stdDev'] = stats.get(f'{var}_stdDev')
        
        return feature.set(props)
    
    # Server-side mapping
    results_fc = points_fc.map(sample_at_point)
    
    # Single getInfo() call for all points
    logger.info("Fetching results from Earth Engine...")
    results = results_fc.getInfo()
    
    # Parse results into dictionary
    results_dict = {}
    for feature in results['features']:
        props = feature['properties']
        idx = props['index']
        
        values = {
            f'{var}_{stat}': props.get(f'{var}_{stat}')
            for var in variables
            for stat in ['mean', 'stdDev']
        }
        
        results_dict[idx] = values
    
    return results_dict


def _add_results_to_dataframe(
    df: pd.DataFrame,
    results_dict: dict,
    variables: List[str]
) -> pd.DataFrame:
    """
    Add extraction results to DataFrame.
    
    Args:
        df: Original DataFrame
        results_dict: Dictionary of results by index
        variables: List of variables extracted
        
    Returns:
        DataFrame with added columns
    """
    result_df = df.copy()
    
    # Initialize columns with NaN
    for var in variables:
        result_df[f'{var}_mean'] = np.nan
        result_df[f'{var}_stdDev'] = np.nan
    
    # Convert results to DataFrame for efficient assignment
    if results_dict:
        results_data = pd.DataFrame.from_dict(results_dict, orient='index')
        
        # Vectorized assignment
        result_df.loc[results_data.index, results_data.columns] = results_data.values
    
    return result_df


def _log_summary_statistics(
    df: pd.DataFrame,
    variables: List[str],
    total_points: int
) -> None:
    """Log summary statistics of extraction results."""
    # Count successful extractions
    first_var_col = f'{variables[0]}_mean'
    valid_points = df[first_var_col].notna().sum()
    
    logger.info(f"Successfully processed {valid_points}/{total_points} points")
    
    if valid_points == 0:
        return
    
    # Log temperature statistics if available
    if 'bio01_mean' in df.columns:
        temps = df['bio01_mean'].dropna()
        if len(temps) > 0:
            logger.info(
                f"Annual Mean Temperature (bio01): "
                f"{temps.min():.1f}°C to {temps.max():.1f}°C "
                f"(mean: {temps.mean():.1f}°C)"
            )
    
    # Log precipitation statistics if available
    if 'bio12_mean' in df.columns:
        precip = df['bio12_mean'].dropna()
        if len(precip) > 0:
            logger.info(
                f"Annual Precipitation (bio12): "
                f"{precip.min():.0f}mm to {precip.max():.0f}mm "
                f"(mean: {precip.mean():.0f}mm)"
            )


def extract_worldclim(
    df: pd.DataFrame,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    variables: Optional[List[str]] = None,
    buffer_meters: int = 200,
    scale: int = SCALE,
) -> pd.DataFrame:
    """
    Extract WorldClim bioclimatic variables for coordinates using batch processing.
    
    Creates ONE image, then samples all points in a single batch operation.
    Uses vectorized operations throughout - NO iterrows(), NO per-point getInfo() calls.
    
    Args:
        df: DataFrame with coordinates
        lat_col: Latitude column name
        lon_col: Longitude column name  
        variables: List of bio variables to extract (default: all 19)
        buffer_meters: Buffer radius around points in meters
        scale: Processing scale in meters
        
    Returns:
        DataFrame with {variable}_mean and {variable}_stdDev columns added
        
    Raises:
        ValueError: If inputs are invalid or no valid coordinates remain
        
    Example:
        >>> df = pd.DataFrame({'lat': [-23.5], 'lon': [-46.6]})
        >>> result = extract_worldclim(df, lat_col='lat', lon_col='lon')
    """
    # Default to all variables
    if variables is None:
        variables = list(SCALE_FACTORS.keys())
    
    # Validate inputs
    _validate_inputs(df, lat_col, lon_col, variables)
    
    # Filter valid coordinates
    df_clean = _filter_valid_coordinates(df, lat_col, lon_col)
    
    # Log processing info
    logger.info(f"Processing {len(df_clean)} points...")
    logger.info(f"Variables: {', '.join(variables)}")
    logger.info(f"Buffer: {buffer_meters}m, Scale: {scale}m")
    
    # Prepare WorldClim image once
    logger.info("Preparing WorldClim image...")
    worldclim_image = _prepare_worldclim_image(variables)
    
    # Create point features
    logger.info("Preparing points for batch processing...")
    points_fc = _create_point_features(df_clean, lat_col, lon_col, buffer_meters)
    
    # Sample all points (batch operation)
    logger.info("Extracting bioclimatic variables (batch operation)...")
    results_dict = _sample_points(points_fc, worldclim_image, variables, scale)
    
    # Add results to DataFrame
    logger.info("Parsing results...")
    result_df = _add_results_to_dataframe(df, results_dict, variables)
    
    # Log summary
    _log_summary_statistics(result_df, variables, len(df))
    
    return result_df
