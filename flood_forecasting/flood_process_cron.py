from precip_map_generator import PrecipitaionMapper
from flood_modelling import FloodModel
from dotenv import load_dotenv
import os
from pathlib import Path



load_dotenv()


def tif_path(file_key: str):
    bucket = os.getenv('AWS_S3_BUCKET')
    key    = os.getenv(file_key)

    if not bucket or not key:
        raise EnvironmentError('AWS_S3_BUCKET or AWS_S3_FLOOD_KEY is not set in .env')

    return f'/vsis3/{bucket}/{key}'


ROOT_PATH = Path(__file__).parent
MAP_MAKER = PrecipitaionMapper()
MAP_MAKER.generate_map()


def get_project_root():
    return Path(__file__).parent.parent


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