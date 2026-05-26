import logging
from typing import Dict, List, Optional, Tuple

import ee
import pandas as pd


EMBEDDING_COLLECTION_ID = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
EMBEDDING_BANDS: List[str] = [f"A{i:02d}" for i in range(64)]
EMBEDDING_COLUMN = "satellite_embeddings_v1"
DEFAULT_SCALE = 10
AVAILABLE_YEARS = list(range(2017, 2025))  # 2017-2024
LATEST_YEAR = AVAILABLE_YEARS[-1]

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_satellite_embedding(
    df: pd.DataFrame,
    aoi: ee.Geometry,
    points_feature_collection: ee.FeatureCollection,
    year: int = LATEST_YEAR,
    scale: int = DEFAULT_SCALE,
) -> Tuple[pd.DataFrame, ee.Image]:
    """
    Extract Google Satellite Embedding V1 (64-dim vector) for buffered sampling units.

    Args:
        df: DataFrame aligned with the buffered feature collection.
        aoi: ee.Geometry defining the area of interest to clip the embedding image.
        points_feature_collection: ee.FeatureCollection of buffered sampling units.
        year: Target year (2017-2024). Falls back to the latest available if out of range.
        scale: Sampling scale in meters (dataset native resolution is 10 m).

    Returns:
        (result_df, embedding_image):
            result_df: DataFrame with a single column `satellite_embeddings_v1` containing lists of 64 floats.
            embedding_image: ee.Image used for the extraction.
    """
    logger.info("-----------------------------------------------")
    logger.info("Starting --Satellite Embedding V1-- extraction...")
    logger.info(f"Requested year: {year}")
    logger.info(f"Scale: {scale}m")

    logger.info("Loading Satellite Embedding image...")
    embedding_image = _load_embedding_image(aoi, year)

    logger.info("Extracting embedding vectors...")
    compute_embeddings = _build_embedding_extractor(embedding_image, scale)
    fc_stats = points_feature_collection.map(compute_embeddings)

    logger.info("Fetching embedding results from Earth Engine...")
    results = _fetch_embedding_results(fc_stats)

    logger.info("Merging embeddings into dataframe...")
    result_df = _merge_embedding_results(df, results)

    _log_extraction_summary(result_df)
    return result_df, embedding_image


def _load_embedding_image(aoi: ee.Geometry, requested_year: int) -> ee.Image:
    """Load the embedding image for the requested year, falling back to the latest available."""
    if requested_year not in AVAILABLE_YEARS:
        logger.warning(
            f"Requested year {requested_year} not available for Satellite Embedding V1. "
            f"Using most recent year {LATEST_YEAR} instead."
        )
        target_year = LATEST_YEAR
    else:
        target_year = requested_year

    start_date = f"{target_year}-01-01"
    end_date = f"{target_year}-12-31"

    collection = (
        ee.ImageCollection(EMBEDDING_COLLECTION_ID)
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .select(EMBEDDING_BANDS)
    )

    size = collection.size()
    if size.getInfo() == 0:
        raise ValueError(
            "No Satellite Embedding imagery found for the specified AOI and year."
        )

    # Annual collection is tiled; mosaic to produce a single image for the AOI.
    image = collection.mosaic()
    return ee.Image(image).clip(aoi)


def _build_embedding_extractor(embedding_image: ee.Image, scale: int):
    """Return a mapper that computes the ordered 64-dim embedding list for a feature."""

    def compute_embedding(feature: ee.Feature) -> ee.Element:
        stats = embedding_image.select(EMBEDDING_BANDS).reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=feature.geometry(),
            scale=scale,
            maxPixels=1_000_000_000,
            bestEffort=True,
        )
        ordered = ee.List([stats.get(band) for band in EMBEDDING_BANDS])
        return feature.set(EMBEDDING_COLUMN, ordered)

    return compute_embedding


def _fetch_embedding_results(
    fc_stats: ee.FeatureCollection,
) -> Optional[Dict]:
    """Fetch sampled embedding values from Earth Engine."""
    try:
        return fc_stats.getInfo()
    except Exception as exc:  # pragma: no cover - EE failure path
        logger.error(f"Failed to fetch Satellite Embedding statistics: {exc}")
        raise


def _merge_embedding_results(
    df: pd.DataFrame,
    results: Optional[Dict],
) -> pd.DataFrame:
    """Merge embedding sampling output into a dataframe copy."""
    merged = df.copy()
    merged[EMBEDDING_COLUMN] = None

    if not results:
        return merged

    features = results.get("features", [])
    if not features:
        return merged

    embedding_map: Dict[object, object] = {}
    for f in features:
        props = f.get("properties", {})
        idx = props.get("index")
        if idx is None or idx not in merged.index:
            continue
        embedding_map[idx] = props.get(EMBEDDING_COLUMN)

    merged[EMBEDDING_COLUMN] = pd.Series(
        [embedding_map.get(idx) for idx in merged.index],
        index=merged.index,
        dtype=object,
    )

    return merged


def _log_extraction_summary(result_df: pd.DataFrame) -> None:
    """Log summary statistics for the extracted embeddings."""
    total_points = len(result_df)
    populated = result_df[EMBEDDING_COLUMN].apply(lambda v: isinstance(v, list)).sum()
    logger.info(
        f"Successfully processed {populated}/{total_points} points with satellite embeddings"
    )
