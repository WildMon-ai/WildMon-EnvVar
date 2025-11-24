import ee


def extract_elevation(
    df,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    buffer_radius: int = 200,
    scale: int = 90,  # SRTM90_V4 → 90 m
):
    """
    Extract elevation and slope statistics from SRTM90_V4 using optimized
    Earth Engine processing (no batches).

    For each point, computes:
        - elevation_mean: mean elevation (m) within the buffer
        - elevation_std:  std. dev. of elevation (m)
        - slope_mean:     mean slope (degrees)
        - slope_std:      std. dev. of slope (degrees)

    Args:
        df: DataFrame with coordinates.
        lat_col: Name of the latitude column.
        lon_col: Name of the longitude column.
        buffer_radius: Buffer radius in meters around each point.
        scale: Processing scale in meters (default: 90 for SRTM90_V4).

    Returns:
        (result_df, elevation_image):
            result_df: original DataFrame with added elevation/slope columns.
            elevation_image: SRTM elevation image used for the computation.
    """

    result_df = df.copy()

    # SRTM90_V4: main band is 'elevation' (meters)
    elevation_image = ee.Image("CGIAR/SRTM90_V4").select("elevation")

    # Terrain products: slope in degrees
    # ee.Terrain.slope returns a single-band image 'slope'
    slope_image = ee.Terrain.slope(elevation_image).rename("slope")

    # Image with two bands: elevation (m) + slope (degrees)
    elev_slope_image = elevation_image.addBands(slope_image)

    # Validation
    if lat_col not in df.columns or lon_col not in df.columns:
        raise ValueError(f"Columns '{lat_col}' and/or '{lon_col}' not found in DataFrame")

    print(f"Processing {len(df)} points...")

    # Create all features at once (buffer around each point)
    features = [
        ee.Feature(
            ee.Geometry.Point([float(lon), float(lat)]).buffer(buffer_radius),
            {"index": i}  # keep index for sorting later
        )
        for i, (lon, lat) in enumerate(zip(df[lon_col], df[lat_col]))
    ]

    fc = ee.FeatureCollection(features)

    # Reduction function (elevation + slope, mean + stdDev)
    def compute_stats(feature):
        stats = elev_slope_image.reduceRegion(
            reducer=ee.Reducer.mean().combine(
                reducer2=ee.Reducer.stdDev(),
                sharedInputs=True
            ),
            geometry=feature.geometry(),
            scale=scale,
        )
        # stats will have keys:
        # 'elevation_mean', 'elevation_stdDev',
        # 'slope_mean',     'slope_stdDev'
        return feature.set(stats)

    # Process everything at once
    fc_stats = fc.map(compute_stats)

    print("🔄 Waiting for Earth Engine response...")
    stats_info = fc_stats.getInfo()["features"]

    # Keep original order using the 'index' property
    elev_slope_data = sorted(
        [(f["properties"]["index"], f["properties"]) for f in stats_info],
        key=lambda x: x[0],
    )

    elevation_means = [props.get("elevation_mean") for _, props in elev_slope_data]
    elevation_stds = [props.get("elevation_stdDev") for _, props in elev_slope_data]
    slope_means = [props.get("slope_mean") for _, props in elev_slope_data]
    slope_stds = [props.get("slope_stdDev") for _, props in elev_slope_data]

    # Save into DataFrame
    result_df["elevation_mean"] = elevation_means   # meters
    result_df["elevation_std"] = elevation_stds     # meters
    result_df["slope_mean"] = slope_means           # degrees
    result_df["slope_std"] = slope_stds             # degrees

    # Report null values
    null_count = result_df["elevation_mean"].isna().sum()
    if null_count > 0:
        print(f"⚠️ {null_count} points without elevation/slope data")

    print("✅ Elevation and slope statistics extracted (SRTM90_V4)!")
    return result_df, elev_slope_image
