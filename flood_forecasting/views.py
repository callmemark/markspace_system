from django.shortcuts import render
from .flood_modelling import FloodModel
import rasterio
from rasterio.warp import transform
from rasterio.crs import CRS

import os
from django.conf import settings
from django.http import JsonResponse
from django.views import View


"""
model = FloodModel(
    dem_file     = "s3://markspace-926109361648-ap-southeast-2-an/flood_forecasting/dem.tif",
    precip_file  = "data_inputs/storm_precip_grid.npy",
    landuse_file = "s3://markspace-926109361648-ap-southeast-2-an/flood_forecasting/land_use.tif",
    river_geojson_file = "data_inputs/pasig.geojson",
    model = "HAND",
    mask_bow = False,
    acc_model="DINF", # D8 | MFD | DINF
)
"""





# --------------------------------------------------------------------------
# Query flood data per location
# --------------------------------------------------------------------------
class FloodDepthView(View):
    """ Returns flood depth (in metres) for a given WGS84 lat/lon point.

    Example: /api/flood-depth/?lat=14.5&lon=121.0
    """
    
    # Path to the GeoTIFF relative to project base directory
    TIF_PATH = os.path.join(
        settings.BASE_DIR, 'flood_forecasting', 'data_inputs', 'flood_depth.tif'
    )

    def get(self, request):
        # 1. Read and validate query parameters
        try:
            lat = float(request.GET.get('lat'))
            lon = float(request.GET.get('lon'))
        except (TypeError, ValueError):
            return JsonResponse(
                {'error': 'Missing or invalid lat/lon parameters'}, status=400
            )

        # 2. Open raster and extract value
        try:
            depth = self._get_flood_depth(lat, lon)
            return JsonResponse({
                'lat': lat,
                'lon': lon,
                'depth_m': depth
            })
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=404)
        except Exception as e:
            # Log the real error in production
            return JsonResponse({'error': 'Internal server error'}, status=500)


    def _get_flood_depth(self, lat, lon):
        """ Core logic to query the GeoTIFF.
        Returns float depth or None if the pixel is nodata.
        Raises ValueError if the point is outside the raster extent.
        """
        with rasterio.open(self.TIF_PATH) as src:
            # Transform WGS84 (EPSG:4326) to raster CRS if needed
            if src.crs != CRS.from_epsg(4326):
                # Note: transform returns (x, y) tuples for each coordinate
                xs, ys = transform(CRS.from_epsg(4326), src.crs, [lon], [lat])
                x, y = xs[0], ys[0]
            else:
                x, y = lon, lat

            # Convert map coordinates to pixel row/col
            row, col = src.index(x, y)

            # Check bounds
            if row < 0 or row >= src.height or col < 0 or col >= src.width:
                raise ValueError('Point is outside raster extent')

            # Read the value from band 1
            value = src.read(1)[row, col]

            if value == src.nodata:
                return None
            return float(value)