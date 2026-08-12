# Plugin submission notes — RasterNinja

This document describes the steps required to submit RasterNinja to the QGIS Plugins Repository (plugins.qgis.org).

1) Prepare ZIP package
- Ensure the plugin folder contains: dem_crop_plugin.py (main plugin), __init__.py, metadata.txt, metadata.txt fields populated, icons/ and icon.png at repo root, README.md, LICENSE (recommended), and optionally a screenshots/ folder.
- Create a zip archive of the plugin folder (example: RasterNinja_v1.0.0.zip). A ZIP is included in the `dist/` folder in this repo.

2) Create screenshots
- Provide PNG images of the plugin UI (recommended sizes: 1280x720 and 600x400). Name them `screenshot1.png`, `screenshot2.png`.

3) QGIS Plugins Repository account
- Create or login to your account on https://plugins.qgis.org/ and go to the plugin submission page.

4) Submission form
- Fill in plugin name, version, short and long description. Use the README as the long description.
- Upload the plugin ZIP file and screenshots.
- Set contact email (optional) and repository URL: https://github.com/hobbybwanali/RasterNinja.

5) After submission
- The QGIS Plugins administrators may review and request changes. Keep the repo up to date and provide requested fixes.

Notes
- Ensure `metadata.txt` is valid and contains `icon` referencing a file found in the plugin root or plugin folder.
- If you prefer not to publish an email in metadata, remove the `email=` line from metadata.txt before submission.
