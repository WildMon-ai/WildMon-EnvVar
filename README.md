# 🌎 WildMon EnvVars

### **Environmental covariate extraction for biodiversity and ecological modeling (via Google Earth Engine)**

**wildmon-envvars** is a Python Pipeline for extracting high-quality environmental variables around point locations using **Google Earth Engine (GEE)**.
It is designed for biodiversity monitoring, ecological analyses, and species distribution modeling (SDMs), where environmental predictors such as NDVI, canopy height, climate variables, or distance to water are essential to understand the relationship between biodiversity and the landscape.

The pipeline provides a **reproducible, scalable, one-config-file workflow** to generate ready-to-use covariates — without requiring users to write GEE code or GIS expertise.

---

## 🚀 Key Features

* Extract environmental covariates for point locations (buffered geometries).
* Automatically build an **Area of Interest (AOI)** from your coordinate set.
* Support for 10+ global datasets:
  NDVI, canopy height, land cover, bioclimate, biomass, nighttime lights, elevation, slope and distance to water. 
* Export processed results to a tidy CSV.
* **Optional:** export raw rasters as GeoTIFFs for GIS workflows.
* **Optional:** build an **Hexagon grid** covering the AOI and extract per-hex statistics (useful for model projections).
* CLI for hands-off, reproducible runs; Jupyter notebook for visual exploration.
* Config-driven design — easy to automate and version-control.

---

## 📦 Quickstart (30 seconds)

### **Prerequisite: Input CSV**

An example CSV is provided at `input/locations.csv`.

```csv
site_id,latitude,longitude
S01,-11.7234,-72.4567
S02,-11.8501,-72.3902
```

You can **run the pipeline using this file immediately** for testing, or replace it with your own CSV (any file with at least `latitude` and `longitude` columns is valid).

Adjust `LOCATIONS_CSV_PATH` in your `config.toml` to point to your own file if you use a different file name.

### 1. Clone and install via [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
After installing `uv`:

```bash
git clone https://github.com/WildMon-ai/ds-gis-pipeline.git
cd ds-gis-pipeline
uv sync
```

### 2. Authenticate with [Google Cloud / Earth Engine](https://docs.cloud.google.com/sdk/docs/install-sdk)
After installing `gcloud`:

```bash
gcloud auth application-default login
gcloud config set project <your-gcp-project-id>
```

### 3. Run the pipeline

After providing a csv (comma separated) with at least two columns representing latitude and longitude of your sites

```bash
uv run python src/cli.py --config config.toml
```

Optional flags:
We recomend using those only after selecting the final env vars due to computational constraints.

```bash
--export-raw-rasters    # save GeoTIFFs to Google Drive
--export-hexa-grid      # compute H3 grid statistics
```

---

## 🧭 What the pipeline does (high-level workflow)

```md
                           Input CSV
                    (lat/lon + metadata)
                               │
                               ▼
                       Coordinate cleaning
                               │
                               ▼
                AOI construction (bounding box + buffer)
                               │
                               ▼
               Create sampling buffers around each point
                               │
                               ▼
     ┌────────────────────────────────────────────────────────────┐
     │   Load + prepare GEE datasets (masking, scaling, proj)     │
     └────────────────────────────────────────────────────────────┘
                               │
                               ▼
                 Extract variables for buffered points
                               │
                               ▼
        ┌─────────────────────────────────────────────────────────┐
        │                 Summary CSV (per-point stats)           │
        └─────────────────────────────────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────────┐
            │                                         │
            ▼                                         ▼

 Optional: Export rasters                      Optional: Build H3 hexgrid
  (GeoTIFFs to Drive)                        inside AOI and extract stats
            │                                         │
            ▼                                         ▼
       GeoTIFF files                             Hexgrid stats file
                                           (SHP / GPKG / CSV formats)
```
---

## 📝 Example Site Level Env Vars Output (CSV)

| site_id | latitude | longitude | ndvi_mean | canopy_height | dist_water | bio1 | bio12 | landcover | ... |
| ------- | -------- | --------- | --------- | ------------- | ---------- | ---- | ----- | --------- | --- |
| S1      | -11.72   | -72.45    | 0.63      | 28.4          | 91.2      | 23.1 | 2400  | Tree_cover  | ... |

The pipeline guarantees:

* consistent scaling
* projection alignment
* masked values handled correctly (water bodies)
* reducers chosen per dataset (mean, mode, median, etc.)

---

## 📁 Available Datasets (and how they’re processed)

| Dataset | Scale | Reducer | Temporal range | Notes |
| --- | --- | --- | --- | --- |
| [**NDVI (Landsat 9)**](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC09_C02_T1_L2) | 30 m | median, sd | 2021–present (filtered by `IMAGE_START_DATE`/`IMAGE_END_DATE`) | Cloud-masked, water-masked |
| [**Canopy height (ETH 2020)**](https://gee-community-catalog.org/projects/canopy/) | 10 m | median, sd | 2020 snapshot | Global canopy height model |
| [**WorldClim bioclim (19 vars)**](https://developers.google.com/earth-engine/datasets/catalog/WORLDCLIM_V1_BIO) | ~1 km | median, sd | Climatology (1970–2000 baseline, static) | Variables scaled automatically |
| [**ESA Land Cover**](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200) | 10 m | mode, percentage of each category | 2021 (v200) | Mapped to class labels |
| **Distance to water** | 30 m | median, sd | Static | Fast distance transform combining [GLCF](https://developers.google.com/earth-engine/datasets/catalog/GLCF_GLS_WATER) and [OSM](https://gee-community-catalog.org/projects/osm_water/?h=water) |
| [**Above-ground biomass (AGB)**](https://gee-community-catalog.org/projects/cci_agb/?h=above+ground+biomass) | 100 m | median, sd | 2007,2010,2015-2022 | ESA CCI Global Forest Above Ground Biomass |
| [**Nighttime lights (VIIRS)**](https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_ANNUAL_V22) | 464 m | median, sd | Annual composites (2012–2023) | Time-filtered by config window |
| [**Elevation & slope (Copernicus)**](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30) | 30 m | median, sd | Static | Derived slope in percentage |
| [**Biodiversity Intactness Index (BII)**](https://gee-community-catalog.org/projects/bii/) | 100 m | mean | 2017–2020 | Global BII annual composites |
| [**Satellite embeddings (Google/DeepMind)**](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_SATELLITE_EMBEDDING_V1_ANNUAL#bands) | 10 m | mean | 2017–2023 | 64-band annual embeddings; point stats only by default (rasters/hex grids not exported due to size) |


All processing steps (scaling, masking, projections) are abstracted away.

---

## 🔧 Configuration (config.toml)

Key required settings:

| Key                                                     | Description                            |
| ------------------------------------------------------- | -------------------------------------- |
| `GEE_PROJECT_ID`                                        | Google Cloud Project ID used for GEE billing/quotas    |
| `LOCATIONS_CSV_PATH`                                    | Input CSV path with location's coordinates                         |
| `LAT_COLUMN_NAME` / `LON_COLUMN_NAME`                   | Location's geographic coordinate column names                  |
| `SAMPLING_POINT_BUFFER_METERS`                          | Radius for buffered sampling, pixels within that buffered area will be used to summarize the variation for each site           |
| `AOI_BUFFER_KM`                                         | Buffer added to bounding box of points (AOI) |
| `HEXAGRID_RESOLUTION`                                   | H3 resolution when exporting hex grids (default 9 ≈ 183 m radius), more details [here](#hexagon-grid-extraction-h3) |
| `IMAGE_START_DATE` / `IMAGE_END_DATE`                   | Date range for NDVI/lights and other variables that have multi-year images             |
| `MAX_SEARCH_DISTANCE_M_WATERDIST`                       | Max radius for water distance, values above that will be set to max value + 1          |
| Optional: `SERVICE_ACCOUNT`, `SERVICE_ACCOUNT_KEY_FILE` | For automated runs                     |
| Optional: `Subselect Variables` | If you are only interested in a subset of variables                     |

---

## 🖥 CLI Usage

```bash
uv run python src.cli --config config.toml \
  [--export-raw-rasters] \
  [--export-hexa-grid]
```

Suggested workflow:

1. Run basic site-level extraction (summary CSV) first without rasters and hexa-grid.
2. When needed, export rasters for GIS debugging or modeling.
3. Use hex-grids for spatial projections (downstream SDMs, maps, etc.).

Outputs:

* Site-level Environmental Variables: `output/site_env_vars.csv`
* Optional: raster GeoTIFFs directly saved to the root of your Google Drive
* Optional: hex grids (`output/hexgrids.*`) in `.shp`, `.gpkg`, and `csv` formats

---

## 🗺 Interactive Notebook

Launch:

```bash
uv run jupyter notebook pipeline.ipynb
```

The notebook mirrors the CLI flow, adds visualization tools, and supports quick parameter tuning. Useful for more interactive processes.

---

## ⚙️ Hexagon Grid Extraction (H3)

When `--export-hexa-grid` is enabled:

* AOI is tiled using an H3 grid (default resolution 9 ≈ 183 m radius).
* The same variables extracted for points are aggregated per hexagon.
* Useful for modeling workflows that require continuous spatial predictions.

Reference table for the different HEXAGRID_RESOLUTIONS values:
| Resolution | Area (km²) | Area (m²)        | Area (ha)        | Approximate Radius (m) |
|------------|------------|------------------|-------------------|-------------------------|
| 0          | 4,250,547  | 4,250,546,847,700 | 425,054,684.77    | 1,163,181               |
| 1          | 607,221    | 607,220,978,243   | 60,722,097.82     | 439,641                 |
| 2          | 86,746     | 86,745,854,035    | 8,674,585.40      | 166,169                 |
| 3          | 12,392     | 12,392,264,862    | 1,239,226.49      | 62,806                  |
| 4          | 1,770      | 1,770,323,552      | 177,032.36        | 23,738                  |
| 5          | 253        | 252,903,365        | 25,290.34         | 8,972                   |
| 6          | 36         | 36,129,052         | 3,612.91          | 3,391                   |
| 7          | 5          | 5,161,293          | 516.13            | 1,282                   |
| 8          | 1          | 737,328            | 73.73             | 484                     |
| 9          | 0          | 105,333            | 10.53             | 183                     |
| 10         | 0          | 15,048             | 1.50              | 69                      |
| 11         | 0          | 2,149              | 0.21              | 26                      |
| 12         | 0          | 307                | 0.03              | 10                      |
| 13         | 0          | 44                 | 0.00              | 4                       |
| 14         | 0          | 6                  | 0.00              | 1                       |
| 15         | 0          | 1                  | 0.00              | 1                       |


Under the hood:

* Band groups processed together to minimize GEE calls.
* Operations batched to avoid memory/time limits.
* Output formats: SHP, GeoPackage, CSV.

---

## 🔒 Authentication Options
Before running any code you'll need access to the GCP project where your GEE is setup. You can do that in two anys:

### Default (recommended)

```bash
gcloud auth application-default login
```

### Service Account (for automation)

Add to `config.toml`:

```
SERVICE_ACCOUNT = "svc@project.iam.gserviceaccount.com"
SERVICE_ACCOUNT_KEY_FILE = "/path/key.json"
```

---

## 🧩 Contributing / Extending

* Add new data extractors under `src/variables/` following the existing pattern.
* Manage dependencies with `uv add <pkg>` / `uv remove <pkg>`.
* Please open issues or PRs for new datasets or bug fixes.

---

## ⚠️ Notes & Performance Tips

* Very large AOIs or fine-resolution hexgrids may exceed Earth Engine compute limits. If you experience difficulties we recommend downscaling the AOI or Hexgrid resolution.
* Start small (few points), inspect results, then scale up.
* Rasters export via Google Drive — ensure Drive API access is enabled.
* If authentication fails, rerun `gcloud auth application-default login`.

---

## 📜 License

This project is released under the MIT License. See the LICENSE file for details (TO BE ADDED).
