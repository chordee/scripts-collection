import numpy as np
import OpenEXR
import Imath
node = hou.pwd()
geo = node.geometry()

# Add code to modify contents of geo.
# Use drop down menu to select examples.

start_frame = 1
end_frame = 200
duration = end_frame - start_frame + 1
out_path = "D:/tmp/offset.exr"
out_rot_path = "D:/tmp/rot.exr"

geo2 = node.inputs()[1].geometry()

npoints = len(geo.points())

rest_position = np.frombuffer(geo.pointFloatAttribValuesAsString(
    'P', float_type=hou.numericData.Float64), dtype=np.float64).reshape(-1, 3)
rest_pscale = np.frombuffer(geo.pointFloatAttribValuesAsString(
    'pscale', float_type=hou.numericData.Float32), dtype=np.float32)

animation_position = np.zeros(
    (npoints, end_frame - start_frame + 1, 3), dtype=np.float64)
animation_pscale = np.zeros(
    (npoints, end_frame - start_frame + 1, 1), dtype=np.float32)

animation_axis = np.zeros(
    (npoints, end_frame - start_frame + 1, 3), dtype=np.float32)
animation_rot_amp = np.zeros(
    (npoints, end_frame - start_frame + 1, 1), dtype=np.float32)

for i in range(duration):
    current_frame = i + start_frame
    hou.setFrame(current_frame)
    animated_position = np.frombuffer(geo2.pointFloatAttribValuesAsString(
        'P', float_type=hou.numericData.Float64), dtype=np.float64).reshape(-1, 3)
    animated_pscale = np.frombuffer(geo2.pointFloatAttribValuesAsString(
        'pscale', float_type=hou.numericData.Float32), dtype=np.float32)

    animated_axis = np.frombuffer(geo2.pointFloatAttribValuesAsString(
        'rot_axis', float_type=hou.numericData.Float32), dtype=np.float32).reshape(-1, 3)
    animated_rot_amp = np.frombuffer(geo2.pointFloatAttribValuesAsString(
        'rot_amp', float_type=hou.numericData.Float32), dtype=np.float32)

    animation_position[:, i, :] = animated_position - rest_position
    animation_pscale[:, i, :] = (animated_pscale / rest_pscale)[:, np.newaxis]

    animation_axis[:, i, :] = animated_axis
    animation_rot_amp[:, i, :] = animated_rot_amp[:, np.newaxis]

print(animation_rot_amp)
out_openexr_header = OpenEXR.Header(duration, npoints)

for ch in 'BGRA':
    out_openexr_header['channels'][ch] = Imath.Channel(
        Imath.PixelType(OpenEXR.HALF))

out_openexr_header['order'] = b'C { r g b } A'

out = OpenEXR.OutputFile(out_path, out_openexr_header)
out_rot = OpenEXR.OutputFile(out_rot_path, out_openexr_header)


out.writePixels(
    {"R": animation_position[:, :, 0].reshape(-1).astype(np.float16).tobytes(), "G": animation_position[:, :, 2].reshape(-1).astype(np.float16).tobytes(),
     "B": animation_position[:, :, 1].reshape(-1).astype(np.float16).tobytes(), 'A': animation_pscale.reshape(-1).astype(np.float16).tobytes()})

out_rot.writePixels(
    {"R": animation_axis[:, :, 0].reshape(-1).astype(np.float16).tobytes(), "G": animation_axis[:, :, 1].reshape(-1).astype(np.float16).tobytes(),
     "B": animation_axis[:, :, 2].reshape(-1).astype(np.float16).tobytes(), 'A': animation_rot_amp.reshape(-1).astype(np.float16).tobytes()})


out.close()
out_rot.close()
