from pathlib import Path
from typing import Optional, Union, Tuple, List
import logging

import ee
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.ticker import FuncFormatter
from shapely.geometry import Point
import contextily as ctx
from pyproj import Transformer

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


import pandas as pd
import logging
from typing import Tuple

# Assume logger and logging setup are configured elsewhere (as in your final code)
logger = logging.getLogger(__name__)


# =============================================================================
# RASTER PLOTTING
# =============================================================================

def _find_raster_files(raster_dir: str, pattern: str) -> List[Path]:
    """Find all raster files matching pattern in directory."""
    raster_path = Path(raster_dir)
    
    if not raster_path.exists():
        raise FileNotFoundError(f"Directory not found: {raster_dir}")
    
    raster_files = list(raster_path.glob(pattern))
    
    if not raster_files:
        logger.warning(f"No rasters found in {raster_dir} with pattern {pattern}")
        return []
    
    logger.info(f"Found {len(raster_files)} raster files")
    return raster_files


def _calculate_grid_layout(n_items: int, max_cols: int = 3) -> Tuple[int, int]:
    """Calculate optimal grid layout for subplots."""
    cols = min(max_cols, n_items)
    rows = (n_items + cols - 1) // cols
    return rows, cols


def _read_raster_data(raster_path: Path) -> Tuple[np.ndarray, dict]:
    """
    Read raster data and metadata.
    
    Args:
        raster_path: Path to raster file
        
    Returns:
        Tuple of (masked_data, metadata)
    """
    with rasterio.open(raster_path) as src:
        data = src.read(1)
        
        # Mask nodata values
        if src.nodata is not None:
            data = np.ma.masked_where(data == src.nodata, data)
        
        metadata = {
            'shape': src.shape,
            'crs': src.crs,
            'bounds': src.bounds,
            'nodata': src.nodata,
            'transform': src.transform
        }
        
        return data, metadata


def _setup_raster_axes(n_rasters: int, figsize_per_plot: Tuple[float, float] = (5, 4)):
    """Setup figure and axes for raster plotting."""
    rows, cols = _calculate_grid_layout(n_rasters)
    
    figsize = (figsize_per_plot[0] * cols, figsize_per_plot[1] * rows)
    fig, axes = plt.subplots(rows, cols, figsize=figsize)
    
    # Normalize axes to always be a flat array
    if n_rasters == 1:
        axes = np.array([axes])
    else:
        axes = np.atleast_1d(axes).flatten()
    
    return fig, axes, rows, cols


def plot_local_rasters(
    raster_dir: str = "output",
    pattern: str = "*.tif",
    cmap: str = "viridis",
    figsize_per_plot: Tuple[float, float] = (5, 4),
    max_cols: int = 3,
    colorbar_shrink: float = 0.6,
) -> Optional[Tuple[Figure, np.ndarray]]:
    """
    Load and plot all rasters from a directory.
    
    Args:
        raster_dir: Directory containing raster files
        pattern: Glob pattern for raster files
        cmap: Matplotlib colormap name
        figsize_per_plot: Size for each subplot (width, height)
        max_cols: Maximum number of columns in grid
        colorbar_shrink: Colorbar size factor
        
    Returns:
        Tuple of (figure, axes) or None if no rasters found
        
    Example:
        >>> fig, axes = plot_rasters(
        ...     raster_dir="output",
        ...     pattern="ndvi_*.tif",
        ...     cmap="RdYlGn"
        ... )
    """
    # Find raster files
    raster_files = _find_raster_files(raster_dir, pattern)
    
    if not raster_files:
        return None
    
    # Setup figure
    fig, axes, rows, cols = _setup_raster_axes(len(raster_files), figsize_per_plot)
    
    # Plot each raster
    for i, raster_file in enumerate(raster_files):
        try:
            data, metadata = _read_raster_data(raster_file)
            
            # Plot
            im = axes[i].imshow(data, cmap=cmap)
            axes[i].set_title(raster_file.stem, fontsize=10)
            axes[i].set_xlabel("X Pixels")
            axes[i].set_ylabel("Y Pixels")
            
            # Add colorbar
            plt.colorbar(im, ax=axes[i], shrink=colorbar_shrink)
            
            # Log info
            logger.info(
                f"Plotted {raster_file.name}: "
                f"{metadata['shape']} pixels, CRS: {metadata['crs']}"
            )
            
        except Exception as e:
            logger.error(f"Error plotting {raster_file}: {e}")
            axes[i].text(
                0.5, 0.5, f"Error loading\n{raster_file.name}",
                ha='center', va='center', transform=axes[i].transAxes
            )
    
    # Remove extra axes
    for j in range(len(raster_files), len(axes)):
        axes[j].remove()
    
    plt.tight_layout()
    
    return fig, axes


# =============================================================================
# MAP PLOTTING
# =============================================================================

def _ensure_geodataframe(
    data: Union[pd.DataFrame, gpd.GeoDataFrame],
    lat_col: str,
    lon_col: str
) -> gpd.GeoDataFrame:
    """
    Convert DataFrame to GeoDataFrame if needed.
    
    Args:
        data: Input data
        lat_col: Latitude column name
        lon_col: Longitude column name
        
    Returns:
        GeoDataFrame in EPSG:4326
    """
    if isinstance(data, gpd.GeoDataFrame):
        gdf = data.copy()
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)
        return gdf
    
    # Check for required columns
    if lat_col not in data.columns:
        raise ValueError(f"Latitude column '{lat_col}' not found in DataFrame")
    
    if lon_col not in data.columns:
        raise ValueError(f"Longitude column '{lon_col}' not found in DataFrame")
    
    # Create GeoDataFrame
    geometry = [Point(xy) for xy in zip(data[lon_col], data[lat_col])]
    gdf = gpd.GeoDataFrame(data.copy(), geometry=geometry, crs="EPSG:4326")
    
    return gdf


def _clean_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Remove invalid geometries."""
    valid_mask = gdf.geometry.notna() & gdf.is_valid
    gdf_clean = gdf[valid_mask].copy()
    
    removed_count = len(gdf) - len(gdf_clean)
    if removed_count > 0:
        logger.warning(f"Removed {removed_count} invalid geometries")
    
    if gdf_clean.empty:
        raise ValueError("No valid geometries remaining after cleaning")
    
    return gdf_clean


def _get_basemap_source(basemap: str):
    """
    Get contextily basemap source from name.
    
    Args:
        basemap: Basemap name ('terrain', 'positron', 'osm', etc.)
        
    Returns:
        Contextily provider or None
    """
    basemap_mapping = {
        'terrain': ['Stamen.Terrain', 'Esri.WorldTopoMap'],
        'positron': ['CartoDB.Positron'],
        'osm': ['OpenStreetMap.Mapnik'],
        'satellite': ['Esri.WorldImagery'],
        'dark': ['CartoDB.DarkMatter'],
    }
    
    providers_to_try = basemap_mapping.get(basemap.lower(), [basemap])
    
    for provider_path in providers_to_try:
        try:
            # Navigate provider hierarchy (e.g., "Stamen.Terrain")
            provider = ctx.providers
            for part in provider_path.split('.'):
                provider = getattr(provider, part)
            return provider
        except AttributeError:
            continue
    
    logger.warning(f"Could not find basemap provider for '{basemap}'")
    return None


def _add_basemap_to_axes(
    ax: Axes, 
    basemap: Optional[str],
    attribution: bool = False
) -> None:
    """
    Add basemap to axes if specified.
    
    Args:
        ax: Matplotlib axes
        basemap: Basemap name
        attribution: Show attribution text (default: False)
    """
    if not basemap:
        return
    
    source = _get_basemap_source(basemap)
    
    if source is not None:
        try:
            ctx.add_basemap(
                ax, 
                source=source,
                attribution=attribution  # Controla a legenda
            )
            logger.info(f"Added basemap: {basemap}")
        except Exception as e:
            logger.warning(f"Could not add basemap: {e}")


def _create_coordinate_formatters(
    ax: Axes
) -> Tuple[FuncFormatter, FuncFormatter]:
    """
    Create formatters for converting Web Mercator to lat/lon labels.
    
    Args:
        ax: Matplotlib axes
        
    Returns:
        Tuple of (lon_formatter, lat_formatter)
    """
    transformer = Transformer.from_crs(3857, 4326, always_xy=True)
    
    def lon_formatter(x, pos=None):
        """Format x-axis labels as longitude."""
        y_mid = 0.5 * sum(ax.get_ylim())
        lon, _ = transformer.transform(x, y_mid)
        return f"{lon:.3f}°"
    
    def lat_formatter(y, pos=None):
        """Format y-axis labels as latitude."""
        x_mid = 0.5 * sum(ax.get_xlim())
        _, lat = transformer.transform(x_mid, y)
        return f"{lat:.3f}°"
    
    return FuncFormatter(lon_formatter), FuncFormatter(lat_formatter)


def _configure_plot_styling(
    ax: Axes,
    gdf: gpd.GeoDataFrame,
    column: Optional[str],
    color: Optional[str],
    cmap: str,
    markersize: float,
    alpha: float
) -> dict:
    """
    Configure plot styling parameters.
    
    Args:
        ax: Matplotlib axes
        gdf: GeoDataFrame to plot
        column: Column to use for coloring
        color: Fixed color to use
        cmap: Colormap name
        markersize: Marker size for points
        alpha: Transparency
        
    Returns:
        Dictionary of plot kwargs
    """
    plot_kwargs = {'ax': ax, 'alpha': alpha}
    
    # Color by column
    if column is not None and column in gdf.columns:
        is_categorical = (
            gdf[column].dtype == "object" or 
            str(gdf[column].dtype).startswith("category")
        )
        
        plot_kwargs['column'] = column
        plot_kwargs['legend'] = True
        
        if not is_categorical:
            plot_kwargs['cmap'] = cmap
    
    # Fixed color
    elif color is not None:
        plot_kwargs['color'] = color
    
    # Point-specific styling
    is_point = gdf.geom_type.str.contains("Point").any()
    if is_point:
        plot_kwargs['markersize'] = markersize
    
    return plot_kwargs


def plot_map(
    data: Union[pd.DataFrame, gpd.GeoDataFrame],
    column: Optional[str] = None,
    color: Optional[str] = None,
    basemap: Optional[str] = "terrain",
    cmap: str = "viridis",
    markersize: float = 40,
    alpha: float = 0.8,
    figsize: Tuple[float, float] = (10, 7),
    title: Optional[str] = None,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    buffer_pct: float = 0.05,
    dpi: int = 110,
    attribution: bool = False,  # NOVO PARÂMETRO
) -> Tuple[Figure, Axes]:
    """
    Create map plot with optional basemap and colored points/polygons.
    
    Args:
        data: DataFrame or GeoDataFrame with spatial data
        column: Column to use for coloring (optional)
        color: Fixed color for all features (optional)
        basemap: Basemap style ('terrain', 'positron', 'osm', 'satellite', 'dark')
        cmap: Matplotlib colormap for numeric columns
        markersize: Size of point markers
        alpha: Transparency (0-1)
        figsize: Figure size (width, height)
        title: Plot title (auto-generated if None)
        lat_col: Latitude column name (for DataFrames)
        lon_col: Longitude column name (for DataFrames)
        buffer_pct: Extra space around features as percentage of extent
        dpi: Figure DPI
        attribution: Show basemap attribution text (default: False)
        
    Returns:
        Tuple of (figure, axes)
    """
    logger.info(f"Creating map plot for {len(data)} features...")
    
    # Ensure GeoDataFrame in WGS84
    gdf = _ensure_geodataframe(data, lat_col, lon_col)
    
    # Clean geometries
    gdf = _clean_geometries(gdf)
    
    # Reproject to Web Mercator for plotting
    gdf_plot = gdf.to_crs(3857)
    
    # Create figure
    plt.rcParams['figure.dpi'] = dpi
    fig, ax = plt.subplots(figsize=figsize)
    
    # Configure plot styling
    plot_kwargs = _configure_plot_styling(
        ax, gdf_plot, column, color, cmap, markersize, alpha
    )
    
    # Plot features
    try:
        gdf_plot.plot(**plot_kwargs)
    except Exception as e:
        logger.warning(f"Plot with full kwargs failed: {e}. Using simplified plot.")
        gdf_plot.plot(ax=ax, alpha=alpha, color=color or 'tab:blue')
    
    # Add basemap
    _add_basemap_to_axes(ax, basemap, attribution=attribution)  # Passa o parâmetro
    
    # Set bounds with buffer
    x0, y0, x1, y1 = gdf_plot.total_bounds
    dx, dy = (x1 - x0), (y1 - y0)
    ax.set_xlim(x0 - dx * buffer_pct, x1 + dx * buffer_pct)
    ax.set_ylim(y0 - dy * buffer_pct, y1 + dy * buffer_pct)
    
    # Configure coordinate formatters (Web Mercator -> Lat/Lon)
    lon_formatter, lat_formatter = _create_coordinate_formatters(ax)
    ax.xaxis.set_major_formatter(lon_formatter)
    ax.yaxis.set_major_formatter(lat_formatter)
    ax.set_xlabel("Longitude (°)")
    ax.set_ylabel("Latitude (°)")
    
    # Title and grid
    if title is None:
        if column is not None:
            title = f"Map of {column}"
        else:
            title = f"{len(gdf)} sampling sites"
    
    ax.set_title(title, fontsize=12, pad=10)
    ax.grid(True, alpha=0.25, linestyle='--')
    
    plt.tight_layout()
    
    logger.info("Map plot created successfully")
    
    return fig, ax



# =============================================================================
# EARTH ENGINE IMAGE VISUALIZATION
# =============================================================================



logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def _get_band_min_max(
    image: ee.Image,
    band: str,
    aoi: ee.Geometry,
    scale: int = 100
) -> Tuple[float, float]:
    """
    Calculate min and max values for an image band.
    
    Args:
        image: Earth Engine image
        band: Band name
        aoi: Area of interest
        scale: Scale for reduction in meters
        
    Returns:
        Tuple of (min_value, max_value)
    """
    band_image = image.select(band)
    if band == "NDVI":
        p = band_image.reduceRegion(
            reducer=ee.Reducer.percentile([2, 98]),
            geometry=aoi,
            scale=scale,
            maxPixels=1e13,
            bestEffort=True,
        )
        min_value = p.get("NDVI_p2").getInfo()
        max_value = p.get("NDVI_p98").getInfo()
        return min_value, max_value
    
    min_max = band_image.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=aoi,
        scale=scale,
        maxPixels=1e13,
        bestEffort=True,
    )
    
    min_value = min_max.get(f"{band}_min").getInfo()
    max_value = min_max.get(f"{band}_max").getInfo()
    
    return min_value, max_value


def plot_images(
    image: ee.Image,
    aoi: ee.Geometry,
    filter_bands: Optional[Union[str, List[str]]] = None,
    palette: Optional[List[str]] = None,
    scale: int = 100,
    zoom: int = 10,
) -> 'geemap.Map':
    """
    Plot Earth Engine image bands on an interactive geemap Map.
    
    Each band is plotted with its own color range based on min/max values
    within the area of interest.
    
    Args:
        image: Earth Engine image to plot
        aoi: Area of interest geometry
        filter_bands: Band name or list of band names to plot (default: all bands)
        palette: Color palette for visualization (default: blue-green-red)
        scale: Scale for min/max calculation in meters
        zoom: Initial zoom level for map
        
    Returns:
        geemap.Map object with image layers
        
    Raises:
        ImportError: If geemap is not installed
        ValueError: If no valid bands are found
        
    Example:
        >>> import ee
        >>> import geemap
        >>> 
        >>> # Load Landsat image
        >>> image = ee.Image("LANDSAT/LC09/C02/T1_L2/LC09_001004_20220127")
        >>> aoi = ee.Geometry.Rectangle([-47, -24, -46, -23])
        >>> 
        >>> # Plot all bands
        >>> m = plot_raster(image, aoi)
        >>> m
        >>> 
        >>> # Plot specific bands
        >>> m = plot_raster(image, aoi, filter_bands=['SR_B4', 'SR_B5'])
        >>> 
        >>> # Custom palette
        >>> m = plot_raster(
        ...     image, aoi, 
        ...     filter_bands='NDVI',
        ...     palette=['red', 'yellow', 'green']
        ... )
    """
    try:
        import geemap
    except ImportError:
        raise ImportError(
            "geemap is required for this function. "
            "Install with: pip install geemap"
        )
    
    # Default palette
    if palette is None:
        palette = ["blue", "green", "red"]
    
    # Clip image to AOI
    image = image.clip(aoi)
    
    # Get available bands
    available_bands = image.bandNames().getInfo()
    logger.info(f"Available bands in image: {', '.join(available_bands)}")
    
    # Determine bands to plot
    if filter_bands is None:
        band_names = available_bands
    elif isinstance(filter_bands, str):
        band_names = [filter_bands]
    else:
        band_names = list(filter_bands)
    
    # Validate bands
    valid_bands = []
    for band in band_names:
        if band not in available_bands:
            logger.warning(f"Band '{band}' not found in image and will be skipped")
        else:
            valid_bands.append(band)
    
    if not valid_bands:
        raise ValueError(
            f"No valid bands found. Available bands: {available_bands}"
        )
    
    logger.info(f"Plotting {len(valid_bands)} bands: {', '.join(valid_bands)}")
    
    # Create map
    map_object = geemap.Map()
    map_object.centerObject(aoi, zoom)
    
    # Add each band to map
    for band in valid_bands:
        try:
            # Calculate min/max for band
            min_value, max_value = _get_band_min_max(image, band, aoi, scale)
            
            logger.info(
                f"Band '{band}': min={min_value:.4f}, max={max_value:.4f}"
            )
            
            # Create visualization parameters
            vis_params = {
                "min": min_value,
                "max": max_value,
                "palette": palette,
            }
            
            # Add layer to map
            map_object.addLayer(image.select(band), vis_params, band)
            
        except Exception as e:
            logger.error(f"Error plotting band '{band}': {e}")
    
    # Add layer controls
    map_object.addLayerControl()
    
    logger.info("Map created successfully")
    
    return map_object