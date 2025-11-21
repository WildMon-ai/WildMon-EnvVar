import logging
from typing import Dict, Tuple

import ee
import pandas as pd

from src.sampling import merge_ee_sampling_results

LANDCOVER_COLLECTION_ID = "ESA/WorldCover/v200"
LANDCOVER_BAND = "Map"

LANDCOVER_CLASSES: Dict[int, str] = {
    10: "Tree_cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built_up",
    60: "Bare_sparse_vegetation",
    70: "Snow_and_ice",
    80: "Permanent_water_bodies",
    90: "Herbaceous_wetland",
    95: "Mangroves",
    100: "Moss_and_lichen",
}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_landcover(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    scale: int = 10,
) -> Tuple[pd.DataFrame, ee.Image]:
    """
    Extract ESA WorldCover dominant class and per-class proportions for buffered points.

    Args:
        df: DataFrame aligned with the buffered feature collection (index preserved).
        aoi: ee.Geometry defining the project area to clip the landcover image.
        points_feature_collection: ee.FeatureCollection of buffered sampling units.
        scale: Scale (meters) for reductions. ESA WorldCover native resolution is 10 m.

    Returns:
        (result_df, landcover_image):
            result_df: DataFrame containing dominant class code/label and per-class proportions.
            landcover_image: ee.Image used for sampling.
    """
    logger.info(f"Processing {len(df)} points...")
    logger.info("Date range: 2021")
    logger.info(f"Scale: {scale}m")

    logger.info("Loading ESA WorldCover composite for study area...")
    landcover_image = _load_worldcover_image(aoi)

    logger.info("Extracting dominant landcover and class proportions...")
    compute_landcover_stats = _build_landcover_extractor(landcover_image, scale)
    fc_stats = points_feature_collection.map(compute_landcover_stats)

    logger.info("Fetching landcover statistics from Earth Engine...")
    results = _fetch_landcover_results(fc_stats)

    logger.info("Merging landcover results into dataframe...")
    result_df = _merge_landcover_results(df, results)
    result_df = _add_dominant_labels(result_df)

    _log_extraction_summary(result_df)
    return result_df, landcover_image


def _load_worldcover_image(
    aoi: ee.Geometry,
) -> ee.Image:
    """Load the ESA WorldCover mosaic for the requested time range and clip to the AOI.

    Args:
        aoi: ee.Geometry defining the area of interest for clipping the WorldCover image.
    Returns:
        landcover_image: ee.Image clipped to the AOI."""
    image = (
        ee.ImageCollection(LANDCOVER_COLLECTION_ID)
        .first()
        .select(LANDCOVER_BAND)
    )
    if image is None:
        raise ValueError("ESA WorldCover dataset returned no imagery")
    return image.clip(aoi)


def _build_landcover_extractor(
    landcover_image: ee.Image,
    scale: int,
):
    """Build a reducer function returning dominant class and per-class proportions.
    This function combines two statistics: mode (dominant class) and proportion of each class
    in the buffered area. First, it computes a histogram of class frequencies, then derives
    proportions from the histogram counts.
    Args:
        landcover_image: ee.Image containing the landcover data.
        scale: Scale in meters for the sampling reducer.
    Returns:
        extract: Function that takes an ee.Feature and returns an ee.Element with stats."""

    def _compute_stats(feature: ee.Feature) -> ee.Element:
        reducer = ee.Reducer.mode().combine(
            reducer2=ee.Reducer.frequencyHistogram(),
            sharedInputs=True,
        )

        stats = landcover_image.reduceRegion(
            reducer=reducer,
            geometry=feature.geometry(),
            scale=scale,
            maxPixels=1_000_000_000,
            bestEffort=True,
        )

        stats_dict = ee.Dictionary(stats)
        histogram_key = f"{LANDCOVER_BAND}_histogram"
        histogram = ee.Dictionary(
            ee.Algorithms.If(
                stats_dict.contains(histogram_key),
                stats_dict.get(histogram_key),
                {},
            )
        )

        total_pixels = ee.Number(
            ee.Algorithms.If(
                histogram.size(),
                ee.Number(histogram.values().reduce(ee.Reducer.sum())),
                0,
            )
        )

        def _compute_proportion(class_code: int):
            """"
            Compute the proportion of pixels for a given class code.
            Returns None if there are no pixels in the area.
            """
            key = ee.String(str(class_code))
            class_count = ee.Number(
                ee.Algorithms.If(
                    histogram.contains(key),
                    histogram.get(key),
                    0,
                )
            )
            return ee.Algorithms.If(
                total_pixels.gt(0),
                ee.Number(class_count).divide(total_pixels),
                None,
            )

        properties: Dict[str, object] = {
            "landcover_dominant_code": stats_dict.get(f"{LANDCOVER_BAND}_mode"),
        }

        for class_code, label in LANDCOVER_CLASSES.items():
            properties[f"landcover_prop_{label}"] = _compute_proportion(class_code)

        return feature.set(properties)

    return _compute_stats


def _fetch_landcover_results(
    fc_stats: ee.FeatureCollection,
):
    """Fetch Earth Engine sampling output."""
    try:
        return fc_stats.getInfo()
    except Exception as exc:  # pragma: no cover - EE failure path
        logger.error(f"Failed to fetch landcover statistics from Earth Engine: {exc}")
        raise


def _merge_landcover_results(
    df: pd.DataFrame,
    results,
) -> pd.DataFrame:
    """Merge dominant class and proportion values into the dataframe copy."""
    column_map: Dict[str, str] = {"landcover_dominant_code": "landcover_dominant_code"}
    for label in LANDCOVER_CLASSES.values():
        prop_col = f"landcover_prop_{label}"
        column_map[prop_col] = prop_col

    return merge_ee_sampling_results(df, results, column_map)


def _add_dominant_labels(result_df: pd.DataFrame) -> pd.DataFrame:
    """Append a human-readable label for the dominant class."""
    code_col = "landcover_dominant_code"
    if code_col not in result_df.columns:
        return result_df

    labeled = result_df.copy()
    labeled["landcover_dominant_label"] = labeled[code_col].map(LANDCOVER_CLASSES)
    labeled = labeled.drop(columns=[code_col])
    return labeled


def _log_extraction_summary(result_df: pd.DataFrame) -> None:
    """Log summary information about extraction success and class distribution."""
    total_points = len(result_df)
    label_col = "landcover_dominant_label"
    if label_col not in result_df.columns:
        logger.info("No dominant landcover label column found; skipping summary.")
        return

    valid_mask = result_df[label_col].notna()
    valid_points = valid_mask.sum()

    logger.info(
        f"Successfully processed {valid_points}/{total_points} points with landcover data"
    )

    if valid_points == 0:
        return

    counts = result_df.loc[valid_mask, label_col].value_counts()
    logger.info("Dominant landcover distribution:")
    for label, count in counts.items():
        share = (count / valid_points) * 100
        logger.info(f"  {label}: {count} points ({share:.1f}%)")
