import os
import time

import hou
import husd.outputprocessor as base


class AvalonPublish(base.OutputProcessor):

    def __init__(self):
        super(AvalonPublish, self).__init__()
        self.output_dir = None

    @staticmethod
    def name():
        return 'avalonpublish'

    @staticmethod
    def displayName():
        return 'Avalon Publish'

    def beginSave(self, config_node, config_overrides, lop_node, t, stage_variables):

        super(AvalonPublish, self).beginSave(
            config_node, config_overrides, lop_node, t, stage_variables)

        self.output_usd = self.evalConfig('lopoutput', config_node, config_overrides, t)
        (self.output_dir, filename) = os.path.split(self.output_usd)

    def processReferencePath(
            self, asset_path, referencing_layer_path, asset_is_layer):

        # If the asset_path is in one of the search directories, generate the
        # asset_path as a search path. Don't use search paths for save paths,
        # which must be returned as full paths. Also, search paths only work
        # on layer files, so ignore other asset types.

        if asset_path == 'invokegraph.py':
            # Houdini Ocean Procedural -- Chordee
            return asset_path

        abs_asset_path = hou.text.abspath(asset_path, self.output_dir)
        abs_asset_path = hou.text.normpath(abs_asset_path)

        if not self.output_dir:
            return abs_asset_path

        if not abs_asset_path.startswith(self.output_dir):
            return abs_asset_path
        if abs_asset_path.startswith(self.output_dir):
            rel_path = hou.text.relpath(abs_asset_path, referencing_layer_path)
            return rel_path
        return asset_path

    def processSavePath(
            self, asset_path, referencing_layer_path, asset_is_layer):

        # Treat asset paths as being relative to the output path.
        if self.output_dir:
           return hou.text.abspath(asset_path, self.output_dir)

        return asset_path

    def processLayer(self, layer):
        layer_data = layer.customLayerData
        layer_data['hip_file'] = hou.hipFile.path()
        layer_data['create_time'] = time.ctime()
        layer_data['user'] = os.getlogin()
        layer.customLayerData = layer_data
        return True


################################################################################
# In order to be considered for output processing, this python module
# implements the function that returns a processor object.
#
def usdOutputProcessor():
    return AvalonPublish
