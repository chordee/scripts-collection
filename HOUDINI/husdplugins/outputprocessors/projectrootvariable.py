import os
import re
import sys

import hou
import husd.outputprocessor as base


VARIABLE_NAME = 'PROJECT_ROOT'
PARAM_NAME = 'projectrootvariable_project_root'
CASE_INSENSITIVE = sys.platform.startswith('win')
# A bare Windows drive letter ("C:", from _normalize("C:\\") / "C:/" / "C:")
# is a filesystem root just like "/" on POSIX, but rstrip('/') never empties
# it out the way it does "/" -> "", so it needs its own check.
_WINDOWS_DRIVE_ROOT_RE = re.compile(r'^[A-Za-z]:$')


def _normalize(path):
    # hou.text.normpath collapses redundant separators and "." / ".." segments;
    # then force forward slashes and strip trailing slash so prefix comparison
    # has a single canonical form on both sides.
    return hou.text.normpath(path).replace('\\', '/').rstrip('/')


def _match_key(path):
    return path.casefold() if CASE_INSENSITIVE else path


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
        group = hou.ParmTemplateGroup()
        group.append(hou.StringParmTemplate(
            PARAM_NAME,
            'Project Root',
            1,
            string_type=hou.stringParmType.FileReference,
            file_type=hou.fileType.Directory,
        ))
        return group.asDialogScript()

    def beginSave(self, config_node, config_overrides, lop_node, t, stage_variables):
        super().beginSave(config_node, config_overrides, lop_node, t, stage_variables)

        raw = self.evalConfig(PARAM_NAME, config_node, config_overrides, t) or ''
        expanded = hou.text.expandString(raw).strip() if raw else ''

        if not expanded:
            self.enabled = False
            self.project_root = ''
            self.project_root_key = ''
            return

        if not os.path.isabs(expanded):
            raise ValueError('Project Root must be an absolute path')

        project_root = _normalize(expanded)
        if not project_root or _WINDOWS_DRIVE_ROOT_RE.match(project_root):
            raise ValueError('Filesystem root cannot be used as Project Root')

        self.project_root = project_root
        self.project_root_key = _match_key(self.project_root) + '/'
        self.enabled = True

    def processReferencePath(self, asset_path, referencing_layer_path, asset_is_layer):
        if not self.enabled:
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

    def processLayer(self, layer, layersavepath=None):
        if not self.enabled:
            return False

        try:
            existing = dict(layer.expressionVariables)
        except AttributeError:
            return False

        if existing.get(VARIABLE_NAME) == self.project_root:
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
