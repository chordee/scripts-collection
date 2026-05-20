import os
import getpass
import time

import hou
import husd.outputprocessor as base


class AvalonPublish(base.OutputProcessor):

    def __init__(self):
        super().__init__()
        self.output_dir = None

    @staticmethod
    def name():
        return 'avalonpublish'

    @staticmethod
    def displayName():
        return 'Avalon Publish'

    def beginSave(self, config_node, config_overrides, lop_node, t, stage_variables):
        super().beginSave(config_node, config_overrides, lop_node, t, stage_variables)
        self.output_usd = self.evalConfig('lopoutput', config_node, config_overrides, t)
        self.output_dir, _ = os.path.split(self.output_usd)

    def processReferencePath(self, asset_path, referencing_layer_path, asset_is_layer):
        # Python procedurals are resolved by the USD plugin, not as file paths.
        if asset_path.endswith('.py'):
            return asset_path

        if not self.output_dir:
            return asset_path

        abs_asset_path = hou.text.normpath(hou.text.abspath(asset_path, self.output_dir))
        output_dir_norm = self.output_dir.rstrip('/').rstrip('\\') + '/'

        if not abs_asset_path.lower().startswith(output_dir_norm.lower()):
            return abs_asset_path

        return hou.text.relpath(abs_asset_path, referencing_layer_path)

    def processSavePath(self, asset_path, referencing_layer_path, asset_is_layer):
        if self.output_dir:
            return hou.text.abspath(asset_path, self.output_dir)
        return asset_path

    def processLayer(self, layer):
        layer_data = layer.customLayerData
        layer_data['hip_file'] = hou.hipFile.path()
        layer_data['create_time'] = time.ctime()
        layer_data['user'] = getpass.getuser()
        layer.customLayerData = layer_data
        return True


################################################################################
# In order to be considered for output processing, this python module
# implements the function that returns a processor object.
#
def usdOutputProcessor():
    return AvalonPublish
