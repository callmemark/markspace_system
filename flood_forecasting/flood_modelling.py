from PIL import Image
from scipy.ndimage import median_filter, gaussian_filter
from rasterio.warp import reproject, Resampling
from matplotlib.patches import Patch
from matplotlib.colors import ListedColormap, BoundaryNorm
from pysheds.grid import Grid
from pysheds.view import Raster, ViewFinder
from pathlib import Path

import rasterio
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np

if not hasattr(np, 'in1d'):
    np.in1d = np.isin


class FloodModel:
    def __init__(
        self,
        dem_file: str,
        precip_file: str,
        landuse_file: str = None,
        river_geojson_file: str = None,
        model: str = "TWI",
        mask_bow: bool = False,
        acc_model: str = "D8",
        use_saved_data: bool = False,
        cache_dir: str = ".flood_cache",
    ):
        self.dem_file           = dem_file
        self.precip_file        = precip_file
        self.landuse_file       = landuse_file
        self.river_geojson_file = river_geojson_file
        self.model              = model
        self.mask_bow           = mask_bow
        self.acc_model          = acc_model
        self.use_saved_data     = use_saved_data
        self.cache_dir          = Path(cache_dir)

        self.save_outputs       = False
        self.output_folder_path = ''
        self.show_plots         = False

        self.dem_raw            = None
        self.precip_raw         = None
        self.landuse_raw        = None
        self.dem_transform      = None
        self.dem_crs            = None
        self.runoff             = None
        self.runoff_coeff_map   = None
        self.fdir               = None
        self.acc                = None
        self.acc_area           = None
        self.acc_specific       = None
        self.flood_depth        = None
        self.depth_cap          = 10.0
        self.hand               = None
        self.ocean_mask         = None
        self.dem_filled         = None

        self.grid    = None
        self.dem_ps  = None
        self.fdir_ps = None
        self.dirmap  = (64, 128, 1, 2, 4, 8, 16, 32)
        self.dir_offsets = {
            64:  (-1, -1),  # NW
            128: (-1,  0),  # N
            1:   (-1,  1),  # NE
            2:   ( 0,  1),  # E
            4:   ( 1,  1),  # SE
            8:   ( 1,  0),  # S
            16:  ( 1, -1),  # SW
            32:  ( 0, -1),  # W
            0:   None,      # boundary / no data
            -1:  None,      # unresolved flat
            -2:  None,      # pit
        }


        self.INFIL_RATE = {
            10: 25.0, 20: 18.0, 30: 15.0, 40: 12.0,
            50:  5.0, 60: 10.0, 70:  2.0, 80:  0.0,
            90:  8.0, 95: 20.0, 100: 10.0, 0:  10.0,
        }

    # ------------------------------------------------------------------
    #  Cache helpers
    # ------------------------------------------------------------------

    def _cache_path(self, key: str) -> Path:
        stem = Path(self.dem_file).stem
        return self.cache_dir / f"{stem}__{key}.npy"

    def _save_cache(self, key: str, arr: np.ndarray):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(self._cache_path(key), arr)

    def _load_cache(self, key: str) -> np.ndarray | None:
        p = self._cache_path(key)
        if p.exists():
            return np.load(p)
        return None

    def _cached(self, key: str, compute_fn, *args, **kwargs) -> np.ndarray:
        """
        If use_saved_data=True and cache exists → load.
        Otherwise → compute, then save to cache.
        """
        if self.use_saved_data:
            cached = self._load_cache(key)
            if cached is not None:
                print(f"Cache hit     — {key} loaded from {self._cache_path(key)}")
                return cached
            print(f"Cache miss    — {key} not found, computing …")

        result = compute_fn(*args, **kwargs)
        self._save_cache(key, result)
        print(f"Cache saved   — {key} → {self._cache_path(key)}")
        return result

    # ------------------------------------------------------------------
    #  Load & Prepare Data
    # ------------------------------------------------------------------

    def load_dem(self):
        with rasterio.open(self.dem_file) as ds:
            self.dem_transform = ds.transform
            self.dem_crs       = ds.crs
            raw                = ds.read(1).astype(np.float32)
            nodata             = ds.nodata
            if nodata is not None:
                raw[np.isclose(raw, nodata)] = np.nan
        self.dem_raw = raw
        valid = np.isfinite(self.dem_raw)
        print(
            f"DEM loaded    — shape: {self.dem_raw.shape}, "
            f"elev range: {self.dem_raw[valid].min():.1f}–{self.dem_raw[valid].max():.1f} m, "
            f"nodata cells: {(~valid).sum():,}"
        )

    def load_landuse(self):
        self.RUNOFF_COEFFICIENTS = {
            10: 0.30, 20: 0.40, 30: 0.45, 40: 0.55,
            50: 0.85, 60: 0.65, 70: 0.10, 80: 1.00,
            90: 0.70, 95: 0.35, 100: 0.35, 0: 0.50,
        }

        with rasterio.open(self.dem_file) as ds:
            dem_data      = ds.read(1)
            dem_transform = ds.transform
            dem_crs       = ds.crs
            dem_shape     = (ds.height, ds.width)

        def _compute_landuse():
            with rasterio.open(self.landuse_file) as lc_ds:
                lc = np.zeros(dem_shape, dtype=np.uint8)
                reproject(
                    source=rasterio.band(lc_ds, 1),
                    destination=lc,
                    src_transform=lc_ds.transform,
                    src_crs=lc_ds.crs,
                    dst_transform=dem_transform,
                    dst_crs=dem_crs,
                    resampling=Resampling.nearest,
                )
            return lc

        def _compute_rc_map(lc):
            rc = np.full(dem_shape, 0.50, dtype=np.float32)
            for cls in np.unique(lc):
                rc[lc == cls] = self.RUNOFF_COEFFICIENTS.get(int(cls), 0.50)
            ocean = (lc == 80) & (dem_data <= 0.0)
            rc[ocean] = np.nan
            return rc

        self.landuse_raw      = self._cached("landuse",      _compute_landuse)
        self.runoff_coeff_map = self._cached("runoff_coeff", lambda: _compute_rc_map(self.landuse_raw))

        ocean_mask = (self.landuse_raw == 80) & (dem_data <= 0.0)
        self.runoff_coeff_map[ocean_mask] = np.nan
        self.ocean_mask = ocean_mask
        self.water_mask = (self.landuse_raw != 80)

        unique = np.unique(self.landuse_raw)
        print(f"Land use      — shape: {self.landuse_raw.shape}")
        print(f"  Classes     : { {int(c): self.RUNOFF_COEFFICIENTS.get(int(c), 0.50) for c in unique} }")
        print(f"  RC range    — min: {self.runoff_coeff_map.min():.2f}, max: {self.runoff_coeff_map.max():.2f}")

    def load_precip(self, duration_hr: float = 1.0, infiltration_rate_mm_hr: float = 10.0):
        arr = np.load(self.precip_file).squeeze().astype(np.float32)
        self.precip_raw  = np.clip(arr, 0, None)
        self.duration_hr = duration_hr

        precip_rate = self.precip_raw / max(duration_hr, 1e-3)

        if self.runoff_coeff_map is not None and self.landuse_raw is not None:
            infil_map = np.full(self.landuse_raw.shape, infiltration_rate_mm_hr, dtype=np.float32)
            for cls, rate in self.INFIL_RATE.items():
                infil_map[self.landuse_raw == cls] = rate

            self.runoff = self.precip_raw * self.runoff_coeff_map

            infil_fraction = 1.0 - (self.runoff.mean() / (self.precip_raw.mean() + 1e-6))
            print(
                f"Precip loaded — range: {self.precip_raw.min():.1f}–{self.precip_raw.max():.1f} mm "
                f"over {duration_hr:.1f} hr (rate: {precip_rate.mean():.1f} mm/hr mean)\n"
                f"Infiltration  — mean capacity: {infil_map.mean():.1f} mm/hr, "
                f"absorbed: {infil_fraction*100:.0f}%\n"
                f"Runoff        — mean: {self.runoff.mean():.2f} mm"
            )
        else:
            effective_rate   = np.clip(precip_rate - infiltration_rate_mm_hr, 0, None)
            effective_precip = effective_rate * duration_hr
            self.runoff      = effective_precip * 0.65
            print(
                f"Precip loaded — range: {self.precip_raw.min():.1f}–{self.precip_raw.max():.1f} mm "
                f"over {duration_hr:.1f} hr\n"
                f"Warning: no land-use map — global infiltration {infiltration_rate_mm_hr} mm/hr"
            )

        assert self.precip_raw.shape == self.dem_raw.shape, \
            f"Precip shape {self.precip_raw.shape} != DEM shape {self.dem_raw.shape}"

    # ------------------------------------------------------------------
    #  DEM Conditioning
    # ------------------------------------------------------------------

    def prepare_dem(self):
        print("Conditioning DEM with pysheds …")

        def _compute_dem_filled():
            grid   = Grid.from_raster(self.dem_file, nodata=-9999)
            dem    = grid.read_raster(self.dem_file, nodata=-9999)
            filled = grid.resolve_flats(
                grid.fill_depressions(grid.fill_pits(dem)),
                max_iter=int(1e9), eps=1e-12
            )
            return np.array(filled, dtype=np.float32)

        self.dem_filled = self._cached("dem_filled", _compute_dem_filled)

        # pysheds objects must always be rebuilt (they hold grid state)
        self.grid    = Grid.from_raster(self.dem_file, nodata=-9999)
        raw_dem      = self.grid.read_raster(self.dem_file, nodata=-9999)
        pit_filled   = self.grid.fill_pits(raw_dem)
        flooded      = self.grid.fill_depressions(pit_filled)
        self.dem_ps  = self.grid.resolve_flats(flooded, max_iter=int(1e9), eps=1e-12)

        dem_raw_finite = np.nan_to_num(self.dem_raw, nan=0.0)
        delta = self.dem_filled - dem_raw_finite
        print(f"Depression fill — max raised: {delta.max():.2f} m, cells modified: {(delta > 1e-6).sum():,}")


    def preprocess_dem_urban(self, spike_threshold=5.0, window=3):
        """
        Remove single-pixel spikes that act as artificial dams.
        
        spike_threshold: if a pixel is this many metres higher than
                        its neighbourhood median, it's a spike.
        window: neighbourhood size (3 = 3×3 = 8 neighbours)
        """
        from scipy.ndimage import median_filter, minimum_filter

        dem = self.dem_raw.copy()

        # Neighbourhood median
        dem_median = median_filter(dem, size=window)

        # Spike mask: pixel is much higher than surroundings
        spike_mask = (dem - dem_median) > spike_threshold

        # Replace spikes with local median
        dem[spike_mask] = dem_median[spike_mask]

        n_spikes = spike_mask.sum()
        print(f"Spike removal — {n_spikes:,} spike pixels fixed "
            f"(threshold={spike_threshold}m, window={window}×{window})")

        # Optional: also fill isolated low pits (negative spikes)
        dem_min = minimum_filter(dem, size=window)
        pit_mask = (dem_median - dem) > spike_threshold
        dem[pit_mask] = dem_median[pit_mask]
        print(f"Pit removal   — {pit_mask.sum():,} pit pixels fixed")

        self.dem_raw = dem


    # ------------------------------------------------------------------
    #  Flow Direction & Accumulation
    # ------------------------------------------------------------------

    def build_flow_model(self):
        routing_map = {"D8": None, "MFD": "mfd", "DINF": "dinf"}
        routing     = routing_map.get(self.acc_model)

        if routing:
            self.fdir_ps = self.grid.flowdir(self.dem_ps, routing=routing, dirmap=self.dirmap)
        else:
            self.fdir_ps = self.grid.flowdir(self.dem_ps, dirmap=self.dirmap)

        def _fdir_array():
            return np.array(self.fdir_ps, dtype=np.int16)

        self.fdir = self._cached(f"fdir_{self.acc_model}", _fdir_array)
        routable  = (self.fdir > 0).sum()
        print(f"Flow direction — {self.acc_model}, {routable:,}/{self.fdir.size:,} routable ({routable/self.fdir.size*100:.1f}%)")

    def compute_accumulation_pyshed_d8(self):
        vf = self.fdir_ps.viewfinder

        def _acc():
            rr = Raster(self.runoff.astype(np.float64), viewfinder=vf)
            return np.array(
                self.grid.accumulation(self.fdir_ps, weights=rr, dirmap=self.dirmap, nodata_out=np.nan),
                dtype=np.float32
            )

        def _acc_area():
            ones = Raster(np.ones(self.runoff.shape, dtype=np.float64), viewfinder=vf)
            return np.array(
                self.grid.accumulation(self.fdir_ps, weights=ones, dirmap=self.dirmap, nodata_out=np.nan),
                dtype=np.float32
            )

        # acc depends on runoff (precip-driven) so it is NOT cached
        self.acc      = _acc()
        self.acc_area = self._cached("acc_area_D8", _acc_area)
        self.acc_specific = np.where(self.acc_area > 0, self.acc / self.acc_area, 0.0).astype(np.float32)

        print(
            f"Accumulation  — raw max: {self.acc.max():.1f} mm·cells\n"
            f"Specific acc  — max: {self.acc_specific.max():.1f} mm, "
            f"95th: {np.percentile(self.acc_specific[np.isfinite(self.acc_specific)], 95):.1f} mm, "
            f"99th: {np.percentile(self.acc_specific[np.isfinite(self.acc_specific)], 99):.1f} mm"
        )

    def compute_accumulation_mfd(self):
        print("Compute Accumulation model: MFD")
        vf = self.dem_ps.viewfinder
        rr = Raster(self.runoff.astype(np.float64), viewfinder=vf)
        self.acc = np.array(
            self.grid.accumulation(self.fdir_ps, weights=rr, routing='mfd', dirmap=self.dirmap, nodata_out=np.nan),
            dtype=np.float32
        )
        print(f"Accumulation  — MFD max: {self.acc.max():.1f} mm, 99th: {np.percentile(self.acc[np.isfinite(self.acc)], 99):.1f} mm")

    def compute_accumulation_dinf(self):
        print("Compute Accumulation model: D-Infinity")
        vf = self.dem_ps.viewfinder
        rr = Raster(self.runoff.astype(np.float64), viewfinder=vf)
        self.acc = np.array(
            self.grid.accumulation(self.fdir_ps, weights=rr, routing='dinf', dirmap=self.dirmap, nodata_out=np.nan),
            dtype=np.float32
        )
        print(f"Accumulation  — D-Inf max: {self.acc.max():.1f} mm, 99th: {np.percentile(self.acc[np.isfinite(self.acc)], 99):.1f} mm")

    # ------------------------------------------------------------------
    #  Flood Depth Models
    # ------------------------------------------------------------------

    def twi_estimate_flood_depth(self):
        dy, dx    = np.gradient(self.dem_filled)
        slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
        tan_slope = np.clip(np.tan(slope_rad), 0.001, None)
        twi       = np.clip(np.log((self.acc + 1.0) / tan_slope), 0, None)
        twi_max   = np.percentile(twi, 99)
        self.flood_depth = np.clip(twi / (twi_max + 1e-6) * self.depth_cap, 0, self.depth_cap)
        print(f"Flood depth   — TWI range: {twi.min():.2f}–{twi.max():.2f}, 99th pct depth: {np.percentile(self.flood_depth, 99):.2f} m")


    def hand_estimate_flood_depth(self, channel_threshold=None, stage_scale=500.0):
        ROUTING_MAP = {"D8": "d8", "MFD": "mfd", "DINF": "dinf"}
        routing     = ROUTING_MAP.get(self.acc_model, "d8")

        if channel_threshold is None:
            channel_threshold = np.percentile(self.acc[np.isfinite(self.acc)], 99)

        channel_mask = self.acc >= channel_threshold
        n_channels   = channel_mask.sum()
        print(f"HAND          — routing: {routing}, threshold: {channel_threshold:.1f} mm, channels: {n_channels:,}")

        def _compute_hand():
            vf        = self.dem_ps.viewfinder
            dem_r     = Raster(self.dem_filled, viewfinder=vf)
            bool_vf   = ViewFinder(affine=vf.affine, shape=vf.shape, crs=vf.crs, nodata=False)
            channel_r = Raster(channel_mask.astype(np.bool_), viewfinder=bool_vf)
            hand_ps   = self.grid.compute_hand(
                self.fdir_ps, dem_r, channel_r,
                dirmap=self.dirmap, routing=routing, nodata_out=np.nan,
            )
            hand = np.clip(np.array(hand_ps, dtype=np.float32), 0, None)
            untraced = ~np.isfinite(hand)
            if untraced.any():
                hand[untraced] = np.nan
            return hand

        self.hand = self._cached(f"hand_{self.acc_model}", _compute_hand)
        print(f"HAND          — range: {self.hand.min():.2f}–{self.hand.max():.2f} m, mean: {self.hand.mean():.2f} m")

        # --- Flood depth via log-scale HAND comparison ---
        acc_stage     = self.acc_specific if hasattr(self, 'acc_specific') and self.acc_specific is not None else self.acc
        acc_stage_log = np.log1p(acc_stage / stage_scale)
        hand_log      = np.log1p(np.where(np.isfinite(self.hand), self.hand, 0))

        flood = np.clip(acc_stage_log - hand_log, 0, None)

        valid_flood   = flood[flood > 0]
        flood_99      = np.percentile(valid_flood, 99) if valid_flood.size > 0 else 1.0
        self.flood_depth = np.clip(
            flood / (flood_99 + 1e-6) * self.depth_cap, 0, self.depth_cap
        )

        flooded = (self.flood_depth > 0).sum()
        print(
            f"HAND flood    — flooded: {flooded:,} ({flooded/self.acc.size*100:.1f}%), "
            f"max: {self.flood_depth.max():.2f} m, "
            f"mean(flooded): {self.flood_depth[self.flood_depth > 0].mean():.2f} m"
        )


    def smooth_flood_depth(self, method="median", size=5, sigma=1.0):
        if method == "median":
            self.flood_depth = median_filter(self.flood_depth, size=size)
        elif method == "gaussian":
            self.flood_depth = gaussian_filter(self.flood_depth, sigma=sigma)
        self.flood_depth = np.clip(self.flood_depth, 0, self.depth_cap)
        print(f"Smoothed      — method={method}, size={size}")

    # ------------------------------------------------------------------
    #  Export
    # ------------------------------------------------------------------

    def _resolve_path(self, out_path: str) -> str:
        filename = Path(out_path).name
        if hasattr(self, 'output_folder_path') and self.output_folder_path:
            folder = Path(self.output_folder_path)
            folder.mkdir(parents=True, exist_ok=True)
            return str(folder / filename)
        return filename

    def _write_tif(self, data, out_path, description, units):
        with rasterio.open(self.dem_file) as src:
            profile = src.profile.copy()
        profile.update(dtype="float32", count=1, compress="lzw", nodata=-9999.0)
        with rasterio.open(out_path, "w", **profile) as dst:
            out = np.where(np.isfinite(data), data, -9999.0).astype(np.float32)
            dst.write(out, 1)
            dst.update_tags(
                description=description, units=units,
                precip_src=self.precip_file,
                landuse_src=self.landuse_file or "none",
                runoff_method="per-pixel ESA WorldCover" if self.landuse_file else "global fraction",
            )
        print(f"TIF saved     — {out_path}  [{data[np.isfinite(data)].min():.2f}–{data[np.isfinite(data)].max():.2f} {units}]")

    def save_tif(self, out_path="flood_accumulation.tif"):
        self._write_tif(self.acc, self._resolve_path(out_path), "D8 flow accumulation (runoff-weighted)", "mm")

    def save_flood_depth_tif(self, out_path="flood_depth.tif"):
        resolved = self._resolve_path(out_path)
        print("Saving on resolved path:", resolved)
        self._write_tif(self.flood_depth, resolved, f"Flood depth proxy ({self.model} model)", "relative_m")

    def save_twi_tif(self, out_path="twi_depth.tif"):
        self._write_tif(self.flood_depth, self._resolve_path(out_path), "TWI flood depth proxy", "relative_m")

    def save_hand_tif(self, out_path="hand.tif"):
        self._write_tif(self.hand, self._resolve_path(out_path), "Height Above Nearest Drainage (HAND)", "metres")

    def save_flood_map(self, out_path="flood_depth.png"):
        max_val = self.flood_depth.max()
        arr = (self.flood_depth / (max_val if max_val > 0 else 1) * 255).astype(np.uint8)
        Image.fromarray(arr, mode="L").save(out_path)
        print(f"PNG saved     — {out_path}")

    # ------------------------------------------------------------------
    #  Visualisation
    # ------------------------------------------------------------------

    def plot(self, figsize=(12, 10)):
        fig, axes = plt.subplots(2, 2, figsize=figsize)
        axes = axes.flatten()

        dy, dx = np.gradient(self.dem_filled)
        slope  = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))

        panels = [
            (self.dem_ps,        "terrain", "DEM — Elevation (m)"),
            (slope,               "gray",   "Slope (degrees)"),
            (np.log1p(self.acc),  "Blues",  f"Flow Accumulation {self.acc_model} - log(mm)"),
            (self.flood_depth,    "jet",    f"Flood Depth proxy {self.model} — (m)"),
        ]
        for ax, (data, cmap, title) in zip(axes, panels):
            d  = np.where(np.isfinite(data), data, 0)
            im = ax.imshow(d, cmap=cmap)
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            ax.set_title(title, fontsize=11)
            ax.axis("off")

        plt.suptitle("Flood Model — Metro Manila (24hr precip)", fontsize=14)
        plt.tight_layout()
        plt.show()

    def plot_landuse(self):
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        classes    = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
        colors_lc  = ['#006400','#ffbb22','#ffff4c','#f096ff','#fa0000',
                       '#b4b4b4','#f0f0f0','#0064c8','#0096a0','#00cf75','#fae6a0']
        labels     = ['Tree','Shrub','Grass','Crop','Built-up','Bare','Snow','Water','Wetland','Mangrove','Moss']
        cmap_c     = ListedColormap(colors_lc)
        norm       = BoundaryNorm(classes + [classes[-1] + 1], cmap_c.N)

        axes[0].imshow(self.landuse_raw, cmap=cmap_c, norm=norm, interpolation='nearest')
        legend = [Patch(facecolor=c, label=f"{v} {l}") for v, c, l in zip(classes, colors_lc, labels)]
        axes[0].legend(handles=legend, loc='lower right', fontsize=7, ncol=2, framealpha=0.8)
        axes[0].set_title("ESA WorldCover Land Use")
        axes[0].axis('off')

        im1 = axes[1].imshow(self.runoff_coeff_map, cmap='RdYlGn_r', vmin=0.2, vmax=1.0)
        plt.colorbar(im1, ax=axes[1], fraction=0.046, pad=0.04, label='Runoff coefficient')
        axes[1].set_title("Per-pixel Runoff Coefficient")
        axes[1].axis('off')

        plt.suptitle("Land Use → Runoff Mapping", fontsize=13)
        plt.tight_layout()
        plt.show()


    def diagnose_hand(self, r, c, max_trace=200):
        """
        Trace the D8 path from pixel (r,c) to its assigned channel.
        Prints every step so you can see where the chain breaks.
        """
        offsets = {
            64:(-1,-1), 128:(-1,0), 1:(-1,1),
            2:( 0, 1),   4:( 1,1), 8:( 1,0),
            16:( 1,-1),  32:( 0,-1)
        }
        rows, cols = self.dem_filled.shape
        print(f"\nTracing from ({r},{c}) elev={self.dem_filled[r,c]:.2f}m "
            f"HAND={self.hand[r,c]:.2f}m acc={self.acc[r,c]:.1f}mm")

        path = [(r, c)]
        for step in range(max_trace):
            cr, cc = path[-1]
            d = int(self.fdir[cr, cc])
            offset = offsets.get(d, None)

            is_channel = self.acc[cr, cc] >= np.percentile(self.acc, 99)
            print(f"  step {step:3d}: ({cr:4d},{cc:4d}) "
                f"elev={self.dem_filled[cr,cc]:.2f}m "
                f"fdir={d:4d} "
                f"acc={self.acc[cr,cc]:.1f}mm "
                f"{'← CHANNEL' if is_channel else ''}"
                f"{'← SINK (fdir=-1)' if d == -1 else ''}"
                f"{'← SINK (fdir=0)' if d == 0 else ''}")

            if is_channel:
                print(f"  → Reached channel at step {step}")
                break
            if offset is None:
                print(f"  → CHAIN BROKEN at step {step} — fdir={d}, no downstream")
                break

            dr, dc = offset
            nr, nc = cr + dr, cc + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                print(f"  → Hit boundary at step {step}")
                break
            path.append((nr, nc))
        else:
            print(f"  → Max trace depth reached ({max_trace}) — likely circular")

    # ------------------------------------------------------------------
    #  Runner
    # ------------------------------------------------------------------

    def run(self):
        self.load_dem()
        self.preprocess_dem_urban(spike_threshold=5.0)
        self.prepare_dem()
        self.load_landuse()
        self.load_precip(duration_hr=24)

        self.build_flow_model()

        if self.acc_model == "MFD":
            self.compute_accumulation_mfd()
        elif self.acc_model == "DINF":
            self.compute_accumulation_dinf()
        elif self.acc_model == "D8":
            self.compute_accumulation_pyshed_d8()
        else:
            raise ValueError(f"Invalid acc_model '{self.acc_model}'. Expected 'MFD', 'DINF', or 'D8'.")

        if self.model == "HAND":
            self.hand_estimate_flood_depth()
        elif self.model == "TWI":
            self.twi_estimate_flood_depth()
        else:
            raise ValueError(f"Invalid model '{self.model}'. Expected 'HAND' or 'TWI'.")

        self.smooth_flood_depth()

        if self.mask_bow:
            land_mask = self.water_mask if self.landuse_file else np.isfinite(self.dem_raw)
            self.acc         = np.where(land_mask, self.acc,        np.nan)
            self.flood_depth = np.where(land_mask, self.flood_depth, np.nan)
            if self.hand is not None:
                self.hand    = np.where(land_mask, self.hand,       np.nan)

        if self.save_outputs:
            self.save_tif()
            self.save_flood_depth_tif()
            self.save_hand_tif() if self.model == "HAND" else self.save_twi_tif()
            self.save_flood_map()

        if self.show_plots:
            if self.landuse_file:
                self.plot_landuse()
            self.plot()