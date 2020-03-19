data = {'file': {'name' : 'texture',
				'map': 'fileTextureName',
				'width' : 'filterWidth',
				'clr': 'outColor',
				'defclrr' : 'defaultColorR',
				'defclrg' : 'defaultColorG',
				'defclrb' : 'defaultColorB',
				'srccolorspace' : 'colorSpace',

				},

		'aiStandardSurface' : {'name':'principledshader',
								'albedomul' : 'base',
								'basecolor' : 'baseColor',
								'basecolorr' : 'baseColorR',
								'basecolorg' : 'baseColorG',
								'basecolorb' : 'baseColorB',
								'ssscolor' : 'subsurfaceColor',
								'ssscolorr' : 'subsurfaceColorR',
								'ssscolorg' : 'subsurfaceColorG',
								'ssscolorb' : 'subsurfaceColorB',
								'rough' : 'specularRoughness',
								'opaccolor' : 'opacity',
								'opaccolorr' : 'opacityR',
								'opaccolorg' : 'opacityG',
								'opaccolorb' : 'opacityB',
								'reflect' : 'specular',
								'ior' : 'specularIOR',
								'sheen' : 'sheen',
								'sss' : 'subsurface',
								'transparency' : 'transmission',
								'transcolor' : 'transmissionColor',
								'transcolorr' : 'transmissionColorR',
								'transcolorg' : 'transmissionColorG',
								'transcolorb' : 'transmissionColorB',
								'baseN' : 'normalCamera',
								'metallic' : 'metalness',
								'layer' : 'outColor',
								'coat' : 'coat',
								'coatrough' : 'coatRoughness',
								'sheen' : 'sheen',
								},
		'aiNormalMap' : { 'name' : 'displacetexture',
							'outN' : 'outValue',
							'scale' : 'strength',
							'N' : 'normal',
							'normalflipy' : 'invertY',
							'normalflipx' : 'invertX',
						},
		'bump2d' : { 'name' : 'displacetexture',
					'scale' : 'bumpValue',
					'outN' : 'outNormal',
					'N' : 'normalCamera',
					'normalflipx' : 'aiFlipR',
					'normalflipy' : 'aiFlipG',
						},

		'aiCurvature' : { 'name' : 'curvature',
							'K' : 'outColor',
							'convexscale' : 'multiply',
							'concavescale' : 'multiply',
							'K' : 'outColorR',
							'K' : 'outColorG',
							'K' : 'outColorB',

						},
		'noise' : {'name' : 'turbnoise',
					'noise' : 'outColor',
					'noise' : 'outAlpha',
					'amp' : 'amplitude'  
					},
		'fractal' : {'name' : 'turbnoise',
					'noise' : 'outColor',
					'noise' : 'outAlpha',
					'amp' : 'amplitude',
					},
		0:{ 'name' : 'rampparm'},
		'aiMixShader' : { 'name' : 'layermix',
						'alpha' : 'mix',
						'A' : 'shader1',
						'B' : 'shader2',
						},
		'V Ramp' : {'name' : 'rampparm',
					'ramp' : 'outColor',
					'ramp' : 'outAlpha',
					},

		'displacementShader' : {'name' : 'displacenml',
								'scale' : 'scale',
								'amount' : 'displacement',
								},
		'lamber' : {'name':'principledshader',
					'albedomul' : 'diffuse',
					'basecolor' : 'color',
					'baseN' : 'normalCamera',
					},
		}

import json

print(data)
file = 'f:/dev/match_table.json'
file2 = 'f:/dev/script_collection/match_table.json'
match = json.dumps(data)
with open(file, 'r') as f:
	match = json.load(f)
print(type(match))
print(match['aiCurvature']['name'])

with open(file, 'w') as f:
	json.dump(data, f)

with open(file2, 'w') as f:
	json.dump(data, f)
