import maya.cmds as cmds
from pxr import Sdf, Usd, UsdShade, UsdGeom

def Same(arg):
    return arg

def FloatToVector(arg):
    return (arg, arg, arg)

def MayaArrayToVector(arg):
    return arg[0]

def IntToString(arg):
    return str(arg)

def VectorToVector4(arg):
    return (arg[0][0], arg[0][1], arg[0][2], 1)

def MayaArrayToInt(arg):
    return int(arg[0][0])

def post_Nothong():
    return


class RedshiftToUSD:

    def __init__(self, shadingGroups = None, scope = 'Looks', filename = None):

        if shadingGroups == None or type(shadingGroups) is not list:
            return

        if len(shadingGroups) == 0:
            return 

        if False in [(cmds.nodeType(shadingGroup) == 'shadingEngine') for shadingGroup in shadingGroups]:
            return

        self.translator = { 
            'RedshiftMaterial': {
                'info:id': {'name': 'redshift::Material'},
                'diffuse_color': {'name': 'diffuse_color', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'diffuse_weight': {'name': 'diffuse_weight', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'diffuse_roughness': {'name': 'diffuse_roughness', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'transl_color': {'name': 'transl_color', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'transl_weight': {'name': 'transl_weight', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'opacity_color': {'name': 'opacity_color', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'refl_color': {'name': 'refl_color', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'refl_weight': {'name': 'refl_weight', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'refl_roughness': {'name': 'refl_roughness', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'refl_samples': {'name': 'refl_samples', 'type': Sdf.ValueTypeNames.Int, 'convert': Same},
                'refl_brdf': {'name': 'refl_brdf', 'type': Sdf.ValueTypeNames.Token, 'convert': IntToString},
                'refl_aniso': {'name': 'refl_aniso', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'refl_aniso_rotation': {'name': 'refl_aniso_rotation', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'refl_fresnel_mode': {'name': 'refl_fresnel_mode', 'type': Sdf.ValueTypeNames.Token, 'convert': IntToString},
                'refl_reflectivity': {'name': 'refl_reflectivity', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'refl_edge_tint': {'name': 'refl_edge_tint', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'refl_metalness': {'name': 'refl_metalness', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'refl_ior': {'name': 'refl_ior', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},

                'refr_color': {'name': 'refr_color', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'refr_weight': {'name': 'refr_weight', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'refr_roughness': {'name': 'refr_roughness', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'refr_samples': {'name': 'refr_samples', 'type': Sdf.ValueTypeNames.Int, 'convert': Same},
                'refr_ior': {'name': 'refr_ior', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'refr_use_base_IOR': {'name': 'refr_use_base_IOR', 'type': Sdf.ValueTypeNames.Int, 'convert': Same},

                'coat_color': {'name': 'coat_color', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'coat_weight': {'name': 'coat_weight', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'coat_roughness': {'name': 'coat_roughness', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'coat_samples': {'name': 'coat_samples', 'type': Sdf.ValueTypeNames.Int, 'convert': Same},
                'coat_brdf': {'name': 'coat_brdf', 'type': Sdf.ValueTypeNames.Token, 'convert': IntToString},
                'coat_reflectivity': {'name': 'coat_reflectivity', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'coat_transmittance': {'name': 'coat_transmittance', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'coat_thickness': {'name': 'coat_thickness', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},

                'bump_input': {'name': 'bump_input', 'type': Sdf.ValueTypeNames.Int, 'convert': MayaArrayToInt},
                'emission_color': {'name': 'emission_color', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'emission_weight': {'name': 'emission_weight', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},

                'ss_unitsMode': {'name': 'ss_unitsMode', 'type': Sdf.ValueTypeNames.Token, 'convert': IntToString},
                'ss_extinction_coeff': {'name': 'ss_extinction_coeff', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'ss_extinction_scale': {'name': 'ss_extinction_scale', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'ss_scatter_coeff': {'name': 'ss_scatter_coeff', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'ss_amount': {'name': 'ss_amount', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'ss_phase': {'name': 'ss_phase', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'ss_samples': {'name': 'ss_samples', 'type': Sdf.ValueTypeNames.Int, 'convert': Same},

                'ms_amount': {'name': 'ms_amount', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'ms_radius_scale': {'name': 'ms_radius_scale', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'ms_mode': {'name': 'ms_mode', 'type': Sdf.ValueTypeNames.Token, 'convert': IntToString},
                'ms_samples': {'name': 'ms_samples', 'type': Sdf.ValueTypeNames.Int, 'convert': Same},
                'ms_include_mode': {'name': 'ms_include_mode', 'type': Sdf.ValueTypeNames.Token, 'convert': IntToString},

                'ms_color0': {'name': 'ms_color0', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'ms_weight0': {'name': 'ms_weight0', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'ms_radius0': {'name': 'ms_radius0', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},

                'ms_color1': {'name': 'ms_color1', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'ms_weight1': {'name': 'ms_weight1', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'ms_radius1': {'name': 'ms_radius1', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},

                'ms_color2': {'name': 'ms_color2', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'ms_weight2': {'name': 'ms_weight2', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'ms_radius2': {'name': 'ms_radius2', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},

                'diffuse_direct': {'name': 'diffuse_direct', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'diffuse_indirect': {'name': 'diffuse_indirect', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},

                'refl_direct': {'name': 'refl_direct', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'refl_indirect': {'name': 'refl_indirect', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'refl_isGlossiness': {'name': 'refl_isGlossiness', 'type': Sdf.ValueTypeNames.Int, 'convert': Same},

                'coat_direct': {'name': 'coat_direct', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'coat_indirect': {'name': 'coat_indirect', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'coat_isGlossiness': {'name': 'coat_isGlossiness', 'type': Sdf.ValueTypeNames.Int, 'convert': Same},

                'outColor': {'name': 'outColor', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},

                'post_proc': self.post_Nothing
            },
            'displacementShader': {
                'info:id': {'name': 'redshift::Displacement'},
                'displacement': {'name': 'out', 'type': Sdf.ValueTypeNames.Float3, 'convert': FloatToVector},
                'scale': {'name': 'scale', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},

                'post_proc': self.post_Nothing
            },
            'file':{
                'info:id': {'name': "redshift::TextureSampler"},
                'output': {'name': 'out', 'type': Sdf.ValueTypeNames.Float3, 'convert': MayaArrayToVector},
                'outColor': {'name': 'outColor', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'outAlpha': {'name': 'outColor', 'type': Sdf.ValueTypeNames.Color3f, 'convert': FloatToVector},
                'fileTextureName': {'name': 'tex0', 'type': Sdf.ValueTypeNames.Asset, 'convert': Same},

                'post_proc': self.post_TextureSampler
            },
            'RedshiftNormalMap':{
                'info:id': {'name': 'redshift::BumpMap'},

                'post_proc': self.post_Nothing
            },
            'RedshiftColorCorrection':{
                'info:id': {'name': 'redshift::RSColorCorrection'},
                'input': {'name': 'input', 'type': Sdf.ValueTypeNames.Color4f, 'convert': VectorToVector4},
                'outColor': {'name': 'outColor', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'gamma': {'name': 'gamma', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'contrast': {'name': 'contrast', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'hue': {'name': 'hue', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'saturation': {'name': 'saturation', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                'level': {'name': 'level', 'type': Sdf.ValueTypeNames.Float, 'convert': Same},
                
                'post_proc': self.post_Nothing
            },
            'setRange': {
                'info:id': {'name': 'redshift::RSColorRange'},
                'value': {'name': 'input', 'type': Sdf.ValueTypeNames.Color4f, 'convert': VectorToVector4},
                'outValue': {'name': 'outColor', 'type': Sdf.ValueTypeNames.Color3f, 'convert': MayaArrayToVector},
                'min': {'name': 'new_min', 'type': Sdf.ValueTypeNames.Color4f, 'convert': VectorToVector4},
                'max': {'name': 'new_max', 'type': Sdf.ValueTypeNames.Color4f, 'convert': VectorToVector4},
                'oldMin': {'name': 'old_min', 'type': Sdf.ValueTypeNames.Color4f, 'convert': VectorToVector4},
                'oldMax': {'name': 'old_max', 'type': Sdf.ValueTypeNames.Color4f, 'convert': VectorToVector4},

                'post_proc': self.post_Nothing
            }
        }
        self.shadingGroups = shadingGroups
        self.scope = scope
        self.filename = filename
        self.Run()
        


    def Run(self):
        self.stage = Usd.Stage.CreateNew(self.filename)
        root = UsdGeom.Scope.Define(self.stage, '/' + self.scope)

        for shadingGroup in self.shadingGroups:
            usdShadingGroup = UsdShade.Material.Define(self.stage, root.GetPath().AppendChild(shadingGroup))
            usdShaderCollector = UsdShade.Shader.Define(self.stage, usdShadingGroup.GetPath().AppendChild(shadingGroup))
            usdShaderCollector.CreateIdAttr('redshift_usd_material')
            usdShaderCollector.CreateOutput('outputs:Shader', Sdf.ValueTypeNames.Token)
            usdShadingGroup.CreateOutput('Redshift:surface', Sdf.ValueTypeNames.Token).ConnectToSource(usdShaderCollector, 'outputs:Shader')

            surfaceShaders = cmds.listConnections(shadingGroup + '.surfaceShader')
            if len(surfaceShaders) > 0:
                surfaceShader = surfaceShaders[0]
                usdShaderCollector.CreateInput('Surface', Sdf.ValueTypeNames.Color3f)
                self.rebuildShader(source_shader = surfaceShader, usd_target = usdShaderCollector, source_attr = 'outColor', target_attr = 'Surface', usdShadingGroup = usdShadingGroup)
            
            displacementShaders = cmds.listConnections(shadingGroup + '.displacementShader')
            if len(displacementShaders) > 0:
                displacementShader = displacementShaders[0]
                usdShaderCollector.CreateInput('Displacement', Sdf.ValueTypeNames.Float3)
                self.rebuildShader(source_shader = displacementShader, usd_target = usdShaderCollector, source_attr = 'displacement', target_attr = 'Displacement', usdShadingGroup = usdShadingGroup)


    def rebuildShader(self, source_shader, usd_target, source_attr, target_attr ,usdShadingGroup):

        nodeType = cmds.nodeType(source_shader)
        
        if nodeType in self.translator.keys():
            attr_table = self.translator[cmds.nodeType(source_shader)]
            if source_shader not in [x.GetName() for x in usdShadingGroup.GetPrim().GetAllChildren()]:
                usdShader = UsdShade.Shader.Define(self.stage, usdShadingGroup.GetPath().AppendChild(source_shader))
                usdShader.CreateIdAttr(self.translator[nodeType]['info:id']['name'])
            else:
                usdShader = UsdShade.Shader.Get(self.stage, usdShadingGroup.GetPath().AppendChild(source_shader))

            if source_attr in attr_table.keys():
                if attr_table[source_attr]['name'] not in [ x.GetBaseName() for x in usdShader.GetOutputs() ]:
                    usdShaderOutput = usdShader.CreateOutput(attr_table[source_attr]['name'], attr_table[source_attr]['type'])
                    
                else:
                    usdShaderOutput = usdShader.GetOutput(attr_table[source_attr]['name'])
                usd_target.GetInput(target_attr).ConnectToSource(usdShaderOutput)
            else:
                return

            for attr in cmds.listAttr(source_shader, hd = True):
                if attr in attr_table.keys():
                    usdShader.CreateInput(attr_table[attr]['name'], attr_table[attr]['type']).Set(attr_table[attr]['convert'](cmds.getAttr(source_shader + '.' + attr)))
            
            connections = iter(cmds.listConnections(source_shader, d = False, c = True, p = True))
            for connectDest, connectSource in zip(connections, connections):
                connectSourceNode = connectSource.split('.')[0]
                connectSourceAttr = connectSource.split('.')[-1]
                connectDestNode = connectDest.split('.')[0]
                connectDestAttr = connectDest.split('.')[-1]
                if connectDestAttr in attr_table.keys():
                    self.rebuildShader(source_shader = connectSourceNode, usd_target = usdShader, source_attr = connectSourceAttr, target_attr = attr_table[connectDestAttr]['name'], usdShadingGroup = usdShadingGroup)
            attr_table['post_proc'](source_shader, usdShader)

        else:
            return

    def post_Nothing(self, mayaShader, usdShader):
        return
        
    def post_TextureSampler(self, mayaShader, usdShader):
        return

    def Save(self):
        self.stage.Save()

        

if __name__ == '__main__':
    filename = 'c:/users/chordee.lin/desktop/test_redshoft_materials.usda'
    shadingGroups = cmds.ls(sl = True)

    tmp = RedshiftToUSD(shadingGroups = shadingGroups, filename = filename)
    tmp.Save()
    del tmp
