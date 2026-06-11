
from dotenv import load_dotenv
from rasterio.shutil import copy
from rasterio.enums import Resampling
from pathlib import Path

import os
import rasterio
import time
import numpy as np


load_dotenv()
ROOT_PATH = Path(__file__).parent

FLOOD_DEPTH_PATH = ROOT_PATH / "flood_model_output" / "flood_depth.tif"
PRECIPITATION_PATH = ROOT_PATH / "flood_model_output" / "precip_grid.tif"

if os.getenv("ENVIRONMENT") == "DEV":
    FLOOD_DEPTH_COG = ROOT_PATH / "flood_model_output" / "flood_depth_cog.tif"
    PRECIPITATION_COG = ROOT_PATH / "flood_model_output" / "precipitation_cog.tif"
else:
    FLOOD_DEPTH_COG  = Path("/var/www/media/cogs/flood_depth_cog.tif")
    PRECIPITATION_COG  = Path("/var/www/media/cogs/precipitation_cog.tif")


# --- CREATE PRECIPITATION MAP ----------------------------------------

def initialize_precipitation_map():
    MAP_MAKER = PrecipitaionMapper()
    MAX_RETRIES = 3

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Attempt {attempt}/{MAX_RETRIES}: generating precipitation map…")
            MAP_MAKER.generate_map()
            MAP_MAKER.save_geotiff(tiff_path="flood_model_output/precip_grid.tif")
            break
        except Exception as e:
            print(f"Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                wait = attempt * 30  # 30s, 60s
                print(f"Retrying in {wait}s…")
                time.sleep(wait)
            else:
                print("All attempts failed. Aborting.")
                raise


# --- HELPER FUNCTION -------------------------------------------------
def tif_path(file_key: str):
    bucket = os.getenv('AWS_S3_BUCKET')
    key    = os.getenv(file_key)

    if not bucket or not key:
        raise EnvironmentError('AWS_S3_BUCKET or AWS_S3_FLOOD_KEY is not set in .env')
    return f'/vsis3/{bucket}/{key}'


# ---- Build Cog Files ------
def convert_to_cog(input_path, output_path):
    tmp_path = str(output_path) + '.tmp.tif'

    with rasterio.open(input_path) as src:
        data    = src.read(1).astype(np.float32)
        profile = src.profile.copy()
        profile.update(dtype='float32', driver='GTiff', compress='deflate')

        with rasterio.open(tmp_path, 'w', **profile) as tmp:
            tmp.write(data, 1)

    with rasterio.open(tmp_path, 'r+') as tmp:
        tmp.build_overviews([2, 4, 8, 16, 32], Resampling.average)
        tmp.update_tags(ns='rio_overview', resampling='average')

    with rasterio.open(tmp_path) as tmp:
        profile = tmp.profile.copy()
        profile.update(
            driver='COG',
            compress='deflate',
            predictor=3,
            blocksize=256,
        )
        from rasterio.shutil import copy
        copy(tmp, str(output_path), **profile, copy_src_overviews=True)

    import os
    os.remove(tmp_path)


# ---- Show Cog Files Info ------
def cog_info(path: str):
    with rasterio.open(path) as src:
        print(f"\n{'='*50}")
        print(f"File     : {Path(path).name}")
        print(f"Size     : {src.width} x {src.height}")
        print(f"Dtype    : {src.dtypes[0]}")
        print(f"Overviews: {src.overviews(1)}")
        print(f"CRS      : {src.crs}")
        print(f"Driver   : {src.driver}")
        nodata = src.nodata
        print(f"NoData   : {nodata}")
        print(f"{'='*50}")





if __name__ == "__main__":
    from precip_map_generator import PrecipitaionMapper
    from flood_modelling import FloodModel

    initialize_precipitation_map()
    
    # --- RUN FLOOD MODELLING CALCULATIONS --------------------------------
    FLOOD_MODEL = FloodModel(
        dem_file        = tif_path("AWS_S3_DEM_KEY"),
        precip_file     = ROOT_PATH / "inputs/precip_grid.npy",
        landuse_file    = tif_path("AWS_S3_LANDUSE_KEY"),
        model           = "HAND",
        mask_bow        = True,
        acc_model       = "DINF",
        use_saved_data  = True,
        cache_dir       = ROOT_PATH / ".flood_cache",
    )

    FLOOD_MODEL.output_folder_path = ROOT_PATH / "flood_model_output"
    FLOOD_MODEL.save_outputs = True
    FLOOD_MODEL.run()

    # --- SAVE TO CLOUD OPTMIZE GeoTiff -----------------------------------
    convert_to_cog(FLOOD_DEPTH_PATH, FLOOD_DEPTH_COG)
    convert_to_cog(PRECIPITATION_PATH, PRECIPITATION_COG)

    cog_info(FLOOD_DEPTH_COG)
    cog_info(PRECIPITATION_COG)