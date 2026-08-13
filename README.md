<p align="center">
  <img src="icon.png" alt="RasterNinja logo" width="160"/>
</p>

<h1 align="center">RasterNinja</h1>

RasterNinja is a QGIS plugin to simplify raster workflows: draw a polygon or use an existing polygon mask (shapefile) to clip rasters, and obtain a temporary clipped raster added to your project. RasterNinja is a foundation for more raster tools like merging, format conversion, and DEM processing

Author: Hobby Bwanali <hobbybwanali@gmail.com>
GitHub: https://github.com/hobbybwanali

## Screenshot

![RasterNinja panel cropping a DEM in QGIS](screenshots/screenshot1.png)

## Installation
1. Copy the `RasterNinja` folder into your QGIS profile's `python/plugins` directory.
2. Restart QGIS.
3. Enable RasterNinja from Plugins > Manage and Install Plugins.

## Usage
- Select a raster layer from the dropdown or load one in the project.
- Optionally select a mask polygon layer from the Mask layer dropdown, or draw a polygon using the Draw button.
- Click Finish polygon to close the polygon, then click Apply crop.
- If no output path is specified, the result is added as a temporary raster layer to the project. Save manually from the Layers panel if you want a permanent file.

## Notes
- RasterNinja expects georeferenced rasters with a valid CRS.
- The plugin is designed to be extended with more raster processing features.

## Quick QA checklist (run this after installing/updating)
1. Restart QGIS and enable RasterNinja in the Plugin Manager.
2. Open the RasterNinja panel (toolbar button). Confirm the Ninja icon and title appear in the panel header.
3. Load two GeoTIFF rasters into the project. Confirm they appear in the DEM dropdown.
4. With a raster visible and selected, ensure the "Polygon" radio is selected and the Draw/Finish/Clear buttons are enabled.
5. Draw a polygon with at least 3 points, click Finish polygon, then click Apply crop. Expect a temporary raster layer to appear in the Layers panel. Check for a green success message in the plugin panel.
6. Toggle the radio to "Mask layer", choose an existing polygon vector from the Mask dropdown, click Apply crop and confirm a temporary output appears.
7. With a raster un-ticked (hidden) in the Layers panel, confirm the plugin disables polygon tools and shows a warning.
8. Try saving the temporary clipped raster from the Layers panel to a GeoTIFF and re-load it to confirm validity.

If any step fails, copy the plugin log or traceback and send it here (the Python traceback shown in the QGIS log). I'll help interpret and fix it.
