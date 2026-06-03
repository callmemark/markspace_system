import os
import rasterio
import rasterio.windows
from rasterio.crs import CRS
from pyproj import transform
from dotenv import load_dotenv
from django.views import View
from django.http import JsonResponse

load_dotenv()


# --------------------------------------------------------------------------
# Query flood data per location — streams GeoTIFF directly from S3
# --------------------------------------------------------------------------
class FloodDepthView(View):
    """Returns flood depth (in metres) for a given WGS84 lat/lon point.

    Reads the GeoTIFF directly from S3 via GDAL's /vsis3/ virtual filesystem.
    Credentials and S3 path are loaded from .env via python-dotenv.

    Example: /api/flood-depth/?lat=14.5&lon=121.0
    """

    @property
    def tif_path(self):
        bucket = os.getenv('AWS_S3_BUCKET')
        key    = os.getenv('AWS_S3_FLOOD_KEY')

        if not bucket or not key:
            raise EnvironmentError('AWS_S3_BUCKET or AWS_S3_FLOOD_KEY is not set in .env')

        return f'/vsis3/{bucket}/{key}'

    def get(self, request):
        try:
            lat = float(request.GET.get('lat'))
            lon = float(request.GET.get('lon'))
        except (TypeError, ValueError):
            return JsonResponse(
                {'error': 'Missing or invalid lat/lon parameters'}, status=400
            )

        try:
            depth = self._get_flood_depth(lat, lon)
            return JsonResponse({'lat': lat, 'lon': lon, 'depth_m': depth})
        except EnvironmentError as e:
            return JsonResponse({'error': str(e)}, status=500)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=404)
        except Exception as e:
            return JsonResponse({'error': f'Internal server error: {e}'}, status=500)

    def _get_flood_depth(self, lat, lon):
        """Streams only the pixel block needed from S3 — not the full file."""
        with rasterio.open(self.tif_path) as src:
            if src.crs != CRS.from_epsg(4326):
                xs, ys = transform(CRS.from_epsg(4326), src.crs, [lon], [lat])
                x, y = xs[0], ys[0]
            else:
                x, y = lon, lat

            row, col = src.index(x, y)

            if row < 0 or row >= src.height or col < 0 or col >= src.width:
                raise ValueError('Point is outside raster extent')

            window = rasterio.windows.Window(col, row, 1, 1)
            value = src.read(1, window=window)[0, 0]

            if value == src.nodata:
                return None
            return float(value)