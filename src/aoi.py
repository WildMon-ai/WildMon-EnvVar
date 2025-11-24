import ee
import pandas as pd


def create_aoi_from_coordinates(
    df: pd.DataFrame, buffer_km: float = 5.0
) -> ee.Geometry:
    """Create Area of Interest from coordinate extremes with buffer."""
    if "latitude" not in df.columns or "longitude" not in df.columns:
        raise ValueError("DataFrame must contain 'latitude' and 'longitude' columns")

    features = [
        ee.Feature(ee.Geometry.Point([row["longitude"], row["latitude"]]))
        for _, row in df.iterrows()
    ]
    feature_collection = ee.FeatureCollection(features)
    aoi = feature_collection.geometry().bounds().buffer(buffer_km * 1000).bounds()

    coords = aoi.getInfo()["coordinates"][0]
    min_lon, min_lat = min(c[0] for c in coords), min(c[1] for c in coords)
    max_lon, max_lat = max(c[0] for c in coords), max(c[1] for c in coords)

    print(
        f"📍 AOI: Lat[{min_lat:.4f}, {max_lat:.4f}], Lon[{min_lon:.4f}, {max_lon:.4f}]"
    )
    print(f"📊 Processing {len(df)} coordinates with {buffer_km}km buffer")

    return aoi
