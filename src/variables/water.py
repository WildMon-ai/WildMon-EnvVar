"""Shared water-layer utilities used by NDVI and water distance modules."""

from typing import Optional, Tuple
import logging

import ee

GLCF_WATER_COLLECTION_ID = "GLCF/GLS_WATER"
OSM_WATER_DATASET_ID = "projects/sat-io/open-datasets/OSM_waterLayer"
DEFAULT_DISTANCE_CRS = "EPSG:3857"
COMBINED_WATER_BAND = "water_mask"

logger = logging.getLogger(__name__)


def load_water_layers(
    aoi: ee.Geometry,
    target_projection: Optional[ee.Projection] = None,
) -> Tuple[ee.Image, ee.Image]:
    """
    Load GLCF and OSM water layers filtered by AOI and reprojected to a common projection.

    Args:
        aoi: Area of interest used for filtering and clipping.
        target_projection: Optional projection to force both layers into. If not provided,
            uses the native projection of the first GLCF image.

    Returns:
        Tuple of (glcf_water, osm_water) images in the same projection, clipped to AOI.
        Class semantics:
          - GLCF: class 2 == water
          - OSM: classes 1..5 == water
    """
    glcf_ic = ee.ImageCollection(GLCF_WATER_COLLECTION_ID).filterBounds(aoi)
    glcf_proj = target_projection or glcf_ic.first().projection()

    glcf_water = (
        glcf_ic.mosaic()
        .reproject(glcf_proj)
        .clip(aoi)
    )

    osm_ic = ee.ImageCollection(OSM_WATER_DATASET_ID).filterBounds(aoi)
    osm_water = (
        osm_ic.mosaic()
        .reproject(glcf_proj)
        .clip(aoi)
    )

    return glcf_water, osm_water


def build_combined_water_mask(
    glcf_water: ee.Image,
    osm_water: ee.Image,
    aoi: ee.Geometry,
    target_crs: Optional[str] = None,
    scale: int = 30,
    invert_for_land_mask: bool = False,
    band_name: str = COMBINED_WATER_BAND,
) -> ee.Image:
    """
    Combine GLCF + OSM into a binary mask and optionally reproject.

    Args:
        glcf_water: GLCF water image (class 2 == water).
        osm_water: OSM water image (classes 1..5 == water).
        aoi: Area of interest for clipping.
        target_crs: Optional CRS string to reproject into (e.g., EPSG codes).
        scale: Pixel scale to use when reprojecting.
        invert_for_land_mask: When True, returns land-as-1 instead of water-as-1.
        band_name: Name for the output band.

    Returns:
        ee.Image with a single binary band (water==1 by default), clipped to AOI.
    """
    glcf_mask = glcf_water.eq(2)
    osm_mask = osm_water.gt(0).And(osm_water.lt(6))

    combined = glcf_mask.Or(osm_mask)

    if invert_for_land_mask:
        combined = combined.Not()

    combined = combined.unmask(0).rename(band_name)

    if target_crs is not None:
        combined = (
            combined
            .reproject(crs=target_crs, scale=scale)
            .selfMask()
        )

    return combined.clip(aoi)


def build_distance_ready_water_mask(
    aoi: ee.Geometry,
    scale: int = 30,
    target_crs: str = DEFAULT_DISTANCE_CRS,
) -> ee.Image:
    """
    Convenience helper for distance-to-water: returns combined water mask
    reprojected to a metric CRS suitable for fastDistanceTransform.

    Args:
        aoi: Area of interest for filtering/clipping.
        scale: Scale in meters for the metric projection.
        target_crs: CRS string for the distance-ready mask (default Web Mercator).

    Returns:
        ee.Image water mask (water == 1) reprojected to target_crs at given scale.
    """
    glcf_water, osm_water = load_water_layers(aoi, target_projection=None)
    return build_combined_water_mask(
        glcf_water=glcf_water,
        osm_water=osm_water,
        aoi=aoi,
        target_crs=target_crs,
        scale=scale,
        invert_for_land_mask=False,
    )
