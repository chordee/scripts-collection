
import json,re
json_file = 'd:/dev/mingShip_shaders.json'
types = []
texs = []

with open(json_file, 'r') as f:
    data = json.load(f)

def getNode(node, par, connect_to, connect_from, shading_group):
    if 'name' in node.keys():
        #print(node['name'] + ' - ' + str(node['type']))
        types.append(node['type'])

        if node['type'] == 'file':
            texs.append(node['name'])
            texs.append(node['fileTextureName'])
        if node['type'] == 'displacementShader':
            for s in node:
                print(s + ': ')
                print(node[s])
        #print(shading_group + ': ' + par + '.' + connect_to + ' <- ' + node['name'] + '.' + connect_from)  
        #print('===')
    for attr in node:
        if type(node[attr]) is dict:
            if 'node' in node[attr].keys():
                getNode(node[attr]['node'], node['name'], attr, node[attr]['slot'], shading_group)

        
if __name__ == '__main__':
    for d in data:
        for n in d:
            for s in d[n]:
                getNode(d[n][s], n, s, '', n)

print(list(set(types)))

tmp = list(set(texs))
re_str = '.*1001.*'
for t in tmp:
    r = re.search(re_str, t) 
    if r is not None:
        print(t)

