from precip_map_generator import PrecipitaionMapper
from flood_modelling import FloodModel
from dotenv import load_dotenv
import os

import psutil, os, time

process = psutil.Process(os.getpid())
peak_rss = 0

load_dotenv()


def tif_path(file_key: str):
    bucket = os.getenv('AWS_S3_BUCKET')
    key    = os.getenv(file_key)

    if not bucket or not key:
        raise EnvironmentError('AWS_S3_BUCKET or AWS_S3_FLOOD_KEY is not set in .env')

    return f'/vsis3/{bucket}/{key}'



MAP_MAKER = PrecipitaionMapper()
MAP_MAKER.generate_map()



FLOOD_MODEL = FloodModel(
    dem_file        = tif_path("AWS_S3_DEM_KEY"),
    precip_file     = "flood_forecasting/inputs/precip_grid.npy",
    landuse_file    = tif_path("AWS_S3_LANDUSE_KEY"),
    model           = "HAND",
    mask_bow        = True,
    acc_model       = "D8",
    use_saved_data  = False,
    cache_dir       = "flood_forecasting/.flood_cache",
)

FLOOD_MODEL.output_folder_path = "flood_forecasting/flood_model_output"
FLOOD_MODEL.save_outputs = True

FLOOD_MODEL.run()


current = process.memory_info().rss
if current > peak_rss:
    peak_rss = current

print(f"Peak RSS: {peak_rss / 1024**2:.2f} MB")