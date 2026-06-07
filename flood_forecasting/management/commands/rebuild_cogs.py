from ...flood_process_cron import (
        convert_to_cog, 
        cog_info, 
        FLOOD_DEPTH_COG, 
        PRECIPITATION_COG,
        FLOOD_DEPTH_PATH,
        PRECIPITATION_PATH
    )


from django.core.management.base import BaseCommand
from ...flood_process_cron import (
    convert_to_cog, 
    cog_info, 
    FLOOD_DEPTH_COG, 
    PRECIPITATION_COG,
    FLOOD_DEPTH_PATH,
    PRECIPITATION_PATH
)

class Command(BaseCommand):
    help = 'Rebuild Cloud Optimized GeoTIFFs for flood depth and precipitation'

    def handle(self, *args, **options):
        self.stdout.write('Converting flood depth to COG...')
        convert_to_cog(FLOOD_DEPTH_PATH, FLOOD_DEPTH_COG)
        self.stdout.write(self.style.SUCCESS('Flood depth COG created.'))

        self.stdout.write('Converting precipitation to COG...')
        convert_to_cog(PRECIPITATION_PATH, PRECIPITATION_COG)
        self.stdout.write(self.style.SUCCESS('Precipitation COG created.'))

        self.stdout.write('COG info:')
        cog_info(FLOOD_DEPTH_COG)
        cog_info(PRECIPITATION_COG)

        self.stdout.write(self.style.SUCCESS('All done.'))