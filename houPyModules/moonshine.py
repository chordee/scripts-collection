import numpy as np
import hou
import importlib

try:
    import scipy as sp
except ImportError:
    pass

from typing import Optional, Union, Type


def matrixManipulate(matrix: Union[hou.Matrix4, hou.Matrix3], data: np.ndarray) -> Optional[np.ndarray]:
    """
    matrixManipulate Use matrix manipulate numpy vecter array

    Args:
        matrix (Union[hou.Matrix4, hou.Matrix3]): Houdini Matrix3 or Matrix4
        data (np.ndarray): numpy vector array

    Returns:
        Optional[np.ndarray]: numpy vector array after manipulated.
    """

    if data.shape[1] != 3:
        return None
    if type(matrix) is hou.Matrix3:
        matrix = hou.Matrix4(matrix)
    mat = np.matrix(matrix.asTupleOfTuples())
    ext = np.ones((data.shape[0], 1), dtype=np.float32)
    concat = np.concatenate((data, ext), axis=1)
    res = mat.T.dot(concat.T)[:3, :].T
    return res


def numpyArrayFromGeoPoints(geo: hou.Geometry, attr: str = 'P') -> Optional[np.ndarray]:
    """
    numpyArrayFromGeoPoints Convert geometry point attribute to numpy array

    Args:
        geo (hou.Geometry): Houdini Geometry
        attr (str, optional): Name of attribute. Defaults to 'P'.

    Returns:
        Optional[np.ndarray]: numpy array
    """

    point_attr = geo.findPointAttrib(attr)
    if not point_attr:
        return None
    if point_attr.dataType() != hou.attribData.Int and point_attr.dataType() != hou.attribData.Float:
        return None
    size = point_attr.size()
    if point_attr.dataType == hou.attribData.Int:
        data = np.frombuffer(geo.pointFloatAttribValuesAsString(attr), dtype=np.int32).reshape(-1, size)
    else:
        data = np.frombuffer(geo.pointFloatAttribValuesAsString(attr), dtype=np.float32).reshape(-1, size)
    return data

def convolve2D(image: np.ndarray, kernel: np.ndarray, padding: int = 0, strides:int = 1, preExpand: bool = False, pad_mode:str = 'edge') -> np.ndarray:
    if preExpand:
        image = np.pad(image, 1, pad_mode)

    # Gather Shapes of Kernel + Image + Padding
    xKernShape = kernel.shape[0]
    yKernShape = kernel.shape[1]
    xImgShape = image.shape[0]
    yImgShape = image.shape[1]

    # Shape of Output Convolution
    xOutput = int(((xImgShape - xKernShape + 2 * padding) / strides) + 1)
    yOutput = int(((yImgShape - yKernShape + 2 * padding) / strides) + 1)
    output = np.zeros((xOutput, yOutput), dtype=image.dtype)

    # Apply Equal Padding to All Sides
    if padding != 0:
        imagePadded = np.zeros((image.shape[0] + padding*2, image.shape[1] + padding*2))
        imagePadded[int(padding):int(-1 * padding), int(padding):int(-1 * padding)] = image
        print(imagePadded)
    else:
        imagePadded = image

    # Iterate through image
    for y in range(image.shape[1]):
        # Exit Convolution
        if y > image.shape[1] - yKernShape:
            break
        # Only Convolve if y has gone down by the specified Strides
        if y % strides == 0:
            for x in range(image.shape[0]):
                # Go to next row once kernel is out of bounds
                if x > image.shape[0] - xKernShape:
                    break
                try:
                    # Only Convolve if x has moved by the specified Strides
                    if x % strides == 0:
                        output[x, y] = (kernel * imagePadded[x: x + xKernShape, y: y + yKernShape]).sum()
                except:
                    break

    return output

if importlib.util.find_spec('scipy') is not None:
    def scipy_convolve2d(image: np.ndarray, kernel: np.ndarray, mode: str = 'same', boundary: str = 'symm') -> np.ndarray:
        output = sp.signal.convolve2d(image, kernel, mode = mode, boundary = boundary)
        return output