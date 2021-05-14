import numpy as np
import os.path as path
import matplotlib.pyplot as plt
import EXR_utils

for i in range(1, 101):

    filepath = "F:/tmp/inference/run.epoch-0-flow-field/" + \
        str(i).zfill(6)+".flo"

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
        EXR_utils.write_rgb_to_exr(filepath.replace('flo', 'exr').replace("tmp/inference/run.epoch-0-exrw-field/", "tmp/"), res)
