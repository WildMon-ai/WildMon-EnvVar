import ee
import pandas as pd
import numpy as np


def extract_canopy_height(
    df: pd.DataFrame,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    buffer_distance: float = 200,
    scale: float = 10,
    batch_size: int = 50,
) -> pd.DataFrame:

    dataset_id = "users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1"
    band_name = "b1"
    image = ee.Image(dataset_id).select(band_name)

    result_df = df.copy()
    all_mean_heights = []
    all_std_heights = []
    all_buffers = []

    total_batches = (len(df) + batch_size - 1) // batch_size
    print(
        f"📦 Processing {len(df)} points in {total_batches} batches of {batch_size}..."
    )

    for start in range(0, len(df), batch_size):
        end = min(start + batch_size, len(df))
        batch = df.iloc[start:end]

        # Build list of features with buffer geometry
        features = []
        for lon, lat in zip(batch[lon_col], batch[lat_col]):
            point = ee.Geometry.Point([lon, lat])
            buffer = point.buffer(buffer_distance)
            feature = ee.Feature(buffer)
            features.append(feature)
            all_buffers.append(buffer)

        fc = ee.FeatureCollection(features)

        def compute_stats(feat):
            stat = image.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    ee.Reducer.stdDev(), sharedInputs=True
                ),
                geometry=feat.geometry(),
                scale=scale,
                maxPixels=1e9,
                bestEffort=True,
            )
            return feat.set(stat)

        fc_stats = fc.map(compute_stats).getInfo()

        for feat in fc_stats["features"]:
            props = feat["properties"]
            all_mean_heights.append(props.get(f"{band_name}_mean", np.nan))
            all_std_heights.append(props.get(f"{band_name}_stdDev", np.nan))

        print(f"  ✅ Batch {start // batch_size + 1} processed ({start + 1}-{end})")

    # Append stats to dataframe
    result_df["canopy_height_mean"] = all_mean_heights
    result_df["canopy_height_std"] = all_std_heights


    return result_df, image
