
import numpy as np
import pandas as pd
import xarray as xr
import dynamical_catalog
import matplotlib.pyplot as plt
from pathlib import Path
import rasterio
from rasterio.transform import from_origin


class PrecipitaionMapper():
    def __init__(self, output_path: str = "inputs/precip_grid.npy"):
        self.ROOT_PATH = Path(__file__).parent
        self.BBOX = (120.882568, 14.413400, 121.294556, 14.807413)
        self.output_path = output_path
        self.DEM_SHAPE = (1418, 1483)
    

    def generate_map(self):
        print("Connecting to dynamical.org cloud archive...")
        ds = dynamical_catalog.open("ecmwf-ifs-ens-forecast-15-day-0-25-degree")

        latest_init = ds.init_time.values[-1]
        print(f"Using latest forecast initialization run: {pd.to_datetime(latest_init).strftime('%Y-%m-%d %H:%M UTC')}")

        print("Slicing bounding box and pulling raw data into local memory...")
        lon_min, lat_min, lon_max, lat_max = self.BBOX
        lead_steps = ds.lead_time.sel(lead_time=slice(pd.Timedelta(hours=3), pd.Timedelta(hours=24)))

        padded_coarse_lazy = ds["precipitation_surface"].sel(
            init_time=latest_init,
            lead_time=lead_steps,
            latitude=slice(lat_max + 0.5, lat_min - 0.5),
            longitude=slice(lon_min - 0.5, lon_max + 0.5)
        )

        local_coarse_data = padded_coarse_lazy.compute()

        print("Calculating 24h accumulation and ensemble mean locally...")
        precip_24h_accum = (local_coarse_data * 10800).sum(dim="lead_time")
        precip_ensemble_mean = precip_24h_accum.mean(dim="ensemble_member")
        print(f"Interpolating local grid to target grid shape {self.DEM_SHAPE}...")

        target_lons = np.linspace(lon_min, lon_max, self.DEM_SHAPE[1])
        target_lats = np.linspace(lat_max, lat_min, self.DEM_SHAPE[0]) 

        high_res_ds = precip_ensemble_mean.interp(latitude=target_lats, longitude=target_lons, method="cubic")
        precip_grid = high_res_ds.values

        precip_grid = np.clip(precip_grid, 0, None)

        script_dir = Path(__file__).parent
        input_dir = script_dir / "inputs"
        input_dir.mkdir(exist_ok=True)
        output_path = input_dir / "precip_grid.npy"
        
        np.save(str(output_path), precip_grid)
        print(f"Saved final precipitation grid to {self.output_path}, shape {precip_grid.shape}")
        print(f"Precipitation range: {precip_grid.min():.2f} – {precip_grid.max():.2f} mm")


    def save_geotiff(self, precip_grid=None, tiff_path=None):
        if precip_grid is None:
            print(f"Loading grid from {self.output_path} ...")
            precip_grid = np.load(self.ROOT_PATH / self.output_path)

        if tiff_path is None:
            tiff_path = self.output_path.replace('.npy', '.tif')

        tiff_path = self.ROOT_PATH / tiff_path

        lon_min, lat_min, lon_max, lat_max = self.BBOX
        height, width = self.DEM_SHAPE

        pixel_width = (lon_max - lon_min) / width
        pixel_height = (lat_max - lat_min) / height
        transform = from_origin(lon_min, lat_max, pixel_width, pixel_height)

        with rasterio.open(
            tiff_path,
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=1,
            dtype=precip_grid.dtype,
            crs='EPSG:4326',
            transform=transform,
        ) as dst:
            dst.write(precip_grid, 1)

        print(f"Saved GeoTIFF to {tiff_path}")
        print(f"Grid shape: {precip_grid.shape}, CRS: EPSG:4326")

    
    def plot_map(self):
        precip_grid = np.load("precip_grid.npy")

        plt.figure(figsize=(10, 8))
        plt.imshow(precip_grid, cmap='Blues', origin='upper')
        plt.colorbar(label='Precipitation (mm)')
        plt.title('Interpolated Precipitation Grid')
        plt.xlabel('Column index')
        plt.ylabel('Row index')
        plt.tight_layout()
        plt.show()


