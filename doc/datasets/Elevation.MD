# SRTM Digital Elevation Data Version 4
Dataset: CGIAR/SRTM90_V4

- Description: Shuttle Radar Topography Mission (SRTM) Digital Elevation Model (DEM) at 3‑arc‑second (~90 m) resolution, void‑filled and mosaicked by CGIAR‑CSI (Version 4). Provides near‑global land elevation referenced to WGS84 ellipsoid/EGM96 geoid (values in meters above mean sea level). Ideal as a baseline for topography, hydrology (flow direction/accumulation), slope/aspect, relief, and terrain‑correction in ecological and remote‑sensing workflows.

- Temporal range: February 2000 (single-epoch DEM)

- Spatial resolution: ~90 m (3 arc‑seconds)

- Coverage: Near‑global land (≈ 60° N to 56° S)

- Projection: EPSG:4326 (WGS 84 geographic)

- Preprocessing requirements: None for basic elevation use. (Already void‑filled and mosaicked.) Optional: clip to AOI; derive slope/aspect/hillshade with ee.Terrain.products; reproject to desired CRS/scale for analysis.

- GEE Documentation: https://developers.google.com/earth-engine/datasets/catalog/CGIAR_SRTM90_V4
- Citations: Jarvis, A., H.I. Reuter, A. Nelson, E. Guevara. 2008. Hole-filled SRTM for the globe Version 4, available from the CGIAR-CSI SRTM 90m Database: https://srtm.csi.cgiar.org.


Python example:
```
dataset = ee.Image('CGIAR/SRTM90_V4')
elevation = dataset.select('elevation')
#slope = ee.Terrain.slope(elevation)

# Visualization parameters
elevation_vis = {
    'min': 0.0,
    'max': 1000.0,
    'palette': ['0000ff', '00ffff', 'ffff00', 'ff0000', 'ffffff']
}

# Create a map
Map = geemap.Map()
Map.setCenter(-6.746, 46.529, 4)  # lon, lat, zoom
Map.addLayer(elevation, elevation_vis, 'DEM')

# Display map
Map
```


# Copernicus GLO-30
Dataset: COPERNICUS/DEM/GLO30

- Description: The Copernicus DEM is a Digital Surface Model (DSM) which represents the surface of the Earth including buildings, infrastructure and vegetation. This DEM is derived from an edited DSM named WorldDEM&trade, i.e. flattening of water bodies and consistent flow of rivers has been included. Editing of shore- and coastlines, special features such as airports and implausible terrain structures has also been applied. The WorldDEM product is based on the radar satellite data acquired during the TanDEM-X Mission, which is funded by a Public Private Partnership between the German State, represented by the German Aerospace Centre (DLR) and Airbus Defence and Space. More details are available in the dataset documentation. Earth Engine asset has been ingested from the DGED files.

- Temporal range: 2011–2015

- Spatial resolution: 30 m

- Coverage: Global

- Projection: EPSG:4326 (WGS 84)

- Preprocessing requirements: None.

- GEE Documentation: https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30

- Reference: European Space Agency (ESA).

- Bands

    | Name  | Min | Max | Pixel size | Description |
    |-------|-----|-----|------------|-------------|
    | **DEM** | — | — | square | Digital Surface Model |
    | **EDM** | 0 | 13 | square | The edit data mask indicates all DEM pixels that were modified during the terrain and hydrographic editing process. |
    | **FLM** | 0 | 101 | square | The fill mask is primarily created during the terrain editing process. |
    | **HEM** | — | — | square | The height error mask represents the corresponding height error for each DEM pixel in the form of the standard deviation derived from interferometric coherence and geometric considerations. |
    | **WBM** | 0 | 3 | square | The water body mask shows all DEM pixels classified as water and edited according to the categories "Ocean", "Lake", or "River". |


Python example:

```
import ee
import geemap

# Initialize Earth Engine
ee.Initialize()

# Load the dataset
dataset = ee.ImageCollection('COPERNICUS/DEM/GLO30')
elevation = dataset.select('DEM')

# Visualization parameters
elevation_vis = {
    'min': 0.0,
    'max': 1000.0,
    'palette': ['0000ff', '00ffff', 'ffff00', 'ff0000', 'ffffff']
}

# Create a map
Map = geemap.Map()
Map.setCenter(-6.746, 46.529, 4)  # lon, lat, zoom
Map.addLayer(elevation, elevation_vis, 'DEM')

# Display map
Map
```
