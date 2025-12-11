import ee
import os
import geopandas as gpd

def export_rasters_to_gdrive(
    image: ee.Image,
    region: ee.Geometry,
    file_name_prefix: str,
    # gdrive_folder: str = "EE_exports", # Currently not very useful as each band is exported to its own folder even if they have same folder name
    scale: int = 30,
    crs: str = "EPSG:4326",
    file_format: str = "GeoTIFF",
):
    """
    Export each band of a multi-band Earth Engine image as a separate GeoTIFF to Google Drive.

    Parameters:
    - image: An ee.Image (can be a result of ee.Image.cat([...])).
    - region: AOI geometry to clip each band to.
    - file_name_prefix: Prefix for exported filenames.
    # - gdrive_folder: Drive folder to save exports.
    - scale: Export resolution in meters.
    - crs: Export CRS, e.g. 'EPSG:4326'.
    - file_format: File format (GeoTIFF by default).

    Returns:
    - List of ee.batch.Task objects (started).
    """
    tasks: list[ee.batch.Task] = []
    band_names = image.bandNames().getInfo()
    
    if not band_names:
        print("⚠️ No bands found in the provided image. Export aborted.")
        return tasks
    for band in band_names:
        single_band = (
            image.select(band)
                 .reproject(ee.Projection(crs).atScale(scale))
                 .clip(region)
        )

        file_name = f"{file_name_prefix}_{band}"

        task = ee.batch.Export.image.toDrive(
            image=single_band,
            description=file_name,
            folder=file_name,
            fileNamePrefix=file_name,
            region=region,
            scale=scale,
            crs=crs,
            fileFormat=file_format,
            maxPixels=1e13,
        )
        task.start()
        tasks.append(task)

        print(f"✅ Started export for band: {band} -> {file_name}")

    print("🔗 Monitor progress at: https://code.earthengine.google.com/tasks")

def export_csv(df, output_path: str):
    """Export a pandas DataFrame to CSV."""
    df.to_csv(output_path, index=False)
    print(f"\nResult saved to {output_path}")

def export_hexagrid_results(gdf: gpd.GeoDataFrame, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    gdf.to_csv(output_path + ".csv", index=False)
    gdf.to_file(output_path + ".shp")
    gdf.to_file(output_path + ".gpkg")
    print(f"\nResult saved to {output_path}")