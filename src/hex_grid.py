from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Polygon, shape
import ee
import h3
import geemap
from tqdm.auto import tqdm

def generate_h3_hexagons(
    aoi: ee.Geometry,
    h3_resolution: int = 9,
    calculate_area: bool = True,
) -> gpd.GeoDataFrame:
    """
    Generate an H3 hexagon grid INSIDE an Earth Engine AOI (ee.Geometry).

    Parameters
    ----------
    aoi : ee.Geometry
        AOI geometry (Polygon or MultiPolygon) in lon/lat.
        Note: this function pulls geometry client-side via .getInfo().
    h3_resolution : int
        H3 resolution (e.g., 9 ~ 183m of Approximate Radius).
    add_h3_id : bool
        Whether to add the H3 cell id as a column.
    calculate_area : bool
        Whether to calculate polygon area (requires projecting; see comment).

    Returns
    -------
    geopandas.GeoDataFrame
        GeoDataFrame (EPSG:4326) with hexagon polygons (and optional h3_id/area).
    """
    if aoi is None:
        raise ValueError("You must provide 'aoi' as an ee.Geometry.")

    aoi_geom = shape(aoi.getInfo())
    if aoi_geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("AOI must be a Polygon or MultiPolygon ee.Geometry.")

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

    hex_gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

    hex_gdf = hex_gdf[hex_gdf.intersects(aoi_geom)].copy()

    if calculate_area:
        hex_gdf["hexagon_area_km2"] = hex_gdf["h3_id"].apply(
            lambda h: h3.cell_area(h, unit='km^2')
        )
        hex_gdf["hexagon_area_m2"] = hex_gdf["hexagon_area_km2"] * 1_000_000

    return hex_gdf

def extract_h3_values(
    hex_gdf: gpd.GeoDataFrame,
    image_dict: dict = None,
    image_stack: ee.Image = None,
    default_scale: int = 100,
    default_reducer: str = 'median',
    batch_size: int = 500,
    tileScale: int = 16,
) -> gpd.GeoDataFrame:
    """
    Extract values from Earth Engine images for H3 hexagon grid.
    
    This function extracts statistical summaries (median, mean, etc.) from Earth Engine images
    for each hexagon in a GeoDataFrame.
    
    Parameters
    ----------
    hex_gdf : gpd.GeoDataFrame
        GeoDataFrame containing hexagon geometries (EPSG:4326).
        Each hexagon will get extracted values added as new columns.
    
    image_dict : dict, optional
        Dictionary mapping band names to (ee.Image, scale, reducer) tuples.
        The reducer parameter is optional - if not provided, uses default_reducer.
        Each image must have exactly ONE band.
        
        Example formats:
        - With custom reducer per band:
          {
              'ndvi': (image_ndvi, 30, 'median'),
              'landcover': (image_landcover, 10, 'mode'),
              'elevation': (image_elevation, 30, 'mean')
          }
        
        - Without custom reducer (uses default_reducer):
          {
              'ndvi': (image_ndvi, 30),
              'elevation': (image_elevation, 30)
          }
        
        - Mixed (some with, some without):
          {
              'ndvi': (image_ndvi, 30),  # Uses default_reducer
              'landcover': (image_landcover, 10, 'mode')  # Uses 'mode'
          }
        
        Cannot be used together with image_stack.
    
    image_stack : ee.Image, optional
        Multi-band Earth Engine image. All bands will be processed at default_scale
        and default_reducer. Cannot be used together with image_dict.
    
    default_scale : int, default=100
        Scale in meters to use when image_stack is provided or when scale is not
        specified in image_dict.
    
    default_reducer : str, default='median'
        Aggregation method to use by default.
        Options: 'mean', 'median', 'min', 'max', 'mode'
        Used when:
        - image_stack is provided (applies to all bands)
        - image_dict entries don't specify a reducer
    
    batch_size : int, default=5000
        Number of hexagons to process per batch.
        Adjust based on:
        - Smaller hexagons → use smaller batch_size (e.g., 1000-2000)
        - Larger hexagons → use larger batch_size (e.g., 5000-10000)
        - Many bands → use smaller batch_size (e.g., 500-1000)
    
    tileScale : int, default=16
        Earth Engine tile scale for processing.
        Higher values = faster but more memory usage.
        Range: 1 (slow, low memory) to 16 (fast, high memory)
        Reduce if getting "memory limit exceeded" errors.
    
    Returns
    -------
    gpd.GeoDataFrame
        Input GeoDataFrame with new columns for each band containing extracted values.
        Original columns and geometries are preserved.
    
    Examples
    --------
    Example 1: Custom reducer per band (continuous vs categorical data)
    
    >>> image_dict = {
    ...     'ndvi': (image_ndvi, 30, 'median'),           # Continuous
    ...     'elevation': (image_elevation, 30, 'mean'),    # Continuous
    ...     'landcover': (image_landcover, 10, 'mode'),    # Categorical
    ...     'soil_type': (image_soil, 250, 'mode')        # Categorical
    ... }
    >>> 
    >>> result = extract_h3_values(
    ...     hex_gdf=hexagons,
    ...     image_dict=image_dict,
    ...     batch_size=5000
    ... )
    
    Example 2: Mixed - some with custom reducer, some with default
    
    >>> image_dict = {
    ...     'ndvi': (image_ndvi, 30),                      # Uses default_reducer
    ...     'landcover': (image_landcover, 10, 'mode'),    # Uses 'mode'
    ...     'elevation': (image_elevation, 30)             # Uses default_reducer
    ... }
    >>> 
    >>> result = extract_h3_values(
    ...     hex_gdf=hexagons,
    ...     image_dict=image_dict,
    ...     default_reducer='median',  # Applied to ndvi and elevation
    ...     batch_size=5000
    ... )
    
    Example 3: Using image_stack with single reducer
    
    >>> image_stack = ee.Image.cat([
    ...     image_ndvi,
    ...     image_elevation
    ... ])
    >>> 
    >>> result = extract_h3_values(
    ...     hex_gdf=hexagons,
    ...     image_stack=image_stack,
    ...     default_scale=100,
    ...     default_reducer='mean'  # Applied to all bands
    ... )
    """
    from tqdm.auto import tqdm
    
    # Validate inputs
    if image_dict is None and image_stack is None:
        raise ValueError("Must provide either 'image_dict' or 'image_stack'")
    
    if image_dict is not None and image_stack is not None:
        raise ValueError("Provide only one: 'image_dict' OR 'image_stack'")
    
    # Setup reducer dictionary
    reducer_dict = {
        'mean': ee.Reducer.mean(),
        'median': ee.Reducer.median(),
        'min': ee.Reducer.min(),
        'max': ee.Reducer.max(),
        'mode': ee.Reducer.mode()
    }
    
    if default_reducer not in reducer_dict:
        raise ValueError(f"default_reducer must be one of {list(reducer_dict.keys())}")
    
    # Setup band configuration and group by (scale, reducer)
    scale_reducer_groups = {}  # {(scale, reducer): [band_names]}
    band_to_image = {}
    band_to_reducer = {}
    
    if image_dict is not None:
        print("Using custom scales per band...")
        print("Validating images...")
        
        for band_name, band_config in image_dict.items():
            # Parse config tuple - supports 2 or 3 elements
            if len(band_config) == 2:
                img, scale = band_config
                reducer = default_reducer  # Use default if not specified
            elif len(band_config) == 3:
                img, scale, reducer = band_config
            else:
                raise ValueError(
                    f"Invalid config for '{band_name}': expected (image, scale) or "
                    f"(image, scale, reducer), got {len(band_config)} elements"
                )
            
            # Validate reducer
            if reducer not in reducer_dict:
                raise ValueError(
                    f"Invalid reducer '{reducer}' for band '{band_name}'. "
                    f"Must be one of {list(reducer_dict.keys())}"
                )
            
            # Validate image bands
            img_bands = img.bandNames().getInfo()
            n_bands = len(img_bands)
            
            if n_bands == 0:
                raise ValueError(f"Image for '{band_name}' has no bands!")
            elif n_bands > 1:
                print(f"  ⚠️  '{band_name}' has {n_bands} bands: {img_bands}")
                print(f"      Selecting first band: '{img_bands[0]}'")
                img = img.select(img_bands[0])
                selected_band = img_bands[0]
            else:
                selected_band = img_bands[0]
            
            # Group by (scale, reducer) for efficient processing
            group_key = (scale, reducer)
            if group_key not in scale_reducer_groups:
                scale_reducer_groups[group_key] = []
            scale_reducer_groups[group_key].append(band_name)
            
            band_to_image[band_name] = img
            band_to_reducer[band_name] = reducer
            
            print(f"  ✓ {band_name}: {scale}m, {reducer} - band: {selected_band}")
            
    else:
        print(f"Using default scale ({default_scale}) and reducer ({default_reducer}) for all bands...")
        band_names = image_stack.bandNames().getInfo()
        group_key = (default_scale, default_reducer)
        scale_reducer_groups[group_key] = band_names
        
        for band in band_names:
            band_to_image[band] = image_stack.select(band)
            band_to_reducer[band] = default_reducer
        
        print(f"  Found {len(band_names)} bands: {band_names}")
    
    # Initialize all columns
    all_bands = list(band_to_image.keys())
    for band in all_bands:
        hex_gdf[band] = None
    
    n_hexagons = len(hex_gdf)
    
    print(f"\nTotal hexagons to process: {n_hexagons}")
    print(f"Scale-Reducer groups: {[((scale, reducer), len(bands)) for (scale, reducer), bands in scale_reducer_groups.items()]}")
    
    # Create progress bars for each band
    band_progress = {band: tqdm(
        total=n_hexagons,
        desc=f"{band}",
        unit="hex",
        position=i,
        leave=True
    ) for i, band in enumerate(all_bands)}
    
    # Process in batches
    for start_idx in range(0, n_hexagons, batch_size):
        end_idx = min(start_idx + batch_size, n_hexagons)
        batch_gdf = hex_gdf.iloc[start_idx:end_idx].copy()
        batch_size_actual = len(batch_gdf)
        
        # Use geemap for faster conversion (20-40x speedup)
        batch_gdf['batch_idx'] = range(len(batch_gdf))
        batch_fc = geemap.geopandas_to_ee(batch_gdf, geodesic=False)
        
        # Process by (scale, reducer) groups
        for (scale, reducer), band_list in scale_reducer_groups.items():
            # Create image stack for this group
            images_for_scale = [band_to_image[band] for band in band_list]
            
            scale_stack = ee.Image.cat(images_for_scale)
            scale_stack = scale_stack.rename(band_list)
            
            # Get appropriate reducer
            ee_reducer = reducer_dict[reducer]
            
            # Use setOutputs for single band to preserve band name
            if len(band_list) == 1:
                scale_reducer = ee_reducer.setOutputs(band_list)
            else:
                scale_reducer = ee_reducer
            
            # Extract values
            sampled_fc = scale_stack.reduceRegions(
                collection=batch_fc,
                reducer=scale_reducer,
                scale=scale,
                crs='EPSG:4326',
                tileScale=tileScale
            )
            
            sampled_info = sampled_fc.getInfo()
            
            # Parse results for all bands in this group
            for band in band_list:
                values = [None] * len(batch_gdf)
                values_extracted = 0
                
                for feature in sampled_info['features']:
                    batch_idx = feature['properties'].get('batch_idx')
                    properties = feature['properties']
                    
                    if batch_idx is not None and band in properties:
                        values[batch_idx] = properties[band]
                        values_extracted += 1
                
                hex_gdf.loc[start_idx:end_idx-1, band] = values
                
                # Update progress bar
                band_progress[band].update(batch_size_actual)
                band_progress[band].set_postfix({
                    'extracted': f'{values_extracted}/{batch_size_actual}',
                    'reducer': reducer
                })
    
    # Close all progress bars
    for pbar in band_progress.values():
        pbar.close()
    
    print(f"\n{'='*60}")
    print("✓ ALL DONE!")
    print(f"{'='*60}")
    
    # Final check
    print("\nFinal check:")
    for band in all_bands:
        non_null = hex_gdf[band].notna().sum()
        reducer_used = band_to_reducer[band]
        print(f"  {band} ({reducer_used}): {non_null}/{len(hex_gdf)} non-null values")
    
    # Clean up temporary column
    hex_gdf = hex_gdf.drop(columns=['batch_idx'], errors='ignore')
    
    return hex_gdf