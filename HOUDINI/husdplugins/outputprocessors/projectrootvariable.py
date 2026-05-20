import os
import sys

import hou
import husd.outputprocessor as base


VARIABLE_NAME = 'PROJECT_ROOT'
PARAM_NAME = 'projectrootvariable_project_root'
CASE_INSENSITIVE = sys.platform.startswith('win')


def _normalize(path):
    # hou.text.normpath collapses redundant separators and "." / ".." segments;
    # then force forward slashes and strip trailing slash so prefix comparison
    # has a single canonical form on both sides.
    return hou.text.normpath(path).replace('\\', '/').rstrip('/')


def _match_key(path):
    return path.lower() if CASE_INSENSITIVE else path


class ProjectRootVariable(base.OutputProcessor):

    def __init__(self):
        super().__init__()
        self.enabled = False
        self.project_root = ''
        self.project_root_key = ''

    @staticmethod
    def name():
        return 'projectrootvariable'

    @staticmethod
    def displayName():
        return 'Project Root Variable'

    @staticmethod
    def parameters():
        template = hou.StringParmTemplate(
            PARAM_NAME,
            'Project Root',
            1,
            string_type=hou.stringParmType.FileReference,
            file_type=hou.fileType.Directory,
        )
        return template.asDialogScript()

    def beginSave(self, config_node, config_overrides, lop_node, t, stage_variables):
        super().beginSave(config_node, config_overrides, lop_node, t, stage_variables)

        raw = self.evalConfig(PARAM_NAME, config_node, config_overrides, t, '') or ''
        expanded = hou.text.expandString(raw).strip() if raw else ''

        if not expanded:
            self.enabled = False
            self.project_root = ''
            self.project_root_key = ''
            return

        self.project_root = _normalize(expanded)
        self.project_root_key = _match_key(self.project_root) + '/'
        self.enabled = True

    def processReferencePath(self, asset_path, referencing_layer_path, asset_is_layer):
        if not self.enabled:
            return asset_path

        if '`' in asset_path or '${' in asset_path:
            return asset_path

        # PROJECT_ROOT only rewrites the beginning of absolute paths;
        # relative paths are passed through untouched.
        if not os.path.isabs(asset_path):
            return asset_path

        normalized = _normalize(asset_path)

        if not _match_key(normalized).startswith(self.project_root_key):
            return asset_path

        rel = normalized[len(self.project_root):].lstrip('/')
        return '`"${' + VARIABLE_NAME + '}/' + rel + '"`'

    def processLayer(self, layer):
        if not self.enabled:
            return False

        try:
            existing = dict(layer.expressionVariables)
        except AttributeError:
            return False

        existing[VARIABLE_NAME] = self.project_root
        layer.expressionVariables = existing
        return True


################################################################################
# In order to be considered for output processing, this python module
# implements the function that returns a processor object.
#
def usdOutputProcessor():
    return ProjectRootVariable
