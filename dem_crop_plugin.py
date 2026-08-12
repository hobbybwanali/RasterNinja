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
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand

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
        except Exception:
            pass

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

        ... (truncated) ...