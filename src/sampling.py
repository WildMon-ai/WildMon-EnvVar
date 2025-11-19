import numpy as np
import pandas as pd
import logging
from typing import Optional, Dict
import ee

# Assume logger and logging setup are configured elsewhere (as in your final code)
logger = logging.getLogger(__name__)

def clean_coordinates_dataframe(
    df: pd.DataFrame, 
    lat_col: str = "latitude", 
    lon_col: str = "longitude"
    ) -> pd.DataFrame:
    """
    Cleans a DataFrame by validating required columns and removing rows with 
    coordinates outside of the standard geographic range.

    Args:
        df: The input Pandas DataFrame.
        lat_col: Name of the latitude column.
        lon_col: Name of the longitude column.

    Returns:
        A tuple containing:
        1. pd.DataFrame: The cleaned DataFrame (a copy).
        2. int: The number of invalid points removed.

    Raises:
        ValueError: If required columns are missing or the input DataFrame is empty.
    """
    
    if lat_col not in df.columns or lon_col not in df.columns:
        raise ValueError(f"Columns '{lat_col}' and/or '{lon_col}' not found in the input DataFrame.")
    
    if df.empty:
        raise ValueError("Input DataFrame is empty.")

    valid_mask = (
        df[lat_col].between(-90, 90) & 
        df[lon_col].between(-180, 180)
    )
    
    df_clean = df[valid_mask].copy()
    
    invalid_count = len(df) - len(df_clean)
    
    if invalid_count > 0:
        logger.warning(f"Removed {invalid_count} points with invalid coordinates (out of bounds).")
        
    if df_clean.empty:
        raise ValueError("DataFrame is empty after removing invalid coordinates. Check your input data.")

    logger.info(f"Successfully validated and cleaned {len(df_clean)} points.")
    return df_clean

def convert_points_to_buffered_features(
        df: pd.DataFrame,
        lat_col: str, lon_col: str,
        buffer_meters: int = 200
    ) -> ee.FeatureCollection:
    """Creates an ee.FeatureCollection of of the sampling units by buffering points
    by a specified radius. This enables batch processing in Earth Engine and taking
    the mean and standard deviation of the values at around the buffered point instead of
    a single point.
    
    Args:
        df: DataFrame with coordinates.
        lat_col: Name of the latitude column.
        lon_col: Name of the longitude column.
        buffer_meters: Buffer radius in meters.
    
    Returns:
        ee.FeatureCollection with buffered points.
        """
    logger.info("Preparing sampling units for batch processing...")
    lons = df[lon_col].values
    lats = df[lat_col].values
    indices = df.index.values

    features = [
        ee.Feature(
            ee.Geometry.Point([float(lon), float(lat)]).buffer(buffer_meters),
            {"index": int(idx)},
        )
        for lon, lat, idx in zip(lons, lats, indices)
    ]
    return ee.FeatureCollection(features)
    
def merge_ee_sampling_results(
    df: pd.DataFrame,
    results: Optional[Dict],
    column_map: Dict[str, str]
) -> pd.DataFrame:
    """
    Generic helper to merge Earth Engine sampling output into a dataframe copy.

    Args:
        df: Original dataframe (index must match the 'index' property in EE features).
        results: dict returned from fc_stats.getInfo().
        column_map: mapping of {dataframe_column_name: ee_property_name}.
        decimals: number of decimal places to round numeric results.

    Returns:
        A new dataframe with added/filled columns as specified in column_map.
    """
    merged = df.copy()

    for col in column_map.keys():
        merged[col] = np.nan

    if not results:
        return merged

    features = results.get("features", [])
    if not features:
        return merged

    parsed: Dict[object, Dict[str, float]] = {}

    for f in features:
        props = f.get("properties", {})
        idx = props.get("index")
        if idx is None or idx not in merged.index:
            continue

        parsed[idx] = {
            df_col: props.get(ee_prop)
            for df_col, ee_prop in column_map.items()
        }

    if parsed:
        for df_col in column_map.keys():
            series = pd.Series({idx: vals[df_col] for idx, vals in parsed.items()})
            merged.loc[series.index, df_col] = series.values

        for df_col in column_map.keys():
            merged[df_col] = merged[df_col].round(3)

    return merged

