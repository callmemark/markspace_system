from precip_map_generator import PrecipitaionMapper
from flood_modelling import FloodModel
from dotenv import load_dotenv
import os
from pathlib import Path
import rasterio
from rasterio.shutil import copy
import time


load_dotenv()
ROOT_PATH = Path(__file__).parent



# --- CREATE PRECIPITATION MAP ----------------------------------------
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



# --- RUN FLOOD MODELLING CALCULATIONS --------------------------------
FLOOD_MODEL = FloodModel(
    dem_file        = tif_path("AWS_S3_DEM_KEY"),
    precip_file     = ROOT_PATH / "inputs/precip_grid.npy",
    landuse_file    = tif_path("AWS_S3_LANDUSE_KEY"),
    model           = "HAND",
    mask_bow        = True,
    acc_model       = "D8",
    use_saved_data  = True,
    cache_dir       = ROOT_PATH / ".flood_cache",
)

FLOOD_MODEL.output_folder_path = ROOT_PATH / "flood_model_output"
FLOOD_MODEL.save_outputs = True
FLOOD_MODEL.run()



# --- SAVE TO CLOUD OPTMIZE GeoTiff -----------------------------------
def convert_to_cog(input_path, output_path):
    with rasterio.open(input_path) as src:
        profile = src.profile.copy()
        profile.update(
            driver='COG',
            compress='deflate',          
            predictor=2,                 
            blocksize=256,               
            overview_resampling='nearest',  
        )
        copy(src, output_path, **profile)


FLOOD_DEPTH_PATH = ROOT_PATH / "flood_model_output" / "flood_depth.tif"
PRECIPITATION_PATH = ROOT_PATH / "flood_model_output" / "precip_grid.tif"

#FLOOD_DEPTH_COG = ROOT_PATH / "flood_model_output" / "flood_depth_cog.tif"
#PRECIPITATION_COG = ROOT_PATH / "flood_model_output" / "precipitation_cog.tif"

FLOOD_DEPTH_COG  = Path("/var/www/media/cogs/flood_depth_cog.tif")
PRECIPITATION_COG  = Path("/var/www/media/cogs/precipitation_cog.tif")

convert_to_cog(FLOOD_DEPTH_PATH, FLOOD_DEPTH_COG)
convert_to_cog(PRECIPITATION_PATH, PRECIPITATION_COG)