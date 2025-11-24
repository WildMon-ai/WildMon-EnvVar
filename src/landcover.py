import ee
import pandas as pd
import numpy as np
from typing import Optional
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ESA WorldCover landcover class definitions
LANDCOVER_CLASSES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}


def _validate_inputs(
    df: pd.DataFrame,
    lat_col: str,
    lon_col: str
) -> None:
    """Validate input parameters."""
    if lat_col not in df.columns:
        raise ValueError(f"Latitude column '{lat_col}' not found in DataFrame")
    
    if lon_col not in df.columns:
        raise ValueError(f"Longitude column '{lon_col}' not found in DataFrame")
    
    if df.empty:
        raise ValueError("DataFrame is empty")


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


def _load_worldcover_image(start_year: int, end_year: int) -> ee.Image:
    """
    Load ESA WorldCover image for specified time period.
    
    Args:
        start_year: Start year
        end_year: End year
        
    Returns:
        ESA WorldCover image
    """
    logger.info(f"Loading ESA WorldCover data ({start_year}-{end_year})...")
    
    worldcover = (
        ee.ImageCollection("ESA/WorldCover/v200")
        .filterDate(f"{start_year}-01-01", f"{end_year}-01-01")
        .first()
        .select("Map")
    )
    
    return worldcover


def _create_point_features(
    df: pd.DataFrame,
    lat_col: str,
    lon_col: str,
    buffer_meters: int
) -> ee.FeatureCollection:
    """
    Create FeatureCollection from DataFrame points with buffers.
    
    Args:
        df: DataFrame with coordinates
        lat_col: Latitude column name
        lon_col: Longitude column name
        buffer_meters: Buffer radius in meters
        
    Returns:
        FeatureCollection with buffered point features
    """
    # Extract as numpy arrays
    lats = df[lat_col].values
    lons = df[lon_col].values
    indices = df.index.values
    
    # Create features using vectorized approach
    features = [
        ee.Feature(
            ee.Geometry.Point([float(lon), float(lat)]).buffer(buffer_meters),
            {'index': int(idx)}
        )
        for lon, lat, idx in zip(lons, lats, indices)
    ]
    
    return ee.FeatureCollection(features)


def _sample_landcover(
    points_fc: ee.FeatureCollection,
    landcover_image: ee.Image,
    scale: int
) -> dict:
    """
    Sample landcover values at all points in batch.
    
    Args:
        points_fc: FeatureCollection of points
        landcover_image: Landcover image to sample
        scale: Scale in meters
        
    Returns:
        Dictionary mapping indices to landcover statistics
    """
    logger.info("Extracting landcover statistics (batch operation)...")
    
    def sample_at_point(feature):
        """Sample landcover statistics for a single buffered point."""
        reducer = ee.Reducer.mean().combine(
            reducer2=ee.Reducer.stdDev(),
            sharedInputs=True
        )
        
        stats = landcover_image.reduceRegion(
            reducer=reducer,
            geometry=feature.geometry(),
            scale=scale,
            maxPixels=1e9,
            bestEffort=True,
        )
        
        return feature.set({
            'index': feature.get('index'),
            'landcover_mean': stats.get('Map_mean'),
            'landcover_std': stats.get('Map_stdDev')
        })
    
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
        
        results_dict[idx] = {
            'landcover_mean': props.get('landcover_mean'),
            'landcover_std': props.get('landcover_std')
        }
    
    return results_dict


def _add_landcover_to_dataframe(
    df: pd.DataFrame,
    results_dict: dict
) -> pd.DataFrame:
    """
    Add landcover results to DataFrame.
    
    Args:
        df: Original DataFrame
        results_dict: Dictionary of results by index
        
    Returns:
        DataFrame with landcover columns added
    """
    result_df = df.copy()
    
    # Initialize columns with NaN
    result_df['landcover_mean'] = np.nan
    result_df['landcover_std'] = np.nan
    
    # Convert results to DataFrame for efficient assignment
    if results_dict:
        results_data = pd.DataFrame.from_dict(results_dict, orient='index')
        result_df.loc[results_data.index, results_data.columns] = results_data.values
    
    return result_df


def _classify_landcover(value: float) -> str:
    """
    Classify landcover value to nearest class.
    
    Args:
        value: Mean landcover value
        
    Returns:
        Landcover class name
    """
    if pd.isna(value) or value is None:
        return "Unknown"
    
    # Find closest class
    closest_class = min(LANDCOVER_CLASSES.keys(), key=lambda x: abs(x - value))
    return LANDCOVER_CLASSES[closest_class]


def _add_landcover_interpretation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add interpretation of landcover values.
    
    Args:
        df: DataFrame with landcover_mean column
        
    Returns:
        DataFrame with dominant_landcover column added
    """
    result_df = df.copy()
    
    if 'landcover_mean' in result_df.columns:
        result_df['dominant_landcover'] = result_df['landcover_mean'].apply(_classify_landcover)
    
    return result_df


def _log_summary_statistics(
    df: pd.DataFrame,
    total_points: int
) -> None:
    """Log summary statistics of landcover extraction."""
    valid_landcover = df['landcover_mean'].notna()
    valid_count = valid_landcover.sum()
    
    logger.info(f"Successfully processed {valid_count}/{total_points} points")
    
    if valid_count == 0:
        return
    
    # Log landcover class distribution
    if 'dominant_landcover' in df.columns:
        class_counts = df[valid_landcover]['dominant_landcover'].value_counts()
        logger.info("Landcover class distribution:")
        for class_name, count in class_counts.items():
            percentage = (count / valid_count) * 100
            logger.info(f"  {class_name}: {count} points ({percentage:.1f}%)")


def extract_landcover(
    df: pd.DataFrame,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    buffer_meters: int = 200,
    start_year: int = 2021,
    end_year: int = 2025,
    scale: int = 10,
    interpret: bool = True,
) -> pd.DataFrame:
    """
    Extract ESA WorldCover landcover data for coordinates using batch processing.
    
    Creates ONE image, then samples all points in a single batch operation.
    Uses vectorized operations throughout - NO loops with getInfo() per batch.
    
    Args:
        df: DataFrame with coordinates
        lat_col: Latitude column name
        lon_col: Longitude column name
        buffer_meters: Buffer radius around points in meters
        start_year: Start year for landcover data
        end_year: End year for landcover data
        scale: Processing scale in meters (ESA WorldCover native resolution is 10m)
        interpret: Add dominant landcover class interpretation
        
    Returns:
        DataFrame with landcover_mean, landcover_std, and optionally 
        dominant_landcover columns added
        
    Raises:
        ValueError: If inputs are invalid or no valid coordinates remain
        
    Example:
        >>> df = pd.DataFrame({'latitude': [-23.5], 'longitude': [-46.6]})
        >>> result = extract_landcover(df)
        >>> print(result[['landcover_mean', 'dominant_landcover']])
    """
    # Validate inputs
    _validate_inputs(df, lat_col, lon_col)
    
    # Filter valid coordinates
    df_clean = _filter_valid_coordinates(df, lat_col, lon_col)
    
    # Log processing info
    logger.info(f"Processing {len(df_clean)} points...")
    logger.info(f"Time period: {start_year}-{end_year}")
    logger.info(f"Buffer: {buffer_meters}m, Scale: {scale}m")
    
    # Load WorldCover image
    worldcover_image = _load_worldcover_image(start_year, end_year)
    
    # Create point features
    logger.info("Preparing points for batch processing...")
    points_fc = _create_point_features(df_clean, lat_col, lon_col, buffer_meters)
    
    # Sample landcover (batch operation)
    results_dict = _sample_landcover(points_fc, worldcover_image, scale)
    
    # Add results to DataFrame
    logger.info("Adding results to DataFrame...")
    result_df = _add_landcover_to_dataframe(df, results_dict)
    
    # Add interpretation if requested
    if interpret:
        result_df = _add_landcover_interpretation(result_df)
    
    # Log summary
    _log_summary_statistics(result_df, len(df))
    
    return result_df, worldcover_image


def interpret_landcover_values(
    df: pd.DataFrame,
    mean_col: str = "landcover_mean",
    output_col: str = "dominant_landcover"
) -> pd.DataFrame:
    """
    Add interpretation of landcover values to existing DataFrame.
    
    Useful for adding interpretation after the fact or with custom column names.
    
    Args:
        df: DataFrame with landcover values
        mean_col: Name of column with mean landcover values
        output_col: Name for output interpretation column
        
    Returns:
        DataFrame with landcover interpretation column added
        
    Example:
        >>> df = pd.DataFrame({'landcover_mean': [10, 40, 80]})
        >>> result = interpret_landcover_values(df)
        >>> print(result['dominant_landcover'])
    """
    if mean_col not in df.columns:
        logger.warning(f"Column '{mean_col}' not found in DataFrame")
        logger.warning(f"Available columns: {list(df.columns)}")
        return df
    
    result_df = df.copy()
    result_df[output_col] = result_df[mean_col].apply(_classify_landcover)
    
    return result_df


def get_landcover_class_info() -> dict:
    """
    Get ESA WorldCover landcover class definitions.
    
    Returns:
        Dictionary mapping class codes to class names
        
    Example:
        >>> classes = get_landcover_class_info()
        >>> print(classes[10])
        'Tree cover'
    """
    return LANDCOVER_CLASSES.copy()