import ee
import pandas as pd


import pandas as pd
import ee
from typing import Union

def create_aoi_from_coordinates(
    df: pd.DataFrame, buffer_km: float = 5.0
) -> ee.Geometry:
    """
    Create Area of Interest (AOI) from coordinate extremes with buffer.

    This function takes a Pandas DataFrame containing 'latitude' and 'longitude' columns,
    and returns an Earth Engine Geometry representing a rectangular AOI around the coordinates with a buffer
    specified by the user.

    Args:
        df: Pandas DataFrame containing 'latitude' and 'longitude' columns.
        buffer_km: Distance in kilometers to extend the bounding box.

    Returns:
        ee.Geometry: A rectangular Earth Engine Geometry representing the buffered AOI.

    Raises:
        ValueError: If required columns are missing.
    """
    if "latitude" not in df.columns or "longitude" not in df.columns:
        raise ValueError("DataFrame must contain 'latitude' and 'longitude' columns")
    
    lons, lats = df[["longitude", "latitude"]].values.T
    
    features = [
        ee.Feature(ee.Geometry.Point([lon, lat]))
        for lon, lat in zip(lons, lats)
    ]
    feature_collection = ee.FeatureCollection(features)
    
    buffer_m = buffer_km * 1000 # convert from km to meters
    aoi = feature_collection.geometry().bounds().buffer(buffer_m).bounds()

    try:
        coords = aoi.getInfo()["coordinates"][0]
        min_lon, min_lat = min(c[0] for c in coords), min(c[1] for c in coords)
        max_lon, max_lat = max(c[0] for c in coords), max(c[1] for c in coords)

        print(
            f"📍 AOI Bounds: Lat[{min_lat:.4f}, {max_lat:.4f}], Lon[{min_lon:.4f}, {max_lon:.4f}]"
        )
        print(f"📊 Defined study area for {len(df)} points with {buffer_km}km margin.")
    except Exception as e:
        print(f"⚠️ AOI defined in Earth Engine, but failed to fetch coordinates for report: {e}")

    return aoi
