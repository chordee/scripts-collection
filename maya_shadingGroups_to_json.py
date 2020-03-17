
import maya.cmds as cmds
import json
json_file = 'd:/dev/mingShip_shaders.json'

sels = cmds.ls(sl = 1)
sg_data = []
i = 0

def nodeInfo(node):
    des_data = {}
    des_data = {'name' : node}
    
    node_type = cmds.nodeType(node)
    des_data['type'] = node_type
    if node_type == 'file':
        attrs = cmds.listAttr(node, hd = True, v = True)
        for attr in attrs:
            try:
                v = cmds.getAttr(node + '.' + attr, x = True, asString = True )
                des_data[attr] = v
            except:
                pass
        return des_data
    else:
        res = cmds.listConnections(node, d = False, c = True, p = True) or list()
        cons = iter(res)
        for s,d in zip(cons, cons):
            sn = s.split('.')[0]
            sa = s.split('.')[-1]
            dn = d.split('.')[0]
            da = d.split('.')[-1]
            des_data[sa]= {'slot' : da}
            node_data = nodeInfo(dn)
            des_data[sa]['node'] = node_data
        attrs = cmds.listAttr(node, hd = True, v = True)
        for attr in attrs:
            if (node + '.' + attr) not in res:
                try:
                    v = cmds.getAttr(node + '.' + attr, x = True, asString = True)
                    des_data[attr] = v
                except:
                    pass
        return des_data


for sel in sels:
    shader_data = {}
    volume_data = {}
    displace_data = {}
    shaders = cmds.listConnections(sel+'.surfaceShader')
    volumes = cmds.listConnections(sel+'.volumeShader')
    displaces = cmds.listConnections(sel+'.displacementShader')
    if shaders != None:
        shader_data = nodeInfo(shaders[0])
    if volumes != None:
        volume_data = nodeInfo(volumes[0])
    if displaces != None:
        displace_data = nodeInfo(displaces[0])

    sg_data.append({sel : {'surfaceShader' : shader_data, 'volumeShader' : volume_data, 'displacementShader' : displace_data}})


with open(json_file, 'w') as f:
    json.dump(sg_data, f, ensure_ascii = False)
        
        