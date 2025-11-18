# WorldClim Bioclimatic Variables v1
Dataset: WORLDCLIM/V1/BIO 

- Description: WorldClim V1 Bioclim provides bioclimatic variables that are derived from the monthly temperature and rainfall in order to generate more biologically meaningful values.The bioclimatic variables represent annual trends (e.g., mean annual temperature, annual precipitation), seasonality (e.g., annual range in temperature and precipitation), and extreme or limiting environmental factors (e.g., temperature of the coldest and warmest month, and precipitation of the wet and dry quarters). The bands scheme follows that of ANUCLIM, except that for temperature seasonality the standard deviation was used because a coefficient of variation does not make sense with temperatures between -1 and 1. WorldClim version 1 was developed by Robert J. Hijmans, Susan Cameron, and Juan Parra, at the Museum of Vertebrate Zoology, University of California, Berkeley, in collaboration with Peter Jones and Andrew Jarvis (CIAT), and with Karen Richardson (Rainforest CRC).

- Temporal range: 1960–1991 (historical climatology)

- Spatial resolution: ~1 km (30 arc-seconds)

- Coverage: Global (land areas)

- Projection: EPSG:4326 (WGS 84 geographic)

- Preprocessing requirements: Some bands need rescale.

- GEE Documentation: https://developers.google.com/earth-engine/datasets/catalog/WORLDCLIM_V1_BIO

- Citation: Hijmans, R.J., et al. (2005). Very high resolution interpolated climate surfaces for global land areas. International Journal of Climatology 25: 1965–1978. DOI: 10.1002/joc.1276

- Bands:

    | Name  | Units                      | Min     | Max      | Scale | Pixel Size | Description |
    |-------|----------------------------|---------|----------|-------|------------|-------------|
    | bio01 | °C                         | -29*    | 32*      | 0.1   | meters     | Annual mean temperature |
    | bio02 | °C                         | 0.9*    | 21.4*    | 0.1   | meters     | Mean diurnal range (mean of monthly (max temp - min temp)) |
    | bio03 | %                          | 7*      | 96*      |       | meters     | Isothermality (bio02 / bio07 × 100) |
    | bio04 | °C                         | 0.62*   | 227.21*  | 0.01  | meters     | Temperature seasonality (standard deviation × 100) |
    | bio05 | °C                         | -9.6*   | 49*      | 0.1   | meters     | Max temperature of warmest month |
    | bio06 | °C                         | -57.3*  | 25.8*    | 0.1   | meters     | Min temperature of coldest month |
    | bio07 | °C                         | 5.3*    | 72.5*    | 0.1   | meters     | Temperature annual range (bio05 − bio06) |
    | bio08 | °C                         | -28.5*  | 37.8*    | 0.1   | meters     | Mean temperature of wettest quarter |
    | bio09 | °C                         | -52.1*  | 36.6*    | 0.1   | meters     | Mean temperature of driest quarter |
    | bio10 | °C                         | -14.3*  | 38.3*    | 0.1   | meters     | Mean temperature of warmest quarter |
    | bio11 | °C                         | -52.1*  | 28.9*    | 0.1   | meters     | Mean temperature of coldest quarter |
    | bio12 | mm                         | 0*      | 11401*   |       | meters     | Annual precipitation |
    | bio13 | mm                         | 0*      | 2949*    |       | meters     | Precipitation of wettest month |
    | bio14 | mm                         | 0*      | 752*     |       | meters     | Precipitation of driest month |
    | bio15 | Coefficient of Variation   | 0*      | 265*     |       | meters     | Precipitation seasonality |
    | bio16 | mm                         | 0*      | 8019*    |       | meters     | Precipitation of wettest quarter |
    | bio17 | mm                         | 0*      | 2495*    |       | meters     | Precipitation of driest quarter |
    | bio18 | mm                         | 0*      | 6090*    |       | meters     | Precipitation of warmest quarter |
    | bio19 | mm                         | 0*      | 5162*    |       | meters     | Precipitation of coldest quarter |

    \* estimated min or max value


Python example:

```
import ee

# Initialize the Earth Engine API
ee.Initialize()

# Load the WorldClim bioclimatic dataset
dataset = ee.Image("WORLDCLIM/V1/BIO")

# Select 'bio01' (Annual Mean Temperature) and apply scale factor 0.1
annual_mean_temperature = dataset.select('bio01').multiply(0.1)

# Visualization parameters
vis_params = {
    'min': -23,
    'max': 30,
    'palette': ['blue', 'purple', 'cyan', 'green', 'yellow', 'red']
}

# Define the map center
center_coords = [52.4, 71.7]  # latitude, longitude
zoom_level = 3

# Use geemap to display in Python
import geemap
Map = geemap.Map(center=center_coords, zoom=zoom_level)
Map.addLayer(annual_mean_temperature, vis_params, 'Annual Mean Temperature')
Map
```