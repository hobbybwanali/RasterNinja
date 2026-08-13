from .dem_crop_plugin import DemCropPlugin


def classFactory(iface):
    return DemCropPlugin(iface)
