import os
import re

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QAction,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QDockWidget,
    QApplication,
    QStyle,
)
from qgis.PyQt.QtCore import QSize

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsMapLayerType,
    QgsMessageLog,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand


def _log_warning(message):
    """Send a non-fatal error to the QGIS Log Messages panel instead of
    swallowing it silently. Used for optional/best-effort UI updates where
    failure shouldn't interrupt the user, but should still be visible for
    debugging (RasterNinja tab in Log Messages)."""
    QgsMessageLog.logMessage(str(message), "RasterNinja", level=Qgis.Warning)

try:
    from qgis import processing
except ImportError:  # pragma: no cover
    processing = None


class DemCropMapTool(QgsMapToolEmitPoint):
    def __init__(self, canvas, plugin):
        super().__init__(canvas)
        self.plugin = plugin
        self.canvas = canvas
        self.rubber_band = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self.rubber_band.setStrokeColor(QColor(255, 68, 68))
        self.rubber_band.setFillColor(QColor(255, 68, 68, 70))
        self.rubber_band.setWidth(2)
        self.vertices = []
        self.active = False
        self.setCursor(Qt.CrossCursor)

    def activate(self):
        self.reset_capture()
        self.active = True
        super().activate()

    def deactivate(self):
        self.active = False
        self.reset_capture()
        super().deactivate()

    def reset_capture(self):
        self.vertices = []
        self.rubber_band.reset(Qgis.GeometryType.Polygon)

    def update_preview(self, temporary_point=None):
        if not self.active:
            return

        points = list(self.vertices)
        if temporary_point is not None:
            points.append(QgsPointXY(temporary_point.x(), temporary_point.y()))

        if len(points) < 2:
            self.rubber_band.reset(Qgis.GeometryType.Polygon)
            return

        self.rubber_band.reset(Qgis.GeometryType.Polygon)
        for point in points:
            self.rubber_band.addPoint(point, False)

        if len(points) >= 3:
            self.rubber_band.addPoint(points[0], True)
        self.rubber_band.show()

    def canvasPressEvent(self, event):
        if not self.active:
            return

        point = self.toMapCoordinates(event.pos())
        self.vertices.append(QgsPointXY(point.x(), point.y()))
        self.update_preview()

    def canvasMoveEvent(self, event):
        if not self.active or not self.vertices:
            return

        point = self.toMapCoordinates(event.pos())
        self.update_preview(point)

    def canvasDoubleClickEvent(self, event):
        if not self.active:
            return
        event.accept()
        self.finish_polygon()

    def finish_polygon(self):
        if len(self.vertices) < 3:
            self.plugin.show_status("Draw at least three points to create a valid crop polygon.", "error")
            return

        closed_vertices = list(self.vertices)
        if closed_vertices[0] != closed_vertices[-1]:
            closed_vertices.append(closed_vertices[0])

        geometry = QgsGeometry.fromPolygonXY([closed_vertices])
        self.plugin.current_geometry = geometry
        self.rubber_band.setToGeometry(geometry, None)
        self.rubber_band.show()
        self.active = False
        self.plugin.show_status("Crop polygon ready. Review it and click Apply crop to export the DEM.")


class DemCropDockWidget(QWidget):
    def __init__(self, iface, plugin):
        super().__init__()
        self.iface = iface
        self.plugin = plugin

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(8)

        # Top toolbar row: plugin icon + title (compact)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        icon_paths = [
            os.path.join(self.plugin.plugin_dir, "icon_main.png"),
            os.path.join(self.plugin.plugin_dir, "icon.png"),
            os.path.join(self.plugin.plugin_dir, "icon_main.svg"),
        ]
        pix = None
        for p in icon_paths:
            if os.path.exists(p):
                try:
                    pix = QPixmap(p)
                    break
                except Exception:
                    pix = None
        if pix is not None and not pix.isNull():
            icon_label = QLabel()
            icon_label.setPixmap(pix.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            top_row.addWidget(icon_label)
        title = QLabel("RasterNinja")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        top_row.addWidget(title)
        top_row.addStretch()
        self.layout.addLayout(top_row)

        # mode selection placed in a labeled group for clarity
        modes_group = QGroupBox("Crop DEM with")
        modes_row = QHBoxLayout()
        self.mode_polygon = QRadioButton("Polygon")
        self.mode_mask = QRadioButton("Mask layer")
        self.mode_polygon.setChecked(True)
        self.mode_polygon.toggled.connect(self.on_mode_changed)
        self.mode_mask.toggled.connect(self.on_mode_changed)
        modes_row.addWidget(self.mode_polygon)
        modes_row.addWidget(self.mode_mask)
        modes_group.setLayout(modes_row)
        self.layout.addWidget(modes_group)

        group = QGroupBox("Selection")
        form_layout = QFormLayout(group)
        self.layer_combo = QComboBox()
        self.layer_combo.setMinimumWidth(240)
        self.layer_combo.currentIndexChanged.connect(self.on_layer_changed)
        form_layout.addRow("DEM layer", self.layer_combo)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Output path (.tif)")
        browse_row = QHBoxLayout()
        browse_row.addWidget(self.output_edit)
        browse_button = QToolButton()
        try:
            folder_icon = QApplication.style().standardIcon(QStyle.SP_DirOpenIcon)
        except Exception:
            folder_icon = None
        icon_path = os.path.join(self.plugin.plugin_dir, "icon.png")
        if os.path.exists(icon_path):
            browse_button.setIcon(QIcon(icon_path))
        elif folder_icon is not None:
            browse_button.setIcon(folder_icon)
        browse_button.setIconSize(QSize(20,20))
        browse_button.setToolTip("Choose output file (optional). Leave blank to create a temporary layer.")
        browse_button.clicked.connect(self.select_output_file)
        browse_button.setStyleSheet("QToolButton{border-radius:6px;padding:2px;margin:0;background:#ffffff;}QToolButton:hover{background:#eef5ff}")
        browse_button.setContentsMargins(0,0,0,0)
        browse_row.addWidget(browse_button)
        form_layout.addRow("Output file", browse_row)

        self.name_edit = QLineEdit("clipped_dem.tif")
        form_layout.addRow("Output name", self.name_edit)

        # mask layer selector: optional polygon shapefile or vector mask
        self.mask_combo = QComboBox()
        self.mask_combo.setMinimumWidth(240)
        form_layout.addRow("Mask layer (optional)", self.mask_combo)
        # ensure mask dropdown is disabled when polygon mode is the default
        try:
            self.mask_combo.setEnabled(not self.mode_polygon.isChecked())
        except Exception as exc:
            _log_warning(f"Could not set initial mask_combo state: {exc}")

        self.layout.addWidget(group)

        action_group = QGroupBox("Crop area")
        action_layout = QHBoxLayout(action_group)
        action_layout.setContentsMargins(2,2,2,2)
        action_layout.setSpacing(6)

        icon_draw = os.path.join(self.plugin.plugin_dir, "icon_draw.svg")
        icon_finish = os.path.join(self.plugin.plugin_dir, "icon_finish.svg")
        icon_clear = os.path.join(self.plugin.plugin_dir, "icon_clear.svg")
        icon_apply = os.path.join(self.plugin.plugin_dir, "icon_apply.svg")

        btn_style = "QToolButton{border-radius:6px;padding:2px;margin:0;background:#ffffff;border:1px solid rgba(0,0,0,0.06);}QToolButton:hover{background:#eef5ff}"

        self.draw_button = QToolButton()
        if os.path.exists(icon_draw):
            self.draw_button.setIcon(QIcon(icon_draw))
        else:
            self.draw_button.setText("Draw")
        self.draw_button.setIconSize(QSize(24,24))
        self.draw_button.setToolTip("Draw polygon — click on the map to add vertices")
        self.draw_button.clicked.connect(self.plugin.start_drawing)
        self.draw_button.setStyleSheet(btn_style)
        self.draw_button.setContentsMargins(0,0,0,0)
        action_layout.addWidget(self.draw_button)

        self.finish_button = QToolButton()
        if os.path.exists(icon_finish):
            self.finish_button.setIcon(QIcon(icon_finish))
        else:
            self.finish_button.setText("Finish")
        self.finish_button.setIconSize(QSize(24,24))
        self.finish_button.setToolTip("Finish polygon — close current polygon")
        self.finish_button.clicked.connect(self.plugin.finish_current_polygon)
        self.finish_button.setStyleSheet(btn_style)
        self.finish_button.setContentsMargins(0,0,0,0)
        action_layout.addWidget(self.finish_button)

        self.clear_button = QToolButton()
        if os.path.exists(icon_clear):
            self.clear_button.setIcon(QIcon(icon_clear))
        else:
            self.clear_button.setText("Clear")
        self.clear_button.setIconSize(QSize(24,24))
        self.clear_button.setToolTip("Clear polygon preview")
        self.clear_button.clicked.connect(self.plugin.clear_polygon)
        self.clear_button.setStyleSheet(btn_style)
        self.clear_button.setContentsMargins(0,0,0,0)
        action_layout.addWidget(self.clear_button)

        self.apply_button = QToolButton()
        if os.path.exists(icon_apply):
            self.apply_button.setIcon(QIcon(icon_apply))
        else:
            self.apply_button.setText("Apply")
        self.apply_button.setIconSize(QSize(24,24))
        self.apply_button.setToolTip("Apply crop — produce a temporary clipped raster")
        self.apply_button.clicked.connect(self.plugin.apply_crop)
        self.apply_button.setStyleSheet(btn_style)
        self.apply_button.setContentsMargins(0,0,0,0)
        action_layout.addWidget(self.apply_button)
        self.layout.addWidget(action_group)

        self.plugin.dock_widget = self

        self.status_label = QLabel("No crop area yet.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("padding: 6px; color: #1a1a1a; background: #f2f2f2; border-radius: 4px;")
        self.layout.addWidget(self.status_label)

        self.refresh_layers()

    def on_layer_changed(self):
        selected_layer = self.selected_dem()
        if selected_layer is None:
            return
        default_name = self.build_default_name(selected_layer)
        if self.name_edit.text().strip() in ("", "clipped_dem.tif"):
            self.name_edit.setText(default_name)
        self.plugin.show_status("Selected DEM: {}".format(selected_layer.name()))

    def build_default_name(self, layer):
        sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", layer.name()).strip("_")
        if not sanitized:
            sanitized = "dem"
        return "{}_clipped.tif".format(sanitized)

    def select_output_file(self):
        default_path = self.output_edit.text().strip() or self.default_output_path()
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save clipped DEM",
            default_path,
            "GeoTIFF (*.tif *.tiff);;All files (*)",
        )
        if file_name:
            self.output_edit.setText(self.ensure_tif_extension(file_name))

    def default_output_path(self):
        selected = self.selected_dem()
        if selected is not None:
            folder = os.path.expanduser("~")
            return os.path.join(folder, self.build_default_name(selected))
        return os.path.join(os.path.expanduser("~"), "clipped_dem.tif")

    @staticmethod
    def ensure_tif_extension(path):
        if not path:
            return path
        lower = path.lower()
        if lower.endswith(".tif") or lower.endswith(".tiff"):
            return path
        return path + ".tif"

    def refresh_layers(self):
        self.layer_combo.clear()
        self.mask_combo.clear()

        raster_layers = self.plugin.get_dem_layers()
        for layer in raster_layers:
            self.layer_combo.addItem(layer.name(), layer)

        # populate polygon/vector mask layers
        mask_layers = self.plugin.get_mask_layers()
        self.mask_combo.addItem("(none)", None)
        for layer in mask_layers:
            self.mask_combo.addItem(layer.name(), layer)

        if self.layer_combo.count() == 0:
            self.plugin.show_status("No raster layers found in the project. Load a georeferenced raster (GeoTIFF).", "warning")
            self.apply_button.setEnabled(False)
            self.draw_button.setEnabled(False)
            self.finish_button.setEnabled(False)
            return

        self.apply_button.setEnabled(True)
        self.draw_button.setEnabled(True)
        self.finish_button.setEnabled(True)
        if self.name_edit.text().strip() == "":
            self.name_edit.setText(self.build_default_name(self.selected_dem()))

        # ensure buttons reflect current mode and layer visibility immediately
        try:
            self.on_mode_changed()
        except Exception as exc:
            _log_warning(f"Could not refresh mode state on init: {exc}")

    def selected_dem(self):
        index = self.layer_combo.currentIndex()
        if index < 0:
            return None
        return self.layer_combo.itemData(index)

    def on_mode_changed(self, checked=None):
        """Radio signal wrapper: forward to plugin's handler."""
        try:
            self.plugin.on_mode_changed()
        except Exception as exc:
            _log_warning(f"Mode-change handler failed: {exc}")


class DemCropPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.current_geometry = None
        self._previous_map_tool = None
        self.toolbar = None
        self.dock = None
        self.dock_widget = None
        self.map_tool = None
        self.action = None
        self.initGui()

    def initGui(self):
        if self.toolbar is not None:
            return

        self.toolbar = self.iface.addToolBar("RasterNinja")
        self.toolbar.setObjectName("RasterNinja")

        self.dock = QDockWidget("RasterNinja", self.iface.mainWindow())
        self.dock.setObjectName("rasterninja_dock")
        try:
            self.dock.setAllowedAreas(Qt.AllDockWidgetAreas)
            self.dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        except Exception as exc:
            _log_warning(f"Could not configure dock widget areas/features: {exc}")
        self.dock_widget = DemCropDockWidget(self.iface, self)
        self.dock.setWidget(self.dock_widget)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.setVisible(False)

        self.map_tool = DemCropMapTool(self.iface.mapCanvas(), self)

        self.action = QAction("RasterNinja", self.iface.mainWindow())
        # prefer a specific main icon if provided; fall back to common names
        icon_candidates = [
            os.path.join(self.plugin_dir, 'icon_main.svg'),
            os.path.join(self.plugin_dir, 'icon.svg'),
            os.path.join(self.plugin_dir, 'icon.png'),
            os.path.join(self.plugin_dir, 'icon_main.png'),
        ]
        for p in icon_candidates:
            if os.path.exists(p):
                self.action.setIcon(QIcon(p))
                break
        self.action.setToolTip("Open the DEM crop tool")
        self.action.triggered.connect(self.toggle_dock)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&RasterNinja", self.action)
        self.actions.append(self.action)

        QgsProject.instance().layersAdded.connect(self._refresh_layers_for_project_change)
        QgsProject.instance().layersRemoved.connect(self._refresh_layers_for_project_change)

    def tr(self, text):
        return text

    def _refresh_layers_for_project_change(self, *args):
        if self.dock_widget is not None:
            self.dock_widget.refresh_layers()

    def on_mode_changed(self):
        """Handle enabling/disabling controls when the user switches between
        polygon drawing mode and mask-layer mode.
        """
        mode_polygon = False
        try:
            mode_polygon = self.dock_widget.mode_polygon.isChecked()
        except Exception as exc:
            _log_warning(f"Could not read mode_polygon state: {exc}")

        if mode_polygon:
            # polygon mode — enable draw tools only when a visible raster is selected
            try:
                self.dock_widget.mask_combo.setEnabled(False)
                sel = self.dock_widget.selected_dem()
                visible = sel in list(self.iface.mapCanvas().layers()) if sel is not None else False
                self.dock_widget.draw_button.setEnabled(visible)
                self.dock_widget.finish_button.setEnabled(visible)
                self.dock_widget.clear_button.setEnabled(visible)
            except Exception as exc:
                _log_warning(f"Could not update polygon-mode controls: {exc}")
        else:
            # mask mode — disable polygon tools
            try:
                self.dock_widget.mask_combo.setEnabled(True)
                self.dock_widget.draw_button.setEnabled(False)
                self.dock_widget.finish_button.setEnabled(False)
                self.dock_widget.clear_button.setEnabled(False)
            except Exception as exc:
                _log_warning(f"Could not update mask-mode controls: {exc}")

    def get_dem_layers(self):
        raster_layers = []
        seen = set()
        for layer in list(QgsProject.instance().mapLayers().values()) + list(self.iface.mapCanvas().layers()):
            if id(layer) in seen:
                continue
            seen.add(id(layer))
            if isinstance(layer, QgsRasterLayer) and layer.isValid() and layer.crs().isValid():
                raster_layers.append(layer)
        return raster_layers

    def get_mask_layers(self):
        vector_layers = []
        seen = set()
        for layer in list(QgsProject.instance().mapLayers().values()) + list(self.iface.mapCanvas().layers()):
            if id(layer) in seen:
                continue
            seen.add(id(layer))
            # polygon vector layers (memory/shapefile)
            try:
                if layer.type() == QgsMapLayerType.VectorLayer and layer.isValid() and layer.wkbType() in (3, 5, 6, 7, 31):
                    vector_layers.append(layer)
            except Exception:
                # fallback: accept valid vector layers
                try:
                    if layer.type() == QgsMapLayerType.VectorLayer and layer.isValid():
                        vector_layers.append(layer)
                except Exception as exc:
                    _log_warning(f"Skipped an unreadable layer while listing vector layers: {exc}")
        return vector_layers

    def toggle_dock(self):
        self.dock.setVisible(not self.dock.isVisible())
        if self.dock.isVisible():
            self.dock_widget.refresh_layers()
            self.show_status("Draw a polygon over the DEM and finish it before clipping.")

    def start_drawing(self):
        dem_layer = self.dock_widget.selected_dem()
        if dem_layer is None:
            self.show_status("Add a DEM raster layer before starting the crop.", "error")
            return

        self.current_geometry = None
        self._previous_map_tool = self.iface.mapCanvas().mapTool()
        self.map_tool.activate()
        self.iface.mapCanvas().setMapTool(self.map_tool)
        self.show_status("Click to add vertices. Double-click or use Finish polygon to complete the crop area.")

    def finish_current_polygon(self):
        if self.map_tool.active:
            self.map_tool.finish_polygon()
            return
        if self.current_geometry is None:
            self.show_status("No polygon is active yet. Draw a crop polygon first.", "error")

    def clear_polygon(self):
        self.current_geometry = None
        self.map_tool.reset_capture()
        self.show_status("Crop polygon cleared. Draw a new polygon to continue.")

    def show_status(self, message, level="info"):
        """Set a short status message on the dock widget and style it by severity.
        level: one of 'info', 'warning', 'error', 'success'.
        """
        if getattr(self, "dock_widget", None) is None:
            return
        label = self.dock_widget.status_label
        label.setText(message)
        if level == "error":
            label.setStyleSheet("padding:6px; color:#721c24; background:#f8d7da; border-radius:4px;")
        elif level == "warning":
            label.setStyleSheet("padding:6px; color:#856404; background:#fff3cd; border-radius:4px;")
        elif level == "success":
            label.setStyleSheet("padding:6px; color:#155724; background:#d4edda; border-radius:4px;")
        else:
            label.setStyleSheet("padding:6px; color:#1a1a1a; background:#f2f2f2; border-radius:4px;")
    def apply_crop(self):
        dem_layer = self.dock_widget.selected_dem()
        if dem_layer is None:
            self.show_status("Select a valid DEM raster.", "error")
            return

        if self.current_geometry is None:
            self.show_status("No crop polygon was created yet. Draw a polygon first.", "error")
            return

        if processing is None:
            self.show_status("QGIS processing is not available in this environment.", "error")
            return

        output_path = self.dock_widget.output_edit.text().strip()
        if not output_path:
            output_path = self.dock_widget.default_output_path()
        output_path = self.dock_widget.ensure_tif_extension(output_path)
        output_dir = os.path.dirname(output_path) or os.getcwd()
        if not os.path.isdir(output_dir):
            try:
                os.makedirs(output_dir)
            except OSError:
                self.show_status("The output folder does not exist and could not be created.", "error")
                return

        if os.path.exists(output_path):
            reply = QMessageBox.question(
                self.iface.mainWindow(),
                "Overwrite output",
                "The target file already exists. Replace it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        mask_layer = QgsVectorLayer(
            "Polygon?crs={}".format(dem_layer.crs().authid()),
            "dem_crop_mask",
            "memory",
        )
        provider = mask_layer.dataProvider()
        feature = QgsFeature()
        feature.setGeometry(self.current_geometry)
        provider.addFeatures([feature])
        mask_layer.updateExtents()

        try:
            params = {
                "INPUT": dem_layer,
                "MASK": mask_layer,
                "CROP_TO_CUTLINE": True,
                "KEEP_RESOLUTION": True,
                "TARGET_CRS": dem_layer.crs(),
                "NODATA": None,
                "OUTPUT": output_path,
            }
            processing.run("gdal:cliprasterbymasklayer", params)
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Crop failed",
                "The DEM could not be clipped.\n\n{}".format(exc),
            )
            self.show_status("Raster clipping failed. Check the DEM layer and polygon geometry.", "error")
            return
        finally:
            QgsProject.instance().removeMapLayer(mask_layer.id())

        new_layer = QgsRasterLayer(output_path, os.path.basename(output_path))
        if new_layer.isValid():
            QgsProject.instance().addMapLayer(new_layer)
            self.show_status("DEM clipped successfully. Output saved to: {}".format(output_path), "success")
        else:
            self.show_status("Crop finished but the output raster could not be loaded.", "error")

        if self._previous_map_tool is not None and self._previous_map_tool is not self.map_tool:
            self.iface.mapCanvas().setMapTool(self._previous_map_tool)
        self._previous_map_tool = None

        self.map_tool.reset_capture()
        self.current_geometry = None

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu("&RasterNinja", action)
            self.iface.removeToolBarIcon(action)
        self.iface.mainWindow().removeDockWidget(self.dock)


def classFactory(iface):
    return DemCropPlugin(iface)
