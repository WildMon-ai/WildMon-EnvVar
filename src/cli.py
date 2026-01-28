"""Command-line interface for running the environmental variable extraction pipeline."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import re

import ee
import pandas as pd

from auth import AuthenticationService
from aoi import create_aoi_from_coordinates
from hex_grid import generate_h3_hexagon_grid, extract_values_from_hexagons
from variables.eii import extract_eii
from variables.biomass import extract_biomass
from variables.bii import extract_bii
from variables.canopy_height import extract_canopy_height
from variables.elevation import extract_elevation, ELEVATION_BANDS
from export import export_aoi_geojson, export_csv, export_rasters_to_gdrive, export_hexagrid_results, DEFAULT_IMAGE_EXPORT_CRS
from variables.landcover import extract_landcover
from variables.ndvi import extract_ndvi
from variables.nighttime_lights import extract_nighttime_lights
from sampling import (
    clean_coordinates_dataframe,
    convert_points_to_buffered_features,
)
from variables.waterdist import extract_distance_to_water, COMBINED_WATER_BAND
from variables.worldclim import extract_worldclim
from variables.satellite_embedding import extract_satellite_embedding

logger = logging.getLogger(__name__)

OUTPUT_AOI_PATH = "output/aoi.geojson" 
OUTPUT_SITE_ENV_VARS_PATH = "output/site_env_vars.csv"
OUTPUT_HEXAGRID = "output/hexagrid"

WORLDCLIM_PATTERN = re.compile(r"^bio\d{2}$")

REQUIRED_KEYS = [
    "GEE_PROJECT_ID",
    "LOCATIONS_CSV_PATH",
    "LAT_COLUMN_NAME",
    "LON_COLUMN_NAME",
    "SAMPLING_POINT_BUFFER_METERS",
    "AOI_BUFFER_KM",
    "IMAGE_START_DATE",
    "IMAGE_END_DATE",
    "MAX_SEARCH_DISTANCE_M_WATERDIST",
]


@dataclass
class PipelineConfig:
    GEE_PROJECT_ID: str
    LOCATIONS_CSV_PATH: Path
    OUTPUT_SITE_ENV_VARS_PATH: Path
    OUTPUT_HEXAGRID: Path
    LAT_COLUMN_NAME: str
    LON_COLUMN_NAME: str
    HEXAGRID_RESOLUTION: int
    SAMPLING_POINT_BUFFER_METERS: int
    AOI_BUFFER_KM: float
    IMAGE_START_DATE: str
    IMAGE_END_DATE: str
    MAX_SEARCH_DISTANCE_M_WATERDIST: int
    VARIABLES_ENABLED: Dict[str, bool]
    WORLDCLIM_VARIABLES: Optional[list[str]] = None
    SERVICE_ACCOUNT: Optional[str] = None
    SERVICE_ACCOUNT_KEY_FILE: Optional[Path] = None

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run environmental variable extraction via CLI.",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to config file (TOML or JSON).",
    )
    parser.add_argument(
        "--export-raw-rasters",
        action="store_true",
        help="Export stacked rasters to Google Drive.",
    )
    parser.add_argument(
        "--export-hexa-grid",
        action="store_true",
        help="(Placeholder) export hexa grid.",
    )
    return parser

def _load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    suffix = path.suffix.lower()
    if suffix in {".toml", ".tml"}:
        try:
            import tomllib  # py3.11+
        except ModuleNotFoundError as exc:  # pragma: no cover - older Python guard
            raise RuntimeError("tomllib is required for TOML configs on this Python version") from exc
        with path.open("rb") as f:
            return tomllib.load(f)
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    raise ValueError(f"Unsupported config format '{suffix}'. Use TOML or JSON.")


def _validate_and_build_config(raw: Dict[str, Any]) -> PipelineConfig:
    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    service_account = raw.get("SERVICE_ACCOUNT")
    service_account_key_file = raw.get("SERVICE_ACCOUNT_KEY_FILE")
    service_account_key_file = Path(service_account_key_file) if service_account_key_file else None

    return PipelineConfig(
        GEE_PROJECT_ID=str(raw["GEE_PROJECT_ID"]),
        LOCATIONS_CSV_PATH=Path(raw["LOCATIONS_CSV_PATH"]),
        OUTPUT_HEXAGRID=Path(OUTPUT_HEXAGRID),
        OUTPUT_SITE_ENV_VARS_PATH=Path(OUTPUT_SITE_ENV_VARS_PATH),
        LAT_COLUMN_NAME=str(raw["LAT_COLUMN_NAME"]),
        LON_COLUMN_NAME=str(raw["LON_COLUMN_NAME"]),
        HEXAGRID_RESOLUTION=int(raw["HEXAGRID_RESOLUTION"]),
        SAMPLING_POINT_BUFFER_METERS=int(raw["SAMPLING_POINT_BUFFER_METERS"]),
        AOI_BUFFER_KM=float(raw["AOI_BUFFER_KM"]),
        IMAGE_START_DATE=str(raw["IMAGE_START_DATE"]),
        IMAGE_END_DATE=str(raw["IMAGE_END_DATE"]),
        MAX_SEARCH_DISTANCE_M_WATERDIST=int(raw["MAX_SEARCH_DISTANCE_M_WATERDIST"]),
        VARIABLES_ENABLED=raw.get("VARIABLES_ENABLED",{}),
        SERVICE_ACCOUNT=service_account,
        SERVICE_ACCOUNT_KEY_FILE=service_account_key_file,
    )

def run_pipeline(cfg: PipelineConfig,
                 export_raw_rasters: bool,
                 export_hexa_grid: bool) -> None:
    
    ok = AuthenticationService.authenticate(
        project_id=cfg.GEE_PROJECT_ID,
        service_account=cfg.SERVICE_ACCOUNT,
        key_file=cfg.SERVICE_ACCOUNT_KEY_FILE,
    )
    if not ok:
        raise SystemExit("Could not initialize Earth Engine")

    df = pd.read_csv(cfg.LOCATIONS_CSV_PATH)

    df = clean_coordinates_dataframe(df=df,
                                     lat_col=cfg.LAT_COLUMN_NAME,
                                     lon_col=cfg.LON_COLUMN_NAME)
    points_fc = convert_points_to_buffered_features(
        df,
        lat_col=cfg.LAT_COLUMN_NAME,
        lon_col=cfg.LON_COLUMN_NAME,
        buffer_meters=cfg.SAMPLING_POINT_BUFFER_METERS,
    )
    aoi = create_aoi_from_coordinates(df, buffer_km=cfg.AOI_BUFFER_KM)
    export_aoi_geojson(aoi=aoi, output_path=OUTPUT_AOI_PATH)
    
    def _year_from_date(date_str: str) -> int:
        return int(str(date_str).split("-")[0])

    end_year = int(str(cfg.IMAGE_END_DATE).split("-")[0])
    
    images: list[ee.Image] = []

    if cfg.VARIABLES_ENABLED.get("ndvi", False):
        df, image_ndvi = extract_ndvi(
            df=df,
            aoi=aoi,
            points_feature_collection=points_fc,
            start_date=cfg.IMAGE_START_DATE,
            end_date=cfg.IMAGE_END_DATE,
        )
        images.append(image_ndvi)

    if cfg.VARIABLES_ENABLED.get("canopy_height", False):
        df, image_canopy_height = extract_canopy_height(
            df=df,
            aoi=aoi,
            points_feature_collection=points_fc,
        )
        images.append(image_canopy_height)

    if cfg.VARIABLES_ENABLED.get("agb", False):
        df, image_biomass = extract_biomass(
            df=df,
            aoi=aoi,
            points_feature_collection=points_fc,
            year=end_year,
        )
        images.append(image_biomass)

    if cfg.VARIABLES_ENABLED.get("land_cover", False):
        df, image_landcover = extract_landcover(
            df=df,
            aoi=aoi,
            points_feature_collection=points_fc,
        )
        images.append(image_landcover)
    
    elev_bands_enabled = [b for b in ELEVATION_BANDS if cfg.VARIABLES_ENABLED.get(b, False)]
    if elev_bands_enabled:
        df, image_elevation = extract_elevation(
            df=df,
            aoi=aoi,
            points_feature_collection=points_fc,
        )
        if "slope_percent" not in elev_bands_enabled:
            df = df.drop(columns=[c for c in df.columns if c.startswith("slope_percent_")], errors="ignore")
        if "elevation" not in elev_bands_enabled:
            df = df.drop(columns=[c for c in df.columns if c.startswith("elevation_")], errors="ignore")
        images.append(image_elevation.select(elev_bands_enabled))

    if cfg.VARIABLES_ENABLED.get("distance_to_water_m", False):
        df, image_waterdist = extract_distance_to_water(
            df=df,
            aoi=aoi,
            points_feature_collection=points_fc,
            max_search_distance=cfg.MAX_SEARCH_DISTANCE_M_WATERDIST,
        )
        images.append(image_waterdist)

    if cfg.VARIABLES_ENABLED.get("biointactness", False):
        df, image_bii = extract_bii(
            df=df,
            aoi=aoi,
            points_feature_collection=points_fc,
            year=end_year,
        )
        images.append(image_bii)

    if cfg.VARIABLES_ENABLED.get("nighttime_lights", False):
        df, image_nightlights = extract_nighttime_lights(
            df=df,
            aoi=aoi,
            points_feature_collection=points_fc,
            year=end_year,
        )
        images.append(image_nightlights)

    if cfg.VARIABLES_ENABLED.get("satellite_embedding", False):
        df, _ = extract_satellite_embedding(
            df=df,
            aoi=aoi,
            points_feature_collection=points_fc,
            year=end_year,
        )
    
    if cfg.VARIABLES_ENABLED.get("eii", False):
        df, image_eii = extract_eii(
            df=df,
            aoi=aoi,
            points_feature_collection=points_fc,
        )
        images.append(image_eii)

    worldclim_enabled = [
    band
    for band, enabled in cfg.VARIABLES_ENABLED.items()
    if enabled and WORLDCLIM_PATTERN.match(band)
    ]
    if worldclim_enabled:
        df, image_worldclim = extract_worldclim(
            df=df,
            aoi=aoi,
            points_feature_collection=points_fc,
            variables=worldclim_enabled,
        )
        images.append(image_worldclim.select(worldclim_enabled))

    if not images:
        raise ValueError("No imagery variables enabled; enable at least one in VARIABLES_ENABLED.")

    export_csv(df, str(cfg.OUTPUT_SITE_ENV_VARS_PATH))
    
    image_stack = (
            images[0]
            if len(images) == 1
            else ee.Image.cat(images)
        )
    
    if export_raw_rasters:
        prefix = str(_year_from_date(cfg.IMAGE_START_DATE))
        export_rasters_to_gdrive(
            image=image_stack,
            region=aoi,
            file_name_prefix=prefix,
            scale=cfg.SAMPLING_POINT_BUFFER_METERS,
            crs=DEFAULT_IMAGE_EXPORT_CRS,
            file_format="GeoTIFF",
        )

    if export_hexa_grid:
        bands = image_stack.bandNames().remove(COMBINED_WATER_BAND)
        image_stack = image_stack.select(bands)

        logger.info("Generating H3 hexagonal grid and extracting values...")
        hex_gdf = generate_h3_hexagon_grid(aoi=aoi,
                                           h3_resolution=cfg.HEXAGRID_RESOLUTION,
                                           calculate_area=True,
                                           crs=DEFAULT_IMAGE_EXPORT_CRS)
        
        hexagons_with_data = extract_values_from_hexagons(
            hex_gdf=hex_gdf,
            image_stack=image_stack,
            batch_size=100, 
            tileScale=4, # increase up to 16 if having memory issues
        )
        logger.info("H3 hexagonal grid generation and data extraction completed")
        
        export_hexagrid_results(hexagons_with_data, OUTPUT_HEXAGRID)

        logger.info("Exported hexagons with data to files.")


def main(argv: Optional[list[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    raw_cfg = _load_config(Path(args.config))
    cfg = _validate_and_build_config(raw_cfg)

    run_pipeline(cfg,
                 export_raw_rasters=args.export_raw_rasters,
                 export_hexa_grid=args.export_hexa_grid)


if __name__ == "__main__":
    main()
