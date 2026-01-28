# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**WildMon EnvVars** is a Python pipeline for extracting environmental covariates around point locations using Google Earth Engine (GEE). It generates ready-to-use environmental variables for biodiversity monitoring, ecological analyses, and species distribution modeling (SDMs).

**Technology Stack:**
- Python 3.12+ with `uv` package manager
- Google Earth Engine (earthengine-api 1.6.2)
- Geospatial: geopandas, rasterio, geemap, h3, shapely
- Data science: pandas 2.3.1, numpy 2.3.2

## Development Commands

### Environment Setup
```bash
# Install dependencies
uv sync

# Authenticate with Google Cloud/Earth Engine
gcloud auth application-default login
gcloud config set project <your-gcp-project-id>

# Install Jupyter kernel (one-time)
uv run python -m ipykernel install --user --name ds-gis-pipeline
```

### Running the Pipeline
```bash
# Basic site-level extraction
uv run python src/cli.py --config config.toml

# With optional outputs (computationally expensive)
uv run python src/cli.py --config config.toml --export-raw-rasters --export-hexa-grid

# Launch Jupyter notebook for interactive development
uv run jupyter notebook pipeline.ipynb
```

### Managing Dependencies
```bash
# Add a new package
uv add <package-name>

# Remove a package
uv remove <package-name>

# Update dependencies
uv sync
```

## Architecture

### Pipeline Orchestration Flow

The [src/cli.py](src/cli.py) module orchestrates the entire extraction workflow:

1. **Configuration** → Load and validate [config.toml](config.toml)
2. **Authentication** → Initialize GEE via [auth.py](src/auth.py)
3. **Data Loading** → Read input CSV with coordinates
4. **Coordinate Cleaning** → Validate lat/lon in [sampling.py](src/sampling.py)
5. **AOI Creation** → Generate Area of Interest from point extent + buffer in [aoi.py](src/aoi.py)
6. **Point Buffering** → Create buffered geometries for sampling (default 200m for PAM devices)
7. **Variable Extraction** → Sequential execution of enabled extractors from [src/variables/](src/variables/)
8. **Export** → Output CSV, optional rasters (GeoTIFF to Google Drive), optional H3 hexgrid

### Modular Variable Extractor Pattern

Each environmental variable module in [src/variables/](src/variables/) follows a consistent pattern:

```python
def extract_{variable}(
    df: pd.DataFrame,                          # Input dataframe
    aoi: ee.Geometry,                          # Area of Interest
    points_feature_collection: ee.FeatureCollection,  # Buffered points
    **kwargs                                   # Variable-specific parameters
) -> Tuple[pd.DataFrame, ee.Image]:
    """
    Returns:
        - Updated dataframe with new columns ({variable}_mean, {variable}_std)
        - Earth Engine image used for extraction
    """
```

**Common operations within extractors:**
1. Load dataset from GEE catalog
2. Apply masks (cloud, water), scaling, projections
3. Clip to AOI
4. Extract statistics for buffered points using `reduceRegion`
5. Merge results into dataframe via index-based joins
6. Log summary statistics

**Reference implementation:** [src/variables/canopy_height.py](src/variables/canopy_height.py) demonstrates the simplest extractor pattern.

### Key Architectural Components

**[src/sampling.py](src/sampling.py):**
- `clean_coordinates_dataframe()` - Validates lat/lon columns
- `convert_points_to_buffered_features()` - Creates ee.FeatureCollection with buffered geometries
- `build_variable_extractor()` - Generic reducer builder for mean/stdDev statistics
- `merge_ee_sampling_results()` - Merges GEE results back into pandas DataFrame

**[src/aoi.py](src/aoi.py):**
- `create_aoi_from_coordinates()` - Builds bounding box from points + configurable buffer

**[src/hex_grid.py](src/hex_grid.py):**
- `generate_h3_hexagon_grid()` - Creates H3 hexagonal grid covering AOI
- `extract_values_from_hexagons()` - Batch processes hexagons to extract variable statistics

**[src/export.py](src/export.py):**
- `export_csv()` - Saves site-level results
- `export_rasters_to_gdrive()` - Exports GeoTIFFs per band to Google Drive
- `export_hexagrid_results()` - Saves hexgrid in SHP, GPKG, CSV formats
- `export_aoi_geojson()` - Exports AOI boundary as GeoJSON

### Available Environmental Variables (29 total)

Variables are toggled via `[VARIABLES_ENABLED]` table in [config.toml](config.toml):

| Variable Group | Bands | Scale | Module |
|---|---|---|---|
| NDVI (Landsat 9) | ndvi | 30m | [ndvi.py](src/variables/ndvi.py) |
| Canopy Height (ETH 2020) | canopy_height | 10m | [canopy_height.py](src/variables/canopy_height.py) |
| Land Cover (ESA WorldCover) | landcover (mode + proportions) | 10m | [landcover.py](src/variables/landcover.py) |
| WorldClim Bioclimate | bio01-bio19 (19 vars) | 1km | [worldclim.py](src/variables/worldclim.py) |
| Distance to Water | distance_to_water_m | 30m | [waterdist.py](src/variables/waterdist.py) |
| Above-ground Biomass (ESA CCI) | agb | 100m | [biomass.py](src/variables/biomass.py) |
| Nighttime Lights (VIIRS) | nighttime_lights | 464m | [nighttime_lights.py](src/variables/nighttime_lights.py) |
| Elevation & Slope (Copernicus) | elevation, slope_percent | 30m | [elevation.py](src/variables/elevation.py) |
| Biodiversity Intactness Index | biointactness | 100m | [bii.py](src/variables/bii.py) |
| Satellite Embeddings (Google) | 64 bands | 10m | [satellite_embedding.py](src/variables/satellite_embedding.py) |
| Ecosystem Integrity Index | eii (in development) | TBD | [eii.py](src/variables/eii.py) |

**Note:** Satellite embeddings are excluded from raster/hexgrid exports by default due to 64-band size.

### Configuration-Driven Design

All pipeline parameters are controlled via [config.toml](config.toml):

**Critical parameters:**
- `GEE_PROJECT_ID` - GCP project with Earth Engine enabled
- `LOCATIONS_CSV_PATH` - Input CSV with lat/lon columns
- `SAMPLING_POINT_BUFFER_METERS` - Buffer radius for statistics (default: 200m)
- `AOI_BUFFER_KM` - Margin around points for AOI boundary (default: 30km)
- `IMAGE_START_DATE` / `IMAGE_END_DATE` - Temporal window for temporal datasets
- `HEXAGRID_RESOLUTION` - H3 resolution level (0-15, default: 5 ≈ 253km²)
- `MAX_SEARCH_DISTANCE_M_WATERDIST` - Max radius for distance-to-water calculation

**Variable toggles:** Each variable can be individually enabled/disabled in `[VARIABLES_ENABLED]` table.

### H3 Hexagon Grid System

When `--export-hexa-grid` is enabled:
- AOI is tessellated using H3 hierarchical spatial index
- Variables are aggregated per hexagon (same reducers as point sampling)
- Batch processing with configurable batch size and tileScale for memory management
- Outputs: SHP, GeoPackage, CSV formats with H3 IDs and area calculations

**Band configuration:** [src/hex_grid.py](src/hex_grid.py) contains `BAND_CONFIG` dictionary that defines band groupings and reducers for efficient GEE processing.

## Input/Output Specifications

### Input CSV
Minimum required columns: `latitude`, `longitude`. All other columns are preserved in output.

Example:
```csv
site_id,latitude,longitude
S01,-11.7234,-72.4567
S02,-11.8501,-72.3902
```

### Outputs
- **Site-level CSV** → [output/site_env_vars.csv](output/site_env_vars.csv) - Original columns + `{variable}_mean`, `{variable}_std`
- **AOI boundary** → [output/aoi.geojson](output/aoi.geojson) - Study area polygon
- **Optional rasters** → Google Drive root (per-band GeoTIFFs clipped to AOI)
- **Optional hexgrid** → [output/hexagrid.*](output/) - SHP, GPKG, CSV with per-hex statistics

## Adding New Environmental Variables

1. **Create module** in [src/variables/{name}.py](src/variables/) following the extractor pattern
2. **Import** in [src/cli.py](src/cli.py)
3. **Add conditional** in `run_pipeline()` function to call extractor when enabled
4. **Add toggle** to `[VARIABLES_ENABLED]` in [config.toml](config.toml)
5. **Update band config** in [src/hex_grid.py](src/hex_grid.py) `BAND_CONFIG` if supporting hexgrid export

**Template structure (see [canopy_height.py](src/variables/canopy_height.py)):**
```python
def extract_{variable}(df, aoi, points_feature_collection, **kwargs):
    # Load GEE dataset
    image = _load_{variable}_image(aoi)

    # Extract statistics using shared utilities
    compute_stats = build_variable_extractor(image, [BAND_NAME], scale)
    fc_stats = points_feature_collection.map(compute_stats)

    # Fetch and merge results
    results = fc_stats.getInfo()
    result_df = merge_ee_sampling_results(df, results, column_map)

    return result_df, image
```

## Important Design Patterns

### Water Masking
[src/variables/water.py](src/variables/water.py) provides `load_water_layers()` combining:
- GLCF Global Land Cover Facility water mask
- OSM OpenStreetMap water layer

Used in NDVI cloud masking and distance-to-water calculations.

### Index-Based Merging
All extractors preserve original DataFrame row order using `merge_ee_sampling_results()` with index-based joins. Never use coordinate-based matching as floating-point precision issues can cause mismatches.

### Lazy Evaluation
GEE operations are staged and only executed on `.getInfo()` calls. This allows building complex image processing pipelines efficiently on the server side.

### Error Handling
The pipeline is fail-fast - configuration and coordinates are validated before expensive GEE operations begin. Individual variable extractors wrap GEE calls in try-except blocks with descriptive error messages.

### Memory Management
For large AOIs or fine hexgrid resolutions, use `tileScale` parameter (range: 1-16) in hexagon extraction to manage Earth Engine memory limits. Higher values = more tiles = less memory per tile.

## Performance Considerations

- **GEE quotas:** Subject to Earth Engine compute and storage limits
- **Satellite embeddings:** 64 bands make raster/hexgrid exports very large and slow - only enabled for point sampling by default
- **Hexgrid resolution:** Each H3 resolution level increases cell count by ~7x (see README table for area reference)
- **Batch processing:** Hexagon extraction uses configurable batch size (default: 100) with progress bars

## Project Structure

```
ds-gis-pipeline/
├── src/
│   ├── cli.py                  # Main orchestrator
│   ├── auth.py                 # GEE authentication
│   ├── aoi.py                  # AOI creation
│   ├── sampling.py             # Point buffering and utilities
│   ├── hex_grid.py             # H3 grid generation
│   ├── export.py               # Export utilities
│   ├── utils.py                # Plotting/visualization
│   └── variables/              # Variable extractors
│       ├── ndvi.py
│       ├── canopy_height.py
│       ├── landcover.py
│       ├── worldclim.py
│       ├── waterdist.py
│       ├── water.py            # Water mask utilities
│       ├── elevation.py
│       ├── biomass.py
│       ├── bii.py
│       ├── nighttime_lights.py
│       ├── satellite_embedding.py
│       └── eii.py              # In development
├── config.toml                 # Pipeline configuration
├── pipeline.ipynb              # Interactive notebook
├── input/locations.csv         # Example input
├── output/                     # Generated outputs (git-ignored)
└── doc/datasets/               # Dataset documentation
```

## Current Development State

**Active branch:** `pr/ei-var` - Integrating Ecosystem Integrity Index (EII)

**Recent changes:**
- Added AOI GeoJSON export functionality
- Updated distance-to-water band naming convention
- EII integration in progress ([src/variables/eii.py](src/variables/eii.py))

**Dependencies:** Using `ecosystem-integrity-index` package from GitHub (see [pyproject.toml](pyproject.toml) line 68).
