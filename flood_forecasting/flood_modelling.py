from PIL import Image
from scipy.ndimage import median_filter, gaussian_filter
from rasterio.warp import reproject, Resampling
from matplotlib.patches import Patch
from matplotlib.colors import ListedColormap, BoundaryNorm
from pysheds.grid import Grid
from pysheds.view import Raster, ViewFinder

import rasterio
import math
import matplotlib.pyplot as plt
import numpy as np
if not hasattr(np, 'in1d'):
    np.in1d = np.isin




class FloodModel:
    def __init__(self, dem_file:str, precip_file:str, landuse_file:str = None, model:str ="TWI", mask_bow:bool = False, acc_model:str ="D8"):
        self.dem_file:str       = dem_file
        self.precip_file:str    = precip_file
        self.landuse_file:str   = landuse_file
        self.model:str          = model
        self.mask_bow:bool      = mask_bow
        self.acc_model:str      = acc_model 
        
        self.dem_raw: np.array  = None
        self.precip_raw         = None
        self.landuse_raw        = None

        self.dem_transform      = None
        self.dem_crs            = None
        self.runoff             = None
        self.runoff_coeff_map   = None 
        self.fdir               = None
        self.acc                = None
        self.flood_depth        = None
        self.depth_cap          = 10.0
        self.hand               = None

        self.grid      = None  
        self.dem_ps    = None  
        self.fdir_ps   = None  
        self.dirmap    = (64, 128, 1, 2, 4, 8, 16, 32) 

    
    

    # ------------------------------------------------------------------
    #  LOADIN & PREPARING DATA 
    # ------------------------------------------------------------------

    def load_dem(self) -> None:
        with rasterio.open(self.dem_file) as dem_dataset:
            self.dem_transform = dem_dataset.transform
            self.dem_crs = dem_dataset.crs

            raw: np.array = dem_dataset.read(1).astype(np.float32)
            nodata: int | float | None = dem_dataset.nodata

            if nodata is not None:
                raw[np.isclose(raw, nodata)] = np.nan

            self.dem_raw = raw
        
        valid: np.array = np.isfinite(self.dem_raw)

        print(
            f"DEM loaded    — shape: {self.dem_raw.shape}, "
            f"elev range: {self.dem_raw[valid].min():.1f}-"
            f"{self.dem_raw[valid].max():.1f} m, "
            f"nodata cells: {(~valid).sum():,}"
        )


    def load_landuse(self):
        
        self.RUNOFF_COEFFICIENTS = {
            10:  0.30,  # Tree cover
            20:  0.40,  # Shrubland
            30:  0.45,  # Grassland
            40:  0.55,  # Cropland
            50:  0.85,  # Built-up
            60:  0.65,  # Bare/sparse vegetation
            70:  0.10,  # Snow and ice
            80:  1.00,  # Permanent water bodies
            90:  0.70,  # Herbaceous wetland
            95:  0.35,  # Mangroves
            100: 0.35,  # Moss and lichen
            0:   0.50,  # fallback
        }

       
        with rasterio.open(self.dem_file) as dem_ds:
            dem_profile = dem_ds.profile
            dem_crs     = dem_ds.crs
            dem_transform = dem_ds.transform
            dem_shape   = (dem_ds.height, dem_ds.width)

        with rasterio.open(self.landuse_file) as lc_ds:
            lc_resampled = np.zeros(dem_shape, dtype=np.uint8)
            reproject(
                source        = rasterio.band(lc_ds, 1),
                destination   = lc_resampled,
                src_transform = lc_ds.transform,
                src_crs       = lc_ds.crs,
                dst_transform = dem_transform,
                dst_crs       = dem_crs,
                resampling    = Resampling.nearest,
            )
        
        print(f"Land use loaded — original shape: ({lc_ds.height}, {lc_ds.width}) → resampled to: {lc_resampled.shape}")

        rc_map = np.full(dem_shape, 0.50, dtype=np.float32)
        unique_classes = np.unique(lc_resampled)

        for cls in unique_classes:
            coeff = self.RUNOFF_COEFFICIENTS.get(int(cls), 0.50)
            rc_map[lc_resampled == cls] = coeff

        self.landuse_raw      = lc_resampled
        self.runoff_coeff_map = rc_map
        self.water_mask = (self.landuse_raw != 80) 

        print(f"  Classes found : { {int(c): self.RUNOFF_COEFFICIENTS.get(int(c), 0.50) for c in unique_classes} }")
        print(f"  Runoff coeff  — min: {rc_map.min():.2f}, max: {rc_map.max():.2f}, mean: {rc_map.mean():.2f}")
        print(f"  Final shape   — {rc_map.shape}  ✓ matches DEM {dem_shape}")


    def load_precip(self, duration_hr:float =24.0, infiltration_rate_mm_hr:float =10.0):
       
        arr = np.load(self.precip_file).squeeze().astype(np.float32)
        self.precip_raw  = np.clip(arr, 0, None)
        self.duration_hr = duration_hr          # store for use in HAND stage

        
        precip_rate = self.precip_raw / max(duration_hr, 1e-3)   # mm/hr
        INFIL_RATE = {
            10:  25.0,   # Tree cover         — high, deep root channels
            20:  18.0,   # Shrubland
            30:  15.0,   # Grassland
            40:  12.0,   # Cropland           — tilled, moderate
            50:   5.0,   # Built-up           — mostly impervious
            60:  10.0,   # Bare/sparse veg
            70:   2.0,   # Snow / ice         — near-zero
            80:   0.0,   # Permanent water    — already saturated
            90:   8.0,   # Herbaceous wetland — saturated soils
            95:  20.0,   # Mangroves          — permeable substrate
            100: 10.0,   # Moss / lichen
            0:   10.0,   # fallback
        }

        if self.runoff_coeff_map is not None and self.landuse_raw is not None:
            infil_map = np.full(self.landuse_raw.shape, infiltration_rate_mm_hr,
                                dtype=np.float32)
            for cls, rate in INFIL_RATE.items():
                infil_map[self.landuse_raw == cls] = rate

            ## NOTE: This line uses the intensity/infiltration concept
            #effective_rate = np.clip(precip_rate - infil_map, 0, None)  # mm/hr
            #effective_precip = effective_rate * duration_hr             # mm
            #self.runoff = effective_precip * self.runoff_coeff_map

            self.runoff = self.precip_raw * self.runoff_coeff_map
            
            infil_fraction = 1.0 - (self.runoff.mean() /
                                    (self.precip_raw.mean() + 1e-6))
            
            print(f"Precip loaded — range: {self.precip_raw.min():.1f}–"
                  f"{self.precip_raw.max():.1f} mm  "
                  f"over {duration_hr:.1f} hr  "
                  f"(rate: {precip_rate.mean():.1f} mm/hr mean)")
            print(f"Infiltration  — land-use specific, "
                  f"mean capacity: {infil_map.mean():.1f} mm/hr, "
                  f"effectively absorbed: {infil_fraction*100:.0f}% of rain")
            print(f"Runoff        — mean effective: {self.runoff.mean():.2f} mm  "
                  f"(was {(self.precip_raw * self.runoff_coeff_map).mean():.2f} mm "
                  f"without intensity filter)")
            
        else:
            print("load_precip: FALLING ELSE")
            global_infil = infiltration_rate_mm_hr
            effective_rate  = np.clip(precip_rate - global_infil, 0, None)
            effective_precip = effective_rate * duration_hr
            self.runoff = effective_precip * 0.65
            print(f"Precip loaded — range: {self.precip_raw.min():.1f}–"
                  f"{self.precip_raw.max():.1f} mm  over {duration_hr:.1f} hr")
            print(f"Warning: no land-use map — global infiltration {global_infil} mm/hr, "
                  f"runoff fraction 0.65")

        assert self.precip_raw.shape == self.dem_raw.shape, \
            f"Precip shape {self.precip_raw.shape} != DEM shape {self.dem_raw.shape}"
    


    # ------------------------------------------------------------------ 
    #  Flood depth — physically grounded proxy
    # ------------------------------------------------------------------ 

    def twi_estimate_flood_depth(self):
        dy, dx = np.gradient(self.dem_filled)
        slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
        tan_slope = np.tan(slope_rad)
        tan_slope = np.clip(tan_slope, 0.001, None)

        twi = np.log((self.acc + 1.0) / tan_slope)
        twi = np.clip(twi, 0, None)

        twi_max = np.percentile(twi, 99)
        self.flood_depth = np.clip(
            twi / (twi_max + 1e-6) * self.depth_cap, 0, self.depth_cap
        )
        print(f"Flood depth   — TWI range: {twi.min():.2f}–{twi.max():.2f}, "
              f"depth 99th pct: {np.percentile(self.flood_depth, 99):.2f} m")



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

    def _write_tif(self, data, out_path, description, units):
        with rasterio.open(self.dem_file) as src:
            profile = src.profile.copy()
        profile.update(dtype="float32", count=1, compress="lzw", nodata=-9999.0)
        with rasterio.open(out_path, "w", **profile) as dst:
            out = np.where(np.isfinite(data), data, -9999.0).astype(np.float32)
            dst.write(out, 1)
            dst.update_tags(
                description  = description,
                units        = units,
                precip_src   = self.precip_file,
                landuse_src  = self.landuse_file or "none",
                runoff_method = "per-pixel ESA WorldCover coefficients" 
                                if self.landuse_file else "global fraction",
            )
        print(f"TIF saved     — {out_path}  "
            f"[{data[np.isfinite(data)].min():.2f}"
            f" – {data[np.isfinite(data)].max():.2f} {units}]")


    def save_tif(self, out_path="flood_accumulation.tif"):
        """Primary — raw D8 weighted accumulation in mm runoff."""
        self._write_tif(self.acc, out_path,
                        "D8 flow accumulation (runoff-weighted)", "mm")


    def save_flood_depth_tif(self, out_path="flood_depth.tif"):
        """Flood depth proxy (relative, 0–10 m)."""
        self._write_tif(self.flood_depth, out_path,
                        f"Flood depth proxy ({self.model} model)",
                        "relative_m")


    def save_twi_tif(self, out_path="twi_depth.tif"):
        """Secondary — TWI-based flood depth proxy for visualization."""
        self._write_tif(self.flood_depth, out_path,
                        "TWI flood depth proxy (not physically calibrated)",
                        "relative_m")
    

    def save_hand_tif(self, out_path="hand.tif"):
        """Raw HAND raster — height above nearest drainage in metres.
        This is the physically meaningful output, independent of precip."""
        self._write_tif(self.hand, out_path,
                        "Height Above Nearest Drainage (HAND)", "metres")
    
    



    # ------------------------------------------------------------------ 
    #  Visualisation
    # ------------------------------------------------------------------ 
    def plot(self, figsize=(12, 10)):
        fig, axes = plt.subplots(2, 2, figsize=figsize)
        axes = axes.flatten()  # now axes is a 1D array of 4 axes

        # Slope map for context
        dy, dx = np.gradient(self.dem_filled)
        slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))

        panels = [
            (self.dem_ps,          "terrain",  "DEM — Elevation (m)"),
            (slope,                 "gray",     "Slope (degrees)"),
            (np.log1p(self.acc),    "Blues",    f"Flow Accumulation {self.acc_model} - log(mm)"),
            (self.flood_depth,      "jet",      f"Flood Depth proxy {self.model} — (m)"),
        ]

        for ax, (data, cmap, title) in zip(axes, panels):
            d = np.where(np.isfinite(data), data, 0)
            im = ax.imshow(d, cmap=cmap)
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            ax.set_title(title, fontsize=11)
            ax.axis("off")

        plt.suptitle("Flood Model — Metro Manila (24hr precip)", fontsize=14)
        plt.tight_layout()
        plt.show()


    def save_flood_map(self, out_path="flood_depth.png"):
        max_val = self.flood_depth.max()
        arr = (self.flood_depth / (max_val if max_val > 0 else 1) * 255).astype(np.uint8)
        Image.fromarray(arr, mode="L").save(out_path)
        print(f"PNG saved     — {out_path}")
    




    # ------------------------------------------------------------------
    # Plot land use map 
    # ------------------------------------------------------------------
    def plot_landuse(self):
        """Show land use classes and their assigned runoff coefficients."""
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        from matplotlib.colors import BoundaryNorm
        from matplotlib.cm import get_cmap

        classes   = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
        colors_lc = [
            '#006400',
            '#ffbb22',
            '#ffff4c',
            '#f096ff',
            '#fa0000',
            '#b4b4b4',
            '#f0f0f0',
            '#0064c8',
            '#0096a0',
            '#00cf75',
            '#fae6a0'
        ]
        
        labels = [  
            'Tree', 'Shrub', 'Grass', 'Crop', 'Built-up',
            'Bare', 'Snow', 'Water', 'Wetland', 'Mangrove','Moss'
        ]
        
        cmap_custom = ListedColormap(colors_lc)
        bounds = classes + [classes[-1] + 1]
        norm = BoundaryNorm(bounds, cmap_custom.N)

        axes[0].imshow(
            self.landuse_raw, 
            cmap = cmap_custom,
            norm = norm,
            interpolation = 'nearest'
        )
        
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


    def prepare_dem(self):
        print("Conditioning DEM with pysheds …")
        self.grid = Grid.from_raster(self.dem_file)
        dem = self.grid.read_raster(self.dem_file)

        pit_filled = self.grid.fill_pits(dem)

        flooded = self.grid.fill_depressions(pit_filled)

        self.dem_ps = self.grid.resolve_flats(flooded, max_iter=int(1e9), eps=1e-12)

        self.dem_filled = np.array(self.dem_ps, dtype=np.float32)

        delta = self.dem_filled - np.where(np.isfinite(self.dem_raw), self.dem_raw, 0)
        print(f"Depression fill — max raised: {delta.max():.2f} m, "
              f"cells modified: {(delta > 1e-6).sum():,}")



    def hand_estimate_flood_depth(self, channel_threshold=None, stage_scale=500.0):
        ROUTING_MAP = {
            "D8":          "d8",
            "MFD":         "mfd",
            "D-INIFINITY": "dinf",
        }
        routing = ROUTING_MAP.get(self.acc_model, "d8")

        # --- Channel mask ---
        if channel_threshold is None:
            channel_threshold = np.percentile(
                self.acc[np.isfinite(self.acc)], 99
            )
        channel_mask = self.acc >= channel_threshold
        n_channels = channel_mask.sum()
        print(f"HAND          — routing: {routing}, "
            f"channel threshold: {channel_threshold:.1f} mm, "
            f"channel cells: {n_channels:,} ({n_channels/self.acc.size*100:.2f}%)")

        vf = self.dem_ps.viewfinder                                    # ← changed
        channel_raster = Raster(channel_mask.astype(np.bool_), viewfinder=vf)
        dem_raster     = Raster(self.dem_filled, viewfinder=vf)

        hand_ps = self.grid.compute_hand(
            self.fdir_ps,
            dem_raster,
            channel_raster,
            dirmap     = self.dirmap,
            routing    = routing,
            nodata_out = np.nan,
        )

        hand = np.array(hand_ps, dtype=np.float32)
        hand = np.clip(hand, 0, None)

        untraced = ~np.isfinite(hand)
        if untraced.any():
            max_hand = np.nanmax(hand)
            hand[untraced] = max_hand
            print(f"HAND          — {untraced.sum():,} untraced → max ({max_hand:.1f} m)")

        self.hand = hand
        print(f"HAND          — range: {hand.min():.2f}–{hand.max():.2f} m, "
              f"mean: {hand.mean():.2f} m")

        raw_stage_m = (self.acc / 1000.0) * (stage_scale / 100) 
        flood       = np.clip(raw_stage_m - hand, 0, None)
        
        self.flood_depth = np.clip(flood, 0, self.depth_cap)

        flooded_cells = (self.flood_depth > 0).sum()

        print(f"HAND flood    — flooded cells: {flooded_cells:,} "
              f"({flooded_cells / self.acc.size * 100:.1f}%), "
              f"max depth: {self.flood_depth.max():.2f} m, "
              f"mean (flooded): "
              f"{self.flood_depth[self.flood_depth > 0].mean():.2f} m")





    # ------------------------------------------------------------------ 
    #  Flow accumulation models
    # ------------------------------------------------------------------ 
    def build_flow_model(self):
        """Compute flow direction using the selected acc_model routing."""
        if self.acc_model == "MFD":
            self.fdir_ps = self.grid.flowdir(self.dem_ps, routing='mfd', dirmap=self.dirmap)
        elif self.acc_model == "D-INIFINITY":
            self.fdir_ps = self.grid.flowdir(self.dem_ps, routing='dinf', dirmap=self.dirmap)
        else:  # Default D8
            self.fdir_ps = self.grid.flowdir(self.dem_ps, dirmap=self.dirmap)

        self.fdir = np.array(self.fdir_ps, dtype=np.int16)

        routable = (self.fdir > 0).sum()
        print(f"Flow direction — {self.acc_model} routing, "
            f"{routable:,} / {self.fdir.size:,} routable "
            f"({routable / self.fdir.size * 100:.1f}%)")
        
    
    def compute_accumulation_mfd(self):
        print("Compute Accumulation model: MFD")
        vf = self.dem_ps.viewfinder
        runoff_raster = Raster(self.runoff.astype(np.float64), viewfinder=vf)
        acc_ps = self.grid.accumulation(
            self.fdir_ps,          # ← now consistent, set in build_flow_model
            weights    = runoff_raster,
            routing    = 'mfd',
            dirmap     = self.dirmap,
            nodata_out = np.nan,
        )
        self.acc = np.array(acc_ps, dtype=np.float32)
        print(f"Accumulation  — MFD max: {self.acc.max():.1f} mm, "
            f"mean: {self.acc.mean():.2f} mm, "
            f"95th pct: {np.percentile(self.acc[np.isfinite(self.acc)], 95):.1f} mm, "
            f"99th pct: {np.percentile(self.acc[np.isfinite(self.acc)], 99):.1f} mm")


    def compute_accumulation_dinf(self):
        print("Compute Accumulation model: D-Infinity")
        vf = self.dem_ps.viewfinder          # ← was self.fdir_ps.viewfinder
        runoff_raster = Raster(self.runoff.astype(np.float64), viewfinder=vf)
        acc_ps = self.grid.accumulation(
            self.fdir_ps,          # ← now consistent
            weights    = runoff_raster,
            routing    = 'dinf',
            dirmap     = self.dirmap,
            nodata_out = np.nan,
        )
        self.acc = np.array(acc_ps, dtype=np.float32)
        print(f"Accumulation  — D-Inf max: {self.acc.max():.1f} mm, "
            f"mean: {self.acc.mean():.2f} mm, "
            f"95th pct: {np.percentile(self.acc[np.isfinite(self.acc)], 95):.1f} mm, "
            f"99th pct: {np.percentile(self.acc[np.isfinite(self.acc)], 99):.1f} mm")


    def compute_accumulation_pyshed_d8(self):
        vf = self.fdir_ps.viewfinder
        runoff_raster = Raster(self.runoff.astype(np.float64), viewfinder=vf)

        acc_ps = self.grid.accumulation(
            self.fdir_ps,
            weights  = runoff_raster,
            dirmap   = self.dirmap,
            nodata_out = np.nan,
        )

        self.acc = np.array(acc_ps, dtype=np.float32)
        print(f"Accumulation  — max: {self.acc.max():.1f} mm, "
              f"mean: {self.acc.mean():.2f} mm, "
              f"95th pct: {np.percentile(self.acc[np.isfinite(self.acc)], 95):.1f} mm, "
              f"99th pct: {np.percentile(self.acc[np.isfinite(self.acc)], 99):.1f} mm")




    # ------------------------------------------------------------------ #
    #  Runner
    # ------------------------------------------------------------------ #
    def run(self):
        # ------- LOADIN & PREPARING DATA  -------------------------------
        self.load_dem()
        self.prepare_dem()

        self.load_landuse() 
        self.load_precip(duration_hr = 24)
       

        # ------- FLODD MODELLING ----------------------------------------
        self.build_flow_model()


        if self.acc_model == "MFD":
            self.compute_accumulation_mfd()
        elif self.acc_model == "D-INIFINITY":
            self.compute_accumulation_dinf()
        elif self.acc_model == "D8":
            self.compute_accumulation_pyshed_d8()
        else:
            raise ValueError(f"Invalid acc_model '{self.acc_model}'. Expected 'MFD', 'D-INIFINITY', or 'D8'.")


        if self.model == "HAND":
            self.hand_estimate_flood_depth() 
        elif self.model == "TWI":
            self.twi_estimate_flood_depth()
        else:
            raise ValueError(f"Invalid acc_model '{self.acc_model}'. Expected 'HAND' or 'TWI'.")
        

        # ------- OUTPUT PREPS -------------------------------------------
        self.smooth_flood_depth()
        if self.mask_bow:
            if self.landuse_file:
                land_mask = self.water_mask   # False where class 80
            else:
                land_mask = np.isfinite(self.dem_raw)   # fallback

            self.acc          = np.where(land_mask, self.acc,          np.nan)
            self.flood_depth  = np.where(land_mask, self.flood_depth,  np.nan)
            if self.hand is not None:
                self.hand     = np.where(land_mask, self.hand,         np.nan)
        

        # ------- SAVING OUTPUT DATA -------------------------------------
        self.save_tif()
        self.save_flood_depth_tif()

        if self.model == "HAND":
            self.save_hand_tif()
        else:
            self.save_twi_tif()
        
        self.save_flood_map()

        
        # ------- PLOTTING -----------------------------------------------
        if self.landuse_file: self.plot_landuse()
        self.plot()