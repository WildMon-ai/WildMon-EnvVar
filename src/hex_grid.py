from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Polygon, shape
import ee
import h3
import geemap
import pandas as pd
from typing import List
from tqdm.auto import tqdm
from variables.landcover import LANDCOVER_CLASSES


BAND_CONFIG = {
    "biointactness": {"scale": 100, "reducer": "mean"},
    "agb": {"scale": 100, "reducers": ["mean", "min", "max", "stdDev"]},
    "canopy_height": {"scale": 10, "reducers": ["mean", "max", "min", "stdDev", "count"]},
    "elevation": {"scale": 30, "reducer": "mean"},
    "slope_percent": {"scale": 30, "reducer": "mean"},
    "land_cover": {"scale": 10, "reducer": "mode"},
    "ndvi": {"scale": 30, "reducer": "mean"},
    "nighttime_lights": {"scale": 464, "reducer": "mean"},
    "water_mask": {"scale": 30, "reducer": "mode"},
    "distance_to_water_m": {"scale": 30, "reducer": "mean"},
    "bio01": {"scale": 1000, "reducer": "mean"},
    "bio02": {"scale": 1000, "reducer": "mean"},
    "bio03": {"scale": 1000, "reducer": "mean"},
    "bio04": {"scale": 1000, "reducer": "mean"},
    "bio05": {"scale": 1000, "reducer": "mean"},
    "bio06": {"scale": 1000, "reducer": "mean"},
    "bio07": {"scale": 1000, "reducer": "mean"},
    "bio08": {"scale": 1000, "reducer": "mean"},
    "bio09": {"scale": 1000, "reducer": "mean"},
    "bio10": {"scale": 1000, "reducer": "mean"},
    "bio11": {"scale": 1000, "reducer": "mean"},
    "bio12": {"scale": 1000, "reducer": "mean"},
    "bio13": {"scale": 1000, "reducer": "mean"},
    "bio14": {"scale": 1000, "reducer": "mean"},
    "bio15": {"scale": 1000, "reducer": "mean"},
    "bio16": {"scale": 1000, "reducer": "mean"},
    "bio17": {"scale": 1000, "reducer": "mean"},
    "bio18": {"scale": 1000, "reducer": "mean"},
    "bio19": {"scale": 1000, "reducer": "mean"},
}

def _build_reducer_dict() -> dict[str, ee.Reducer]:
    """Return the supported EE reducers keyed by name."""
    return {
        'mean': ee.Reducer.mean(),
        'median': ee.Reducer.median(),
        'min': ee.Reducer.min(),
        'max': ee.Reducer.max(),
        'mode': ee.Reducer.mode(),
        'stdDev': ee.Reducer.stdDev(),
        'count': ee.Reducer.count(),
    }


def _build_combined_reducer(reducers: list[str], reducer_dict: dict[str, ee.Reducer]) -> ee.Reducer:
    """Combine multiple reducers with shared inputs."""
    combined = reducer_dict[reducers[0]]
    for r in reducers[1:]:
        combined = combined.combine(reducer2=reducer_dict[r], sharedInputs=True)
    return combined

def _configure_from_image_stack(
    image_stack: ee.Image,
    default_scale: int,
    default_reducer: str,
    reducer_dict: dict[str, ee.Reducer],
):
    """
    Configure the scale and reducer for each band in an image stack based on BAND_CONFIG and defaults.

    Bands with a single "reducer" key are grouped together by (scale, reducer) for efficiency.
    Bands with a "reducers" list get their own group with a combined EE reducer; their output
    columns are named {band}_{reducer} (e.g. canopy_height_mean, canopy_height_stdDev).

    Returns:
    - scale_reducer_groups: dict[tuple, list[str]] — bands grouped by (scale, reducer_key).
    - band_to_image: dict[str, ee.Image]
    - band_to_reducer: dict[str, str] — human-readable reducer label per band.
    - band_to_output_cols: dict[str, list[str]] — output column names per band.
    - group_to_ee_reducer: dict[tuple, ee.Reducer] — EE reducer per group key.
    """
    band_names = image_stack.bandNames().getInfo()
    print(f"Using image_stack with BAND_CONFIG/defaults for {len(band_names)} bands...")

    scale_reducer_groups = {}
    band_to_image = {}
    band_to_reducer = {}
    band_to_output_cols = {}
    group_to_ee_reducer = {}

    for band in band_names:
        band_defaults = BAND_CONFIG.get(band, {})
        scale = band_defaults.get("scale", default_scale)

        if "reducers" in band_defaults:
            reducers = band_defaults["reducers"]
            for r in reducers:
                if r not in reducer_dict:
                    raise ValueError(
                        f"Invalid reducer '{r}' for band '{band}'. "
                        f"Must be one of {list(reducer_dict.keys())}"
                    )
            group_key = (scale, f"multi_{band}")
            ee_reducer = _build_combined_reducer(reducers, reducer_dict)
            output_cols = [f"{band}_{r}" for r in reducers]
            reducer_label = "+".join(reducers)
        else:
            reducer = band_defaults.get("reducer", default_reducer)
            if reducer not in reducer_dict:
                raise ValueError(
                    f"Invalid reducer '{reducer}' for band '{band}'. "
                    f"Must be one of {list(reducer_dict.keys())}"
                )
            group_key = (scale, reducer)
            ee_reducer = reducer_dict[reducer]
            output_cols = [band]
            reducer_label = reducer

        if group_key not in scale_reducer_groups:
            scale_reducer_groups[group_key] = []
            group_to_ee_reducer[group_key] = ee_reducer
        scale_reducer_groups[group_key].append(band)

        band_to_image[band] = image_stack.select(band)
        band_to_reducer[band] = reducer_label
        band_to_output_cols[band] = output_cols

        print(f"  ✓ {band}: {scale}m, {reducer_label}")

    return scale_reducer_groups, band_to_image, band_to_reducer, band_to_output_cols, group_to_ee_reducer

def _log_scale_reducer_groups(
    scale_reducer_groups: dict[tuple[int, str], List[str]]
) -> None:
    """
    Print the scale/reducer groups and their bands for transparency.
    It will print the scale, reducer, the number and which bands are included in each group.

    Parameters:
    - scale_reducer_groups: dict[tuple[int, str], List[str]], A dictionary where each key is a tuple of (scale, reducer) and each value is a list of bands that should be grouped together for reduction.

    Returns:
    - None
    """
    print("Scale/Reducer groups:")
    for (scale, reducer), bands in scale_reducer_groups.items():
        print(f"  - {scale}m/{reducer}: {len(bands)} band(s) {bands}")

def _postprocess_results(df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Postprocess a GeoDataFrame of results by rounding numeric columns to 3 decimal places,
    replacing land cover codes with class labels, and computing derived canopy height stats
    (CV and 95% CI) from the extracted mean/stdDev/count columns.
    """
    non_geom_cols = df.columns.drop(df.geometry.name)

    for col in non_geom_cols:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().any():
            df[col] = converted.round(3)

    if 'land_cover' in df.columns:
        df['land_cover'] = df['land_cover'].astype(int).map(LANDCOVER_CLASSES)

    # Derived canopy height stats
    if {"canopy_height_mean", "canopy_height_stdDev", "canopy_height_count"}.issubset(df.columns):
        df["canopy_height_cv"] = (
            df["canopy_height_stdDev"] / df["canopy_height_mean"].replace(0, float("nan"))
        ).fillna(0).round(3)
        df["canopy_height_ci"] = (
            1.96 * df["canopy_height_stdDev"] / df["canopy_height_count"].pow(0.5)
        ).round(3)
        df = df.drop(columns=["canopy_height_count"])

    return df

def generate_h3_hexagon_grid(
    aoi: ee.Geometry,
    h3_resolution: int = 9,
    calculate_area: bool = True,
    crs: str = "EPSG:4326",
) -> gpd.GeoDataFrame:
    """
    Generate a GeoDataFrame of hexagons covering an AOI using the H3 library.
    https://h3geo.org/docs/core-library/restable

    Parameters:
    - aoi: ee.Geometry, The area of interest (AOI) to generate hexagons within.
    - h3_resolution: int, The resolution to use for the H3 hexagons. Default is 9 (~200m apothem).
    - calculate_area: bool, Whether to calculate the area of each hexagon in km^2 and m^2. Default is True.

    Returns:
    - gpd.GeoDataFrame, A GeoDataFrame containing the hexagon geometries and their H3 IDs. If calculate_area is True, it also contains the hexagon area in km^2 and m^2.
    """
    def validate_aoi(aoi):
        """
        Validate an area of interest (AOI) to ensure it is a valid
        Returns:
        - ee.Geometry, The validated AOI in shapely format.
        """
        if aoi is None:
            raise ValueError("You must provide 'aoi' as an ee.Geometry.")
        aoi_geom = shape(aoi.getInfo())
        if aoi_geom.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("AOI must be a Polygon or MultiPolygon ee.Geometry.")
        
        return aoi_geom
    
    aoi_geom = validate_aoi(aoi)

    h3_aoi = h3.geo_to_h3shape(aoi_geom.__geo_interface__)

    hex_ids = list(
        h3.polygon_to_cells(h3_aoi,
            res=h3_resolution
        )
    )

    # invert lat long
    hex_geoms = []
    for h in hex_ids:
        boundary = h3.cell_to_boundary(h)  # e.g. [(lat, lon), (lat, lon), ...]
        boundary_lonlat = [(lon, lat) for lat, lon in boundary]
        hex_geoms.append(Polygon(boundary_lonlat))

    data = {"geometry": hex_geoms}
    data["h3_id"] = list(hex_ids)

    hex_gdf = gpd.GeoDataFrame(data, crs=crs)

    hex_gdf = hex_gdf[hex_gdf.intersects(aoi_geom)].copy()

    if calculate_area:
        hex_gdf["hexagon_area_km2"] = hex_gdf["h3_id"].apply(
            lambda h: h3.cell_area(h, unit='km^2')
        )
        hex_gdf["hexagon_area_m2"] = hex_gdf["hexagon_area_km2"] * 1_000_000
    
    print(f"Generated {len(hex_gdf)} hexagons")

    return hex_gdf

def extract_values_from_hexagons(
    hex_gdf: gpd.GeoDataFrame,
    image_stack: ee.Image,
    default_scale: int = 100,
    default_reducer: str = 'mean',
    batch_size: int = 100,
    tileScale: int = 4,
) -> gpd.GeoDataFrame:
    
    """
    Extracts raster image values for a given GeoDataFrame of hexagons grids. The extraction
    is done by sampling the statistics (mean, median, etc...) of a given image stack considering 
    the pixels inside the area of each hexagon.

    The function aggregates images that share the same scale and reducer and processes them
    in batches.

    The function is optimized for performance by processing the hexagons in
    batches and using parallel processing when available.

    Parameters:
    - hex_gdf: gpd.GeoDataFrame, The GeoDataFrame containing the hexagons to sample.
    - image_stack: ee.Image, The image stack to sample from.
    - default_scale: int, The default scale to use for sampling. Default is 100.
    - default_reducer: str, The default reducer to use for reducing the sampled values. Default is 'mean'.
    - batch_size: int, The number of hexagons to process in each batch. Default is 100.
    - tileScale: int, The tile scale to use for the sampling. Default is 4. Increase up to 16 if having memory issues.

    Returns:
    - gpd.GeoDataFrame, A GeoDataFrame containing the sampled and reduced values for each band in the image stack.
    """
    reducer_dict = _build_reducer_dict()
    if default_reducer not in reducer_dict:
        raise ValueError(f"default_reducer must be one of {list(reducer_dict.keys())}")

    scale_reducer_groups, band_to_image, band_to_reducer, band_to_output_cols, group_to_ee_reducer = (
        _configure_from_image_stack(image_stack, default_scale, default_reducer, reducer_dict)
    )

    all_bands = list(band_to_image.keys())
    all_output_cols = [col for band in all_bands for col in band_to_output_cols[band]]
    for col in all_output_cols:
        hex_gdf[col] = None

    n_hexagons = len(hex_gdf)

    print(f"\nTotal hexagons to process: {n_hexagons}")
    _log_scale_reducer_groups(scale_reducer_groups)

    col_progress = {col: tqdm(
        total=n_hexagons,
        desc=col,
        unit="hex",
        position=i,
        leave=True,
    ) for i, col in enumerate(all_output_cols)}

    for start_idx in range(0, n_hexagons, batch_size):
        end_idx = min(start_idx + batch_size, n_hexagons)
        batch_gdf = hex_gdf.iloc[start_idx:end_idx].copy()
        batch_size_actual = len(batch_gdf)

        batch_gdf['batch_idx'] = range(len(batch_gdf))
        batch_fc = geemap.geopandas_to_ee(batch_gdf, geodesic=False)

        for group_key, band_list in scale_reducer_groups.items():
            scale = group_key[0]
            images_for_group = [band_to_image[band] for band in band_list]

            scale_stack = ee.Image.cat(images_for_group)
            scale_stack = scale_stack.rename(band_list)

            ee_reducer = group_to_ee_reducer[group_key]
            # For single-band single-reducer groups, name the output after the band
            is_single_band_single_reducer = (
                len(band_list) == 1 and len(band_to_output_cols[band_list[0]]) == 1
            )
            if is_single_band_single_reducer:
                ee_reducer = ee_reducer.setOutputs(band_list)

            sampled_fc = scale_stack.reduceRegions(
                collection=batch_fc,
                reducer=ee_reducer,
                scale=scale,
                tileScale=tileScale,
            )

            sampled_gdf = geemap.ee_to_gdf(sampled_fc)
            sampled_gdf = sampled_gdf.drop(columns=['geometry'], errors='ignore')

            if not sampled_gdf.empty and 'batch_idx' in sampled_gdf.columns:
                sampled_gdf = sampled_gdf.set_index('batch_idx')

            for band in band_list:
                for col in band_to_output_cols[band]:
                    if sampled_gdf.empty or col not in sampled_gdf.columns:
                        values = [None] * batch_size_actual
                        values_extracted = 0
                    else:
                        col_series = sampled_gdf[col].reindex(range(batch_size_actual))
                        values = col_series.tolist()
                        values_extracted = col_series.notna().sum()

                    hex_gdf.loc[start_idx:end_idx - 1, col] = values

                    col_progress[col].update(batch_size_actual)
                    col_progress[col].set_postfix({'extracted': f'{values_extracted}/{batch_size_actual}'})

    for pbar in col_progress.values():
        pbar.close()

    print(f"\n{'='*60}")
    print("✓ ALL DONE!")
    print(f"{'='*60}")

    print("\nFinal check:")
    for band in all_bands:
        reducer_used = band_to_reducer[band]
        for col in band_to_output_cols[band]:
            non_null = hex_gdf[col].notna().sum()
            print(f"  {col} ({reducer_used}): {non_null}/{len(hex_gdf)} non-null values")

    hex_gdf = hex_gdf.drop(columns=['batch_idx'], errors='ignore')
    hex_gdf = _postprocess_results(hex_gdf)

    return hex_gdf