import OpenEXR
import Imath

import numpy as np


def get_width_height_from_exr(exr):
    header = exr.header()
    dataWindow = header['dataWindow']

    width = dataWindow.max.x - dataWindow.min.x + 1
    height = dataWindow.max.y - dataWindow.min.y + 1

    return np.array([width, height])


def get_rgb_from_exr(exr):
    header = exr.header()

    channels = header['channels']
    pixel_type = str(channels['R'].type)
    if pixel_type == "HALF":
        pixel_type = np.float16
    elif pixel_type == "FLOAT":
        pixel_type = np.float32
    else:
        return

    dataWindow = header['dataWindow']

    width = dataWindow.max.x - dataWindow.min.x + 1

    (r, g, b) = exr.channels("RGB")
    r = np.frombuffer(r, dtype=pixel_type).reshape(-1, width)
    g = np.frombuffer(g, dtype=pixel_type).reshape(-1, width)
    b = np.frombuffer(b, dtype=pixel_type).reshape(-1, width)

    clr = np.stack((r, g, b), axis=-1)

    return clr


def write_rgb_to_exr(filepath, clr, pixelType='FLOAT'):
    height = clr.shape[0]
    width = clr.shape[1]
    header = OpenEXR.Header(width, height)

    pixel_type = OpenEXR.FLOAT
    if pixelType == "HALF":
        pixel_type = OpenEXR.HALF
    elif pixelType != "FLOAT":
        return

    if clr.shape[2] == 4:
        for ch in 'BGRA':
            header['channels'][ch] = Imath.Channel(
                Imath.PixelType(pixel_type))
        header['order'] = b'C { r g b } A'
    elif clr.shape[2] == 3:
        for ch in 'BGR':
            header['channels'][ch] = Imath.Channel(
                Imath.PixelType(pixel_type))
        header['order'] = b'C { r g b } A'
    else:
        return

    exr_file = OpenEXR.OutputFile(filepath, header)

    exr_file.writePixels(
        {"R": clr[:, :, 0].reshape(-1).astype(np.float32 if pixelType == 'FLOAT' else np.float16).tobytes(),
         "G": clr[:, :, 1].reshape(-1).astype(np.float32 if pixelType == 'FLOAT' else np.float16).tobytes(),
         "B": clr[:, :, 2].reshape(-1).astype(np.float32 if pixelType == 'FLOAT' else np.float16).tobytes()})

    if clr.shape[2] == 4:
        exr_file.writePixels(
            {"R": clr[:, :, 3].reshape(-1).astype(np.float32 if pixelType == 'FLOAT' else np.float16).tobytes()})

    exr_file.close()


if __name__ == "__main__":
    exr_file = OpenEXR.InputFile("D:/Downloads/uv_rgb_texture.exr")

    header = exr_file.header()
    for key in header.keys():
        print("{0} / format: {1} / value: {2}".format(key,
                                                      type(header[key]), header[key]))

    print(header['channels'])
    channels = header['channels']
    k = channels['R']
    print(str(k.type))
    for i in dir(k.type):
        print(i)
    dataWindow = header['dataWindow']

    width = dataWindow.max.x - dataWindow.min.x + 1
    height = dataWindow.max.y - dataWindow.min.y + 1
    clr = get_rgb_from_exr(exr_file)
