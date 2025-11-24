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