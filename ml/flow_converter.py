import numpy as np
import os.path
import EXR_utils
import sys


def flow_converter(filepaath):

    with open(filepath, mode='r') as flo:
        tag = np.fromfile(flo, np.float32, count=1)[0]
        width = np.fromfile(flo, np.int32, count=1)[0]
        height = np.fromfile(flo, np.int32, count=1)[0]

        print('tag', tag, 'width', width, 'height', height)

        nbands = 2
        tmp = np.fromfile(flo, np.float32, count=nbands * width * height)
        flow = np.resize(tmp, (int(height), int(width), int(nbands)))
        zeros = np.zeros(width * height).reshape(-1, width)
        res = np.dstack((flow, zeros[:, :, np.newaxis]))
        EXR_utils.write_rgb_to_exr(filepath.replace('flo', 'exr'), res)


if __name__ == "__main__":
    path = "F:/tmp"

    if not os.path.isdir(path):
        sys.exit(1)

    for filename in os.listdir(path):
        if filename.endswith(".flo"):
            filepath = '/'.join((path, filename))
            flow_converter(filepath)
