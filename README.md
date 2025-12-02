# ds-gis-pipeline

Environmental variable extraction around point locations using Google Earth Engine (GEE). The pipeline ingests a CSV of coordinates, builds an area of interest (AOI), buffers each point, samples multiple environmental datasets, and exports a tidy CSV (plus optional rasters to Google Drive). A companion notebook is available for interactive exploration (maps, per-variable scaling, quick tweaks); for production runs we recommend the CLI with the provided defaults.

## What the pipeline does
- Validates and cleans input coordinates, discarding out-of-bounds points.
- Builds an AOI by bounding all points and adding a user-defined buffer. This is used to expedite processing but also to export rasters and other grids necessary for model projections.
- Buffers each point to create sampling geometries (circles). This gets used to extract mean/std statistics for each variable.
- Extracts variables from GEE (current set): NDVI (Landsat 9), canopy height (ETH 2020 10 m), WorldClim bioclim, ESA Land Cover, distance to water, above-ground biomass, nighttime lights, and elevation (& slope). 
- Exports a CSV with summary stats per location, and optionally exports the raw source rasters from GEE to GeoTIFFs to Google Drive.

## Prerequisites
- Google Earth Engine access (and a GCP project you can bill against).
- Python 3.12 (managed automatically by `uv`).
- [`uv`](https://docs.astral.sh/uv/) 0.4.0+ for environment and commands.
- Google Cloud SDK for authentication (`gcloud`).

## Setup with uv and GCP auth
```bash
# 1) Install uv (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh
# or: brew install uv

# 2) Ensure Python 3.12 is available to uv
uv python install 3.12

# 3) Create the virtual env and install locked deps
uv sync

# 4) Install gcloud (for browser-based auth)
brew install --cask google-cloud-sdk # Mac
sudo apt-get install google-cloud-sdk # Linux
https://cloud.google.com/sdk/docs/install#windows # Windows

# 5) Authenticate to GCP/GEE (one-time per machine)
gcloud init                           # choose account and defaults
gcloud auth login                     # browser login for gcloud CLI
gcloud auth application-default login # sets ADC used by the pipeline
gcloud config set project <your-gcp-project-id>
```

### Service account option
If browser auth is not possible, you can create a service account with Earth Engine + Drive access, download its JSON key, and set in the config:
- `SERVICE_ACCOUNT = "svc@project.iam.gserviceaccount.com"`
- `SERVICE_ACCOUNT_KEY_FILE = "/abs/path/to/key.json"`
More info at:
[https://docs.cloud.google.com/iam/docs/service-accounts-create]

## Configure the run
If you plan to run the CLI, You need to first edit the `config.toml` file (or point the CLI at another TOML/JSON).

Required keys:

| Key | What it controls |
| --- | --- |
| `GEE_PROJECT_ID` | GCP project used for GEE billing/quotas. |
| `LOCATIONS_CSV_PATH` | Input CSV with at least latitude/longitude columns. |
| `OUTPUT_CSV_PATH` | Where the output summary CSV with results will be written. |
| `LAT_COLUMN_NAME` / `LON_COLUMN_NAME` | Column names in your CSV (case-insensitive). |
| `SAMPLING_POINT_BUFFER_METERS` | Radius for buffered sampling geometries. |
| `AOI_BUFFER_KM` | Buffer added to the bounding box of all points to form the AOI. |
| `IMAGE_START_DATE` / `IMAGE_END_DATE` | Date range for time-filtered datasets (e.g., NDVI, lights). |
| `MAX_SEARCH_DISTANCE_M_WATERDIST` | Max search radius when finding nearest water. |
| Optional: `WORLDCLIM_VARIABLES` | List of WorldClim bands to subset (defaults to all 19). |
| Optional: `SERVICE_ACCOUNT`, `SERVICE_ACCOUNT_KEY_FILE` | Use service account instead of browser auth. |

Input expectations:
- CSV rows represent sampling locations; default columns `latitude`, `longitude`. You can have aditional columns into your DF.
- Values outside valid coordinates ranges are dropped; the run will fail if all points are invalid.
- AOI and sampling buffers are derived from the cleaned points and your buffer settings.

## Run the CLI (recommended)
From the repo root:
```bash
uv run python -m cli --config config.toml \
  [--export-raw-rasters] [--export-hexa-grid]
```
- `--export-raw-rasters`: exports each band to Google Drive as GeoTIFF (one folder per band).
- `--export-hexa-grid`: placeholder flag; not implemented yet.
- Outputs: the CSV at `OUTPUT_CSV_PATH`; if raster export is enabled, monitor tasks at https://code.earthengine.google.com/tasks.

## Use the notebook (interactive option)
```bash
uv run jupyter notebook pipeline.ipynb
```
The notebook mirrors the CLI flow but lets you visualize the AOI, adjust per-variable scale parameters, and inspect map layers. Keep the same config values unless you intentionally diverge.

## Contributing / tweaking
- Modify dependencies with `uv add <pkg>` / `uv remove <pkg>`; commit both `pyproject.toml` and `uv.lock`.
- Add new variables under `src/variables/` following the existing extractor pattern, and wire them into `src/cli.py`.

## Tips and troubleshooting
- If you see auth errors, rerun `gcloud auth application-default login` or switch to a service account.
- Rasters export to Drive; ensure your account/service account has Drive access.
- Keep buffer sizes reasonable; very large AOIs can exhaust Earth Engine limits.
