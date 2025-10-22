# Hansen Global Forest Change v1.12 (2000–2024)

Dataset: UMD/hansen/global_forest_change_2024_v1_12

- Description: Global forest extent and change derived from annual time-series analysis of Landsat imagery. Includes tree canopy cover for 2000, annual forest loss (2001–2024), forest gain (2000–2012), and reference multispectral composites from the first and last years of the study period. The dataset enables high-resolution tracking of deforestation, regrowth, and forest dynamics over the 21st century, with 30 m pixel size. Forest loss is defined as a stand-replacement disturbance (forest → non-forest), while forest gain represents the opposite (non-forest → forest) within the specified period. Developed by the University of Maryland’s Global Land Analysis and Discovery (GLAD) lab in collaboration with Google, USGS, and NASA.

- Temporal range: 2000–2024 (annual updates; gain fixed for 2000–2012)

- Spatial resolution: 30 m (Landsat native resolution)

- Coverage: Global (land areas)

- Projection: EPSG:4326 (WGS 84 geographic)

- Preprocessing requirements: None for direct use. For AOI analyses, clip to study area and optionally mask to treecover2000 > X %. Loss/gain bands are binary; lossyear is integer-encoded (0 = no loss, 1–24 = 2001–2024). The datamask band can be used to exclude water or no-data pixels.

- GEE Documentation: https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2024_v1_12

- Citation: Hansen, M.C., Potapov, P.V., Moore, R., Hancher, M., et al. (2013). High-resolution global maps of 21st-century forest cover change. Science, 342(6160), 850–853. DOI: 10.1126/science.1244693.

---

## Bands

| Name          | Units | Min | Max | Pixel Size | Wavelength       | Description |
|---------------|-------|-----|-----|------------|------------------|-------------|
| `treecover2000` | %     | 0   | 100 | meters     | None             | Tree canopy cover for year 2000, defined as canopy closure for all vegetation taller than 5 m in height. |
| `loss`        |       |     |     | meters     | None             | Forest loss during the study period, defined as a stand-replacement disturbance (a change from forest to non-forest state). |
| `gain`        |       |     |     | meters     | None             | Forest gain during 2000–2012, defined as the inverse of loss (a non-forest to forest change entirely within the study period). Not updated in later versions. |
| `lossyear`    |       | 0   | 24  | meters     | None             | Year of gross forest cover loss event. Values: `0` = no loss; `1–24` = loss detected primarily in 2001–2024, respectively. |
| `first_b30`   |       |     |     | meters     | 0.63–0.69 µm     | Landsat Red cloud-free composite (Landsat 5/7 band 3, Landsat 8/9 band 4) from the first available year (typically 2000). |
| `first_b40`   |       |     |     | meters     | 0.77–0.90 µm     | Landsat NIR cloud-free composite (Landsat 5/7 band 4, Landsat 8/9 band 5) from the first available year (typically 2000). |
| `first_b50`   |       |     |     | meters     | 1.55–1.75 µm     | Landsat SWIR1 cloud-free composite (Landsat 5/7 band 5, Landsat 8/9 band 6) from the first available year (typically 2000). |
| `first_b70`   |       |     |     | meters     | 2.09–2.35 µm     | Landsat SWIR2 cloud-free composite (Landsat 5/7 band 7, Landsat 8/9 band 7) from the first available year (typically 2000). |
| `last_b30`    |       |     |     | meters     | 0.63–0.69 µm     | Landsat Red cloud-free composite from the last available year (typically the last year of the study period). |
| `last_b40`    |       |     |     | meters     | 0.77–0.90 µm     | Landsat NIR cloud-free composite from the last available year (typically the last year of the study period). |
| `last_b50`    |       |     |     | meters     | 1.55–1.75 µm     | Landsat SWIR1 cloud-free composite from the last available year (typically the last year of the study period). |
| `last_b70`    |       |     |     | meters     | 2.09–2.35 µm     | Landsat SWIR2 cloud-free composite from the last available year (typically the last year of the study period). |
| `datamask`    |       |     |     | meters     | None             | Encodes areas of no data, mapped land surface, and permanent water bodies. |

---

## Bitmask Information

### `loss`
- **Definition:** Forest loss = stand-replacement disturbance (forest → non-forest).  
- **Values:** `0` = no loss, `1` = loss.

### `gain`
- **Definition:** Forest gain = non-forest → forest change entirely within 2000–2012.  
- **Values:** `0` = no gain, `1` = gain. *(Not updated after v1.2)*

---

## `lossyear` Class Table

| Value | Year  |
|-------|-------|
| 0     | No loss |
| 1     | 2001 |
| 2     | 2002 |
| 3     | 2003 |
| 4     | 2004 |
| 5     | 2005 |
| 6     | 2006 |
| 7     | 2007 |
| 8     | 2008 |
| 9     | 2009 |
| 10    | 2010 |
| 11    | 2011 |
| 12    | 2012 |
| 13    | 2013 |
| 14    | 2014 |
| 15    | 2015 |
| 16    | 2016 |
| 17    | 2017 |
| 18    | 2018 |
| 19    | 2019 |
| 20    | 2020 |
| 21    | 2021 |
| 22    | 2022 |
| 23    | 2023 |
| 24    | 2024 |

---

## `datamask` Class Table

| Value | Description |
|-------|-------------|
| 0     | No data |
| 1     | Mapped land surface |
| 2     | Permanent water bodies |


Python example:

```
import ee
import geemap

# Initialize Earth Engine
ee.Initialize()

# Load dataset
dataset = ee.Image('UMD/hansen/global_forest_change_2024_v1_12')

# Tree cover visualization (year 2000)
tree_cover_vis = {
    'bands': ['treecover2000'],
    'min': 0,
    'max': 100,
    'palette': ['black', 'green']
}

# Tree loss year visualization
tree_loss_vis = {
    'bands': ['lossyear'],
    'min': 0,
    'max': 24,
    'palette': ['yellow', 'red']
}

# Create interactive map
Map = geemap.Map()

# Add layers
Map.addLayer(dataset, tree_cover_vis, 'Tree Cover 2000')
Map.addLayer(dataset, tree_loss_vis, 'Tree Loss Year')

# Set initial view (global)
Map.setCenter(0, 0, 2)

# Display map
Map
```

# Copernicus Global Land Cover Layers — CGLS‑LC100 Collection 3 (v3.0.1)
Dataset: COPERNICUS/Landcover/100m/Proba-V-C3/Global

- Description: The Copernicus Global Land Service (CGLS) provides global bio‑geophysical products describing the status and evolution of the land surface. The Dynamic Land Cover map at 100 m (CGLS‑LC100) delivers a global land‑cover product at 100 m spatial resolution with: a primary discrete classification (land‑cover classes), and continuous field layers (fractional cover) for each basic land‑cover type (e.g., tree, shrub, herbaceous, cropland, bare, urban, snow/ice, permanent/seasonal water). The continuous layers are useful to represent heterogeneous landscapes and tailor analyses for applications such as forest and crop monitoring, biodiversity & conservation, climate modeling, and environmental security.

- Temporal range: 2015–2019 (v3.0.1, global). Planned yearly updates from 2020 onward using Sentinel time series.

- Spatial resolution: 100 m (PROBA‑V 100 m basis)

- Coverage: Global land

- Projection: EPSG:4326 (WGS 84 geographic)

- Preprocessing requirements: None for direct use. Optional steps depend on the analysis: Clip to AOI; Use discrete_classification-proba to mask low‑confidence pixels (e.g., ≥50–70%); Prefer fractional cover layers (*-coverfraction) for sub‑pixel estimates; Use change-confidence for interannual change screening (years > 2015).

- GEE Documentation: https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_Landcover_100m_Proba-V-C3_Global

- Citations: Copernicus Global Land Service (CGLS) — LC100 Collection 3 (PROBA‑V 100 m). Overall accuracy reported ~80% (Level‑1) across years 2015–2019.

- Bands: 

    | Name                              | Units | Min | Max | Pixel Size | Description |
    |-----------------------------------|-------|-----|-----|------------|-------------|
    | discrete_classification           |       | 0   | 200 | meters     | Land-cover class (primary scheme). |
    | discrete_classification-proba     | %     | 0   | 100 | meters     | Classification probability (quality indicator) for the discrete class. |
    | forest_type                       |       | 0   | 5   | meters     | Forest type (for pixels with tree cover >1%). |
    | bare-coverfraction                | %     | 0   | 100 | meters     | Fractional cover for bare/sparse vegetation. |
    | crops-coverfraction               | %     | 0   | 100 | meters     | Fractional cover for cropland. |
    | grass-coverfraction               | %     | 0   | 100 | meters     | Fractional cover for herbaceous vegetation. |
    | moss-coverfraction                | %     | 0   | 100 | meters     | Fractional cover for moss & lichen. |
    | shrub-coverfraction               | %     | 0   | 100 | meters     | Fractional cover for shrubland. |
    | tree-coverfraction                | %     | 0   | 100 | meters     | Fractional cover for forest (tree) cover. |
    | snow-coverfraction                | %     | 0   | 100 | meters     | Fractional ground cover for snow & ice. |
    | urban-coverfraction               | %     | 0   | 100 | meters     | Fractional ground cover for built-up. |
    | water-permanent-coverfraction     | %     | 0   | 100 | meters     | Fractional ground cover for permanent water. |
    | water-seasonal-coverfraction      | %     | 0   | 100 | meters     | Fractional ground cover for seasonal water. |
    | data-density-indicator            |       | 0   | 100 | meters     | Input data density indicator used by the algorithm. |
    | change-confidence                 |       | 0   | 3   | meters     | Change confidence (years after 2015). |

- discrete_classification Class Table:

    | Value | Color   | Description |
    |------:|---------|-------------|
    | 0     | #282828 | Unknown. No/insufficient satellite data. |
    | 20    | #ffbb22 | Shrubs. Woody perennials <5 m; evergreen or deciduous. |
    | 30    | #ffff4c | Herbaceous vegetation. <10% tree/shrub cover. |
    | 40    | #f096ff | Cultivated & managed vegetation / agriculture. Temporary crops; perennial woody crops classified under forest/shrub as appropriate. |
    | 50    | #fa0000 | Urban / built-up. Buildings and other man-made structures. |
    | 60    | #b4b4b4 | Bare / sparse vegetation. Exposed soil/sand/rock; never >10% vegetation during the year. |
    | 70    | #f0f0f0 | Snow & ice. Persistent cover throughout the year. |
    | 80    | #0032c8 | Permanent water bodies. Lakes, reservoirs, rivers (fresh or salt water). |
    | 90    | #0096a0 | Herbaceous wetland. Persistent mix of water and vegetation (salt/brackish/fresh). |
    | 100   | #fae6a0 | Moss & lichen. |
    | 111   | #58481f | Closed forest, evergreen needle-leaf. Canopy >70%; needles evergreen year-round. |
    | 112   | #009900 | Closed forest, evergreen broad-leaf. Canopy >70%; broadleaf evergreen. |
    | 113   | #70663e | Closed forest, deciduous needle-leaf. Canopy >70%; seasonal needles. |
    | 114   | #00cc00 | Closed forest, deciduous broad-leaf. Canopy >70%; seasonal broadleaf. |
    | 115   | #4e751f | Closed forest, mixed. |
    | 116   | #007800 | Closed forest, other. Not matching other closed-forest defs. |
    | 121   | #666000 | Open forest, evergreen needle-leaf. Trees 15–70% + shrubs/grass; evergreen needles. |
    | 122   | #8db400 | Open forest, evergreen broad-leaf. Trees 15–70% + shrubs/grass; evergreen broadleaf. |
    | 123   | #8d7400 | Open forest, deciduous needle-leaf. Trees 15–70% + shrubs/grass; seasonal needles. |
    | 124   | #a0dc00 | Open forest, deciduous broad-leaf. Trees 15–70% + shrubs/grass; seasonal broadleaf. |
    | 125   | #929900 | Open forest, mixed. |
    | 126   | #648c00 | Open forest, other. Not matching other open-forest defs. |
    | 200   | #000080 | Oceans, seas. |

- Forest_type Class Table:

    | Value | Color   | Description |
    |------:|---------|-------------|
    | 0     | #282828 | Unknown |
    | 1     | #666000 | Evergreen needle leaf |
    | 2     | #009900 | Evergreen broad leaf |
    | 3     | #70663e | Deciduous needle leaf |
    | 4     | #a0dc00 | Deciduous broad leaf |
    | 5     | #929900 | Mixed forest types |

- Image Properties

    | Name                                   | Type         | Description |
    |----------------------------------------|--------------|-------------|
    | discrete_classification_class_names    | STRING_LIST  | Land cover class names |
    | discrete_classification_class_palette  | STRING_LIST  | Land cover class palette |
    | discrete_classification_class_values   | INT_LIST     | Values of the land cover classification |
    | forest_type_class_names                | STRING_LIST  | Forest cover class names |
    | forest_type_class_palette              | STRING_LIST  | Forest cover class palette |
    | forest_type_class_values               | INT_LIST     | Forest cover class values |
