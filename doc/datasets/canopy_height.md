
# ETH Global Sentinel-2 10m Canopy Height (2020)

- Dataset: "users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1 "

- Description: Global canopy top height for the year 2020 at 10 m ground sampling distance. A probabilistic deep learning model has been developed to retrieve canopy top height from Sentinel-2 images anywhere on Earth. This model, an ensemble of convolutional neural networks (CNN) is trained with sparse supervision from GEDI derived canopy top height data (i.e. estimated RH98 from Lang et al., 2022). Furthermore, the predictive uncertainty of these dense estimates is quantified. That approach reduces the saturation effect commonly encountered when estimating canopy height from optical satellite images allowing to resolve tall canopies with typically high carbon stocks. The global wall-to-wall map is based on Sentinel-2 images taken between May and September 2020. See the project page for more resources and links to download data.

- GEE app link: https://nlang.users.earthengine.app/view/global-canopy-height-2020
- Temporal range = 2020 (single image)
- Projection = EPSG:4326 (WGS 84)
- Coverage = Global
- Spatial resolution = 10m
- Preprocessing requirements = No
- GEE format: ee.Image with two bands:
    - b1 → Canopy height (in meters) 
        - ```var canopy_height = ee.Image("users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1");```
    - b1_SD → Standard deviation (associated uncertainty, also in meters)
        - ```var standard_deviation = ee.Image("users/nlang/ETH_GlobalCanopyHeightSD_2020_10m_v1");```
- GEE Documentation = https://gee-community-catalog.org/projects/canopy/#citation
- paper = https://www.nature.com/articles/s41559-023-02206-6




# High Resolution 1m Global Canopy Height Maps

- Dataset: "projects/sat-io/open-datasets/facebook/meta-canopy-height"

- Description: The Global Canopy Height Maps dataset offers comprehensive insights into tree canopy heights worldwide, providing an overview of tree canopy presence and height for the analysed period (2009-2020), with eighty per cent of the data obtained from imagery acquired between 2018 and 2020. This baseline can be used as a reference for supplementing field-based measurements of carbon in carbon credit monitoring and verification schema. When newer imagery is available, the publicly shared model can be used to detect changes in canopy heights. Developed through a collaboration between Meta and the World Resources Institute, this dataset stands as a cornerstone for understanding forest structure and dynamics. This dataset achieves an unparalleled level of detail through the fusion of state-of-the-art satellite imagery and advanced artificial intelligence techniques. By analyzing satellite imagery spanning from 2009 to 2020, with a focus on data from 2018 to 2020, it provides extensive temporal coverage for tracking changes in canopy height over time across the entire landmass of the planet. Using AI models such as DiNOv2, the dataset enables precise prediction of canopy height with a mean absolute error of 2.8 meters, empowering accurate assessment of carbon stocks and the effectiveness of mitigation strategies.

- GEE app = https://meta-forest-monitoring-okw37.projects.earthengine.app/view/canopyheight
- Temporal range = 2009-2020 (collection of images)
- Spatial resolution = 1m
- Coverage = Global, but organized into individual tiles
- Projection = EPSG:3857
- Preprocessing requirements = No
- GEE Documentation = https://gee-community-catalog.org/projects/canopy/#citation
- paper = https://www.sciencedirect.com/science/article/pii/S003442572300439X