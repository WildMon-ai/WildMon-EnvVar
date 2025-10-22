# ESA WorldCover 10 m v200
Dataset: ESA/WorldCover/v200

- Description: The European Space Agency (ESA) WorldCover 10 m 2021 product provides a global land cover map for 2021 at 10 m resolution based on Sentinel-1 and Sentinel-2 data. The WorldCover product comes with 11 land cover classes and has been generated in the framework of the ESA WorldCover project, part of the 5th Earth Observation Envelope Programme (EOEP-5) of the European Space Agency.

- Temporal range: 2021

- Spatial resolution: 10 m

- Coverage: Global land areas

- Projection: EPSG:4326 (WGS 84)

- Preprocessing requirements: Despite using the collection method, it only has the year 2021 and should be called like this ```ee.ImageCollection('ESA/WorldCover/v200').first()```.

- GEE Documentation: https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200

- Reference: Zanaga, D., Van De Kerchove, R., et al. (2021). ESA WorldCover 10 m 2020.

- Map Class Table


    | Value | Color   | Description              |
    |-------|---------|--------------------------|
    | 10    | #006400 | Tree cover               |
    | 20    | #ffbb22 | Shrubland                 |
    | 30    | #ffff4c | Grassland                 |
    | 40    | #f096ff | Cropland                  |
    | 50    | #fa0000 | Built-up                  |
    | 60    | #b4b4b4 | Bare / sparse vegetation  |
    | 70    | #f0f0f0 | Snow and ice              |
    | 80    | #0064c8 | Permanent water bodies    |
    | 90    | #0096a0 | Herbaceous wetland        |
    | 95    | #00cf75 | Mangroves                 |
    | 100   | #fae6a0 | Moss and lichen           |


Python example code
```
# Load the dataset and get the first image (2020 global map)
dataset = ee.ImageCollection('ESA/WorldCover/v200').first()

# Visualization parameters
visualization = {
    'bands': ['Map'],
}

# Create the map
Map = geemap.Map()
Map.centerObject(dataset)
Map.addLayer(dataset, visualization, 'Landcover')

# Display the map
Map
```

- Note: Can be used to Calculate distance to forest. Use a function to add a new band to the image which represents the distance from a specific value of all pixels in the image. Use the "Map" band which contains landcover classes and the value "10" which represents forest, so the new band shows distance to forest.


# MCD12Q1.061 MODIS Land Cover Type Yearly Global 500 m
Dataset: MODIS/061/MCD12Q1

- Description: The Terra and Aqua combined Moderate Resolution Imaging Spectroradiometer (MODIS) Land Cover Type (MCD12Q1) Version 6.1 provides global land cover maps at yearly intervals (2001–present). Post-processing integrates ancillary data and expert knowledge to refine class boundaries. Additional property layers follow the FAO Land Cover Classification System (LCCS) for land cover, land use, and surface hydrology, plus confidence layers, quality control (QC), and a land–water mask. Classifications are generated using supervised algorithms applied to MODIS Terra and Aqua reflectance data. Five different classification schemes are included:

    - International Geosphere-Biosphere Programme (IGBP)

    - University of Maryland (UMD)

    - Leaf Area Index (LAI)

    - BIOME-Biogeochemical Cycles (BGC)

    - Plant Functional Types (PFT)

- Temporal range: 2001-01-01 – 2024-01-01

- Spatial resolution: 500 m

- Coverage: Global

- Projection: Sinusoidal projection (MODIS standard)

- Cadence: Annual

- Preprocessing requirements: If your goal is to extract vegetation cover using MODIS MCD12Q1 (the source of these tables), the best band will depend on how you plan to classify and group vegetation:

    🔹 Option 1 — General classification (forest, shrub, grass, etc.)
Recommended band: LC_Type1 (IGBP classification)

        Why:

            It is the most widely used and documented scheme.

            Contains separate classes for deciduous, evergreen forests, shrublands, grasslands, croplands, water, snow, and ice.

            Easy to filter only vegetated classes (values 1 to 11).

    🔹 Option 2 — Agricultural vs. natural separation
Recommended band: LC_Type2 (UMD classification)

        Why:

            Useful when you need to clearly differentiate between natural vegetation and croplands.

            Provides well-defined classes for agricultural vs. natural land cover.

    🔹 Option 3 — Functional vegetation types
Recommended band: LC_Type5 (Plant Functional Types)

        Why:

            Best if you need functional types (broadleaf trees, conifers, shrubs, cereal croplands, broadleaf croplands, etc.).

            Excellent for ecological studies and process modeling.

    💡 Quick summary:

        To map general vegetation → LC_Type1

        To separate agriculture vs. natural → LC_Type2

        To characterize vegetation functionally → LC_Type5

- Dataset provider: NASA LP DAAC at the USGS EROS Center

- GEE Documentation: [MODIS/061/MCD12Q1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MCD12Q1#description)

- Reference: Friedl, M.A., et al., 2022. MODIS Collection 6.1 Land Cover Type Product.

## Bands

| Name                   | Units | Min | Max | Pixel Size | Description |
|------------------------|-------|-----|-----|------------|-------------|
| LC_Type1               |       |     |     | meters     | Land Cover Type 1: Annual International Geosphere-Biosphere Programme (IGBP) classification |
| LC_Type2               |       |     |     | meters     | Land Cover Type 2: Annual University of Maryland (UMD) classification |
| LC_Type3               |       |     |     | meters     | Land Cover Type 3: Annual Leaf Area Index (LAI) classification |
| LC_Type4               |       |     |     | meters     | Land Cover Type 4: Annual BIOME-Biogeochemical Cycles (BGC) classification |
| LC_Type5               |       |     |     | meters     | Land Cover Type 5: Annual Plant Functional Types classification |
| LC_Prop1_Assessment    | %     | 0   | 100 | meters     | LCCS1 land cover layer confidence |
| LC_Prop2_Assessment    | %     | 0   | 100 | meters     | LCCS2 land use layer confidence |
| LC_Prop3_Assessment    | %     | 0   | 100 | meters     | LCCS3 surface hydrology layer confidence |
| LC_Prop1               |       |     |     | meters     | FAO-Land Cover Classification System 1 (LCCS1) land cover layer |
| LC_Prop2               |       |     |     | meters     | FAO-LCCS2 land use layer |
| LC_Prop3               |       |     |     | meters     | FAO-LCCS3 surface hydrology layer |
| QC                     |       |     |     | meters     | Product quality flags |
| LW                     |       |     |     | meters     | Binary land (class 2) / water (class 1) mask derived from MOD44W |

---

## LC_Type1 Class Table

| Value | Color     | Description |
|-------|-----------|-------------|
| 1     | #05450a   | Evergreen Needleleaf Forests: dominated by evergreen conifer trees (canopy >2m). Tree cover >60%. |
| 2     | #086a10   | Evergreen Broadleaf Forests: dominated by evergreen broadleaf and palmate trees (canopy >2m). Tree cover >60%. |
| 3     | #54a708   | Deciduous Needleleaf Forests: dominated by deciduous needleleaf (larch) trees (canopy >2m). Tree cover >60%. |
| 4     | #78d203   | Deciduous Broadleaf Forests: dominated by deciduous broadleaf trees (canopy >2m). Tree cover >60%. |
| 5     | #009900   | Mixed Forests: dominated by neither deciduous nor evergreen (40-60% of each) tree type (canopy >2m). Tree cover >60%. |
| 6     | #c6b044   | Closed Shrublands: dominated by woody perennials (1-2m height) >60% cover. |
| 7     | #dcd159   | Open Shrublands: dominated by woody perennials (1-2m height) 10-60% cover. |
| 8     | #dade48   | Woody Savannas: tree cover 30-60% (canopy >2m). |
| 9     | #fbff13   | Savannas: tree cover 10-30% (canopy >2m). |
| 10    | #b6ff05   | Grasslands: dominated by herbaceous annuals (<2m). |
| 11    | #27ff87   | Permanent Wetlands: permanently inundated lands with 30-60% water cover and >10% vegetated cover. |
| 12    | #c24f44   | Cropland. |
| 13    | #a5a5a5   | Urban and Built-up Lands: at least 30% impervious surface area including building materials, asphalt and vehicles. |
| 14    | #ff6d4c   | Cropland/Natural Vegetation Mosaics: mosaics of small-scale cultivation 40-60% with natural tree, shrub, or herbaceous vegetation. |
| 15    | #69fff8   | Permanent Snow and Ice: at least 60% of area is covered by snow and ice for at least 10 months of the year. |
| 16    | #f9ffa4   | (sand, rock, soil) areas with less than 10% vegetation. |
| 17    | #1c0dff   | Water Bodies: at least 60% of area is covered by permanent water bodies. |

---

## LC_Type2 Class Table

| Value | Color     | Description |
|-------|-----------|-------------|
| 0     | #1c0dff   | Water Bodies: at least 60% of area is covered by permanent water bodies. |
| 1     | #05450a   | Evergreen Needleleaf Forests: dominated by evergreen conifer trees (canopy >2m). Tree cover >60%. |
| 2     | #086a10   | Evergreen Broadleaf Forests: dominated by evergreen broadleaf and palmate trees (canopy >2m). Tree cover >60%. |
| 3     | #54a708   | Deciduous Needleleaf Forests: dominated by deciduous needleleaf (larch) trees (canopy >2m). Tree cover >60%. |
| 4     | #78d203   | Deciduous Broadleaf Forests: dominated by deciduous broadleaf trees (canopy >2m). Tree cover >60%. |
| 5     | #009900   | Mixed Forests: dominated by neither deciduous nor evergreen (40-60% of each) tree type (canopy >2m). Tree cover >60%. |
| 6     | #c6b044   | Closed Shrublands: dominated by woody perennials (1-2m height) >60% cover. |
| 7     | #dcd159   | Open Shrublands: dominated by woody perennials (1-2m height) 10-60% cover. |
| 8     | #dade48   | Woody Savannas: tree cover 30-60% (canopy >2m). |
| 9     | #fbff13   | Savannas: tree cover 10-30% (canopy >2m). |
| 10    | #b6ff05   | Grasslands: dominated by herbaceous annuals (<2m). |
| 11    | #27ff87   | Permanent Wetlands: permanently inundated lands with 30-60% water cover and >10% vegetated cover. |
| 12    | #c24f44   | Cropland. |
| 13    | #a5a5a5   | Urban and Built-up Lands: at least 30% impervious surface area including building materials, asphalt and vehicles. |
| 14    | #ff6d4c   | Cropland/Natural Vegetation Mosaics: mosaics of small-scale cultivation 40-60% with natural tree, shrub, or herbaceous vegetation. |
| 15    | #f9ffa4   | Non-Vegetated Lands: at least 60% of area is non-vegetated barren (sand, rock, soil) or permanent snow and ice with less than 10% vegetation. |


## LC_Type5 Class Table

| Value | Color   | Description |
|-------|---------|-------------|
| 0     | #1c0dff | Water Bodies: at least 60% of area is covered by permanent water bodies. |
| 1     | #05450a | Evergreen Needleleaf Trees: dominated by evergreen conifer trees (>2 m). Tree cover >10%. |
| 2     | #086a10 | Evergreen Broadleaf Trees: dominated by evergreen broadleaf and palmate trees (>2 m). Tree cover >10%. |
| 3     | #54a708 | Deciduous Needleleaf Trees: dominated by deciduous needleleaf (larch) trees (>2 m). Tree cover >10%. |
| 4     | #78d203 | Deciduous Broadleaf Trees: dominated by deciduous broadleaf trees (>2 m). Tree cover >10%. |
| 5     | #dcd159 | Shrub: shrub (1–2 m) cover >10%. |
| 6     | #b6ff05 | Not cultivated. |
| 7     | #dade48 | Cereal Croplands: dominated by herbaceous annuals (<2 m). At least 60% cultivated cereal crops. |
| 8     | #c24f44 | Broadleaf Croplands: dominated by herbaceous annuals (<2 m). At least 60% cultivated broadleaf crops. |
| 9     | #a5a5a5 | Urban and Built-up Lands: at least 30% impervious surface area including building materials, asphalt, and vehicles. |
| 10    | #69fff8 | Permanent Snow and Ice: at least 60% of area is covered by snow and ice for at least 10 months of the year. |
| 11    | #f9ffa4 | Non‑Vegetated Lands: at least 60% of area is non‑vegetated barren (sand, rock, soil) with <10% vegetation. |
