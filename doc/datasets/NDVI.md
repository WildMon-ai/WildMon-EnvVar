# MOD13A1.061 Terra Vegetation Indices 16-Day Global 500m

Dataset: MODIS/061/MOD13A1

- Description: 16-day Terra/MODIS Vegetation Indices (VIs) at 500 m providing:

    - NDVI (continuity with AVHRR NDVI)

    - EVI (reduces soil/background effects and keeps sensitivity in dense canopy; uses blue band to mitigate residual atmospheric effects). Images also include red/NIR/blue/MIR surface reflectances (used to compute the VIs), observation geometry (solar/view angles, relative azimuth), composite DayOfYear, and QA layers (DetailedQA bitmask and SummaryQA class). Surface reflectances are atmospherically corrected and masked for water, clouds, heavy aerosols, and cloud shadows. Each 16-day composite stores the best-quality observation per pixel.

- Temporal range: 2000-02-18 to 2025-09-30 (Terra, Collection 6.1)

- Spatial resolution: 500 m

- Coverage: Global land

- Projection: MODIS Integerized Sinusoidal (per 10°×10° tile)

- Preprocessing requirements:

    - Apply scale factors (NDVI/EVI/reflectances × 0.0001).

    - Quality control: quick mask with SummaryQA == 0 (good), or decode DetailedQA bits for stricter filtering (cloud/snow/shadow/aerosol/land-water).

    - Optional: mosaic tiles over AOI; reproject/clip as needed.

- Bands (key):

    - NDVI (scaled int16: −2000..10000 → ×0.0001)

    - EVI (scaled int16: −2000..10000 → ×0.0001)

    - DetailedQA (uint16 bitmask; VI quality/usefulness, aerosol, clouds/snow/shadow, land/water)

    - SummaryQA (0=good, 1=marginal, 2=snow/ice, 3=cloudy)

    - sur_refl_b01/b02/b03/b07 (red/NIR/blue/MIR reflectances, ×0.0001)

    - ViewZenith, SolarZenith, RelativeAzimuth, DayOfYear

- GEE Documentation: https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13A1

- Citations: Didan, K. (2015). MOD13A1 MODIS/Terra Vegetation Indices 16-Day L3 Global 500 m SIN Grid V006. NASA LP DAAC. Huete, A. et al. (2002) EVI. Remote Sensing of Environment.

Python example:
```
import ee, geemap
ee.Initialize()

# Load 16-day MOD13A1 and filter a period
col = (ee.ImageCollection('MODIS/061/MOD13A1')
       .filterDate('2022-01-01', '2022-03-01'))

# Helper to keep only good-quality pixels (SummaryQA == 0)
def mask_good(img):
    good = img.select('SummaryQA').eq(0)
    return img.updateMask(good)

col_good = col.map(mask_good)

# Work with NDVI (apply scale factor 0.0001 for analysis; for display keep raw 0..10000)
ndvi_raw = col_good.select('NDVI').median()

ndvi_vis = {
    'min': 0,
    'max': 9000,
    'palette': [
        'ffffff','ce7e45','df923d','f1b555','fcd163','99b718','74a901',
        '66a000','529400','3e8601','207401','056201','004c00','023b01',
        '012e01','011d01','011301'
    ]
}

Map = geemap.Map()
Map.setCenter(6.746, 46.529, 2)
Map.addLayer(ndvi_raw, ndvi_vis, 'MOD13A1 NDVI (16-day, median, good only)')

# If you need NDVI in [-1, 1] for computations:
ndvi_unitless = ndvi_raw.multiply(0.0001).rename('NDVI_unitless')
# Example: export or further analysis...
Map.addLayer(ndvi_unitless, {'min': 0, 'max': 1}, 'NDVI (0..1)')

Map

```

# USGS Landsat 9 Level 2, Collection 2, Tier 1
Dataset: LANDSAT/LC09/C02/T1_L2
- Description: This dataset contains atmospherically corrected surface reflectance (SR) and land surface temperature (LST) derived from Landsat 9 OLI/TIRS sensor data.
Each image includes: 
    - 5 visible and near-infrared (VNIR) bands

    - 2 short-wave infrared (SWIR) bands (orthorectified surface reflectance)

    - 1 thermal infrared (TIR) band (orthorectified surface temperature) Intermediate and QA bands are also included. SR products are generated with the Land Surface Reflectance Code (LaSRC). LST products are produced using a single-channel algorithm from RIT and NASA JPL. Images are delivered as overlapping scenes (~170 km × 183 km) using a standard reference grid.

    - PROCESSING_LEVEL = L2SP → Both SR and LST bands present

    - PROCESSING_LEVEL = L2SR → Only SR bands present (LST bands empty)

    - Note: LST requires both optical and thermal data plus ASTER NDVI for temporal adjustment. Nighttime scenes cannot be processed to LST. Missing ASTER GED emissivity data results in permanent LST gaps.

- Temporal range: 2021-present (Landsat 9 operational period)

- Spatial resolution: 30 m (all bands)

- Coverage: Global (land and coastal zones, except persistent cloud areas)

- Projection: UTM zone per scene (WGS 84 / UTM)

- Preprocessing requirements:
    None for basic reflectance/temperature use.

    Cloud masking using QA_PIXEL bitmasks (NDVI)

    Conversion to Top-of-Atmosphere (TOA) reflectance if required

    Scaling factors for reflectance and temperature bands must be applied

- GEE Documentation:
https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC09_C02_T1_L2

- Citations: Cook, M., et al. (2014). Cloud and Shadow Detection in Landsat Data. USGS Landsat Collection 2 Product Guide: https://www.usgs.gov/landsat-missions/landsat-collection-2 ASTER GED dataset info: https://lpdaac.usgs.gov/products/astt03v003/


Python example:

```
dataset = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2').filterDate(
    '2022-01-01', '2022-02-01'
)


# Applies scaling factors.
def apply_scale_factors(image):
  optical_bands = image.select('SR_B.').multiply(0.0000275).add(-0.2)
  thermal_bands = image.select('ST_B.*').multiply(0.00341802).add(149.0)
  return image.addBands(optical_bands, None, True).addBands(
      thermal_bands, None, True
  )


dataset = dataset.map(apply_scale_factors)

visualization = {
    'bands': ['SR_B4', 'SR_B3', 'SR_B2'],
    'min': 0.0,
    'max': 0.3,
}

m = geemap.Map()
m.set_center(-114.2579, 38.9275, 8)
m.add_layer(dataset, visualization, 'True Color (432)')
m
```


# Harmonized Sentinel-2 MSI: MultiSpectral Instrument, Level-2A (SR)
Dataset: "COPERNICUS/S2_SR_HARMONIZED"

- Description: After 2022-01-25, Sentinel-2 scenes with PROCESSING_BASELINE '04.00' or above have their DN (value) range shifted by 1000. The HARMONIZED collection shifts data in newer scenes to be in the same range as in older scenes. Sentinel-2 is a wide-swath, high-resolution, multi-spectral imaging mission supporting Copernicus Land Monitoring studies, including the monitoring of vegetation, soil and water cover, as well as observation of inland waterways and coastal areas. The Sentinel-2 L2 data are downloaded from CDSE. They were computed by running sen2cor. WARNING: 2017-2018 L2 coverage in the EE collection is not yet global. The assets contain 12 UINT16 spectral bands representing SR scaled by 10000 (unlike in L1 data, there is no B10). There are also several more L2-specific bands (see band list for details). QA60 is a bitmask band that contained rasterized cloud mask polygons until 2022-01-25, when these polygons stopped being produced. Starting 2024-02-28, legacy-consistent QA60 bands are constructed from the MSK_CLASSI cloud classification bands. For more details, see the full explanation of how cloud masks are computed. EE asset ids for Sentinel-2 L2 assets have the following format: COPERNICUS/S2_SR/20151128T002653_20151128T102149_T56MNN. Here the first numeric part represents the sensing date and time, the second numeric part represents the product generation date and time, and the final 6-character string is a unique granule identifier indicating its UTM grid reference (see MGRS). For datasets to assist with cloud and/or cloud shadow detection, see COPERNICUS/S2_CLOUD_PROBABILITY and GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED.

- Temporal range: 2015-06-27 → present (coverage not global in 2017-2018)

- Spatial resolution: 10 m, 20 m, 60 m (band-dependent)

- Coverage: Global land

- Projection: UTM/WGS84 (MGRS tile-based)

- Preprocessing requirements: None for basic use; values must be scaled by 0.0001 for reflectance. Optionally mask clouds/shadows using QA60 or MSK_CLASSI.

- Related datasets: COPERNICUS/S2_CLOUD_PROBABILITY (cloud probability masks); GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED (harmonized SR + cloud scores)

- GEE Documentation: https://developers.google.com/earth-engine/datasets/catalog/
COPERNICUS_S2_SR

- Bands:

    ## Sentinel-2 L2 SR Bands

    | Name       | Units | Min  | Max  | Scale   | Pixel Size | Wavelength                              | Description |
    |------------|-------|------|------|---------|------------|------------------------------------------|-------------|
    | B1         |       |      |      | 0.0001  | 60 m       | 443.9 nm (S2A) / 442.3 nm (S2B)          | Aerosols |
    | B2         |       |      |      | 0.0001  | 10 m       | 496.6 nm (S2A) / 492.1 nm (S2B)          | Blue |
    | B3         |       |      |      | 0.0001  | 10 m       | 560 nm (S2A) / 559 nm (S2B)              | Green |
    | B4         |       |      |      | 0.0001  | 10 m       | 664.5 nm (S2A) / 665 nm (S2B)            | Red |
    | B5         |       |      |      | 0.0001  | 20 m       | 703.9 nm (S2A) / 703.8 nm (S2B)          | Red Edge 1 |
    | B6         |       |      |      | 0.0001  | 20 m       | 740.2 nm (S2A) / 739.1 nm (S2B)          | Red Edge 2 |
    | B7         |       |      |      | 0.0001  | 20 m       | 782.5 nm (S2A) / 779.7 nm (S2B)          | Red Edge 3 |
    | B8         |       |      |      | 0.0001  | 10 m       | 835.1 nm (S2A) / 833 nm (S2B)            | NIR |
    | B8A        |       |      |      | 0.0001  | 20 m       | 864.8 nm (S2A) / 864 nm (S2B)            | Red Edge 4 |
    | B9         |       |      |      | 0.0001  | 60 m       | 945 nm (S2A) / 943.2 nm (S2B)            | Water vapor |
    | B11        |       |      |      | 0.0001  | 20 m       | 1613.7 nm (S2A) / 1610.4 nm (S2B)        | SWIR 1 |
    | B12        |       |      |      | 0.0001  | 20 m       | 2202.4 nm (S2A) / 2185.7 nm (S2B)        | SWIR 2 |
    | AOT        |       |      |      | 0.001   | 10 m       | None                                     | Aerosol Optical Thickness |
    | WVP        | cm    |      |      | 0.001   | 10 m       | None                                     | Water Vapor Pressure — height the water would occupy if condensed into liquid and spread evenly across the column |
    | SCL        |       | 1    | 11   |         | 20 m       | None                                     | Scene Classification Map (`No Data` value of 0 masked out) |
    | TCI_R      |       |      |      |         | 10 m       | None                                     | True Color Image — Red channel |
    | TCI_G      |       |      |      |         | 10 m       | None                                     | True Color Image — Green channel |
    | TCI_B      |       |      |      |         | 10 m       | None                                     | True Color Image — Blue channel |
    | MSK_CLDPRB |       | 0    | 100  |         | 20 m       | None                                     | Cloud Probability Map *(missing in some products)* |
    | MSK_SNWPRB |       | 0    | 100  |         | 10 m       | None                                     | Snow Probability Map *(missing in some products)* |
    | QA10       |       |      |      |         | 10 m       | None                                     | Always empty |
    | QA20       |       |      |      |         | 20 m       | None                                     | Always empty |
    | QA60       |       |      |      |         | 60 m       | None                                     | Cloud mask *(masked out between 2022-01-25 and 2024-02-28 inclusive)* |


    ## QA60 Bitmask

    | Bits   | Meaning         | Value | Description |
    |--------|-----------------|-------|-------------|
    | 0–9    | Unused          |       | — |
    | 10     | Opaque clouds   | 0     | No opaque clouds |
    |        |                 | 1     | Opaque clouds present |
    | 11     | Cirrus clouds   | 0     | No cirrus clouds |
    |        |                 | 1     | Cirrus clouds present |

    ---

    ## Classification Bands

    | Name                  | Pixel Size | Wavelength | Description |
    |-----------------------|------------|------------|-------------|
    | MSK_CLASSI_OPAQUE     | 60 m       | None       | Opaque clouds classification band *(0 = no clouds, 1 = clouds)*. Masked out before February 2024. |
    | MSK_CLASSI_CIRRUS     | 60 m       | None       | Cirrus clouds classification band *(0 = no clouds, 1 = clouds)*. Masked out before February 2024. |
    | MSK_CLASSI_SNOW_ICE   | 60 m       | None       | Snow/ice classification band *(0 = no snow/ice, 1 = snow/ice)*. |

    ## SCL Class Table

    | Value | Color   | Description                                    |
    |-------|---------|------------------------------------------------|
    | 1     | #ff0004 | Saturated or defective                         |
    | 2     | #868686 | Dark Area Pixels                               |
    | 3     | #774b0a | Cloud Shadows                                  |
    | 4     | #10d22c | Vegetation                                     |
    | 5     | #ffff52 | Bare Soils                                     |
    | 6     | #0000ff | Water                                          |
    | 7     | #818181 | Clouds Low Probability / Unclassified          |
    | 8     | #c0c0c0 | Clouds Medium Probability                      |
    | 9     | #f1f1f1 | Clouds High Probability                        |
    | 10    | #bac5eb | Cirrus                                         |
    | 11    | #52fff9 | Snow / Ice                                     |


Python example:

```
def mask_s2_clouds(image):
  """Masks clouds in a Sentinel-2 image using the QA band.

  Args:
      image (ee.Image): A Sentinel-2 image.

  Returns:
      ee.Image: A cloud-masked Sentinel-2 image.
  """
  qa = image.select('QA60')

  # Bits 10 and 11 are clouds and cirrus, respectively.
  cloud_bit_mask = 1 << 10
  cirrus_bit_mask = 1 << 11

  # Both flags should be set to zero, indicating clear conditions.
  mask = (
      qa.bitwiseAnd(cloud_bit_mask)
      .eq(0)
      .And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
  )

  return image.updateMask(mask).divide(10000)


dataset = (
    ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterDate('2020-01-01', '2020-01-30')
    # Pre-filter to get less cloudy granules.
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    .map(mask_s2_clouds)
)

visualization = {
    'min': 0.0,
    'max': 0.3,
    'bands': ['B4', 'B3', 'B2'],
}

m = geemap.Map()
m.set_center(83.277, 17.7009, 12)
m.add_layer(dataset.mean(), visualization, 'RGB')
m

```