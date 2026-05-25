"""Tests for chd_toolkits.core 2D convolution helpers.

``core`` imports ``hou`` at module level so this whole file is skipped
under plain Python; run via ``python tests/run_hython.py``.
"""

import numpy as np
import pytest

pytest.importorskip("hou")

from chd_toolkits.core import convolve2d


# ---------------------------------------------------------------------------
# Basic shape / value cases
# ---------------------------------------------------------------------------


def test_convolve2d_identity_kernel_preserves_image():
    img = np.arange(9, dtype=np.float32).reshape(3, 3)
    kernel = np.array([[1.0]])
    out = convolve2d(img, kernel)
    assert out.shape == (3, 3)
    np.testing.assert_allclose(out, img)


def test_convolve2d_sum_kernel_2x2():
    img = np.ones((4, 4), dtype=np.float32)
    kernel = np.ones((2, 2), dtype=np.float32)
    out = convolve2d(img, kernel)
    assert out.shape == (3, 3)
    np.testing.assert_allclose(out, np.full((3, 3), 4.0))


def test_convolve2d_stride_reduces_output():
    img = np.ones((4, 4), dtype=np.float32)
    kernel = np.ones((2, 2), dtype=np.float32)
    out = convolve2d(img, kernel, strides=2)
    assert out.shape == (2, 2)


def test_convolve2d_padding_preserves_shape_for_3x3_kernel():
    img = np.ones((4, 4), dtype=np.float32)
    kernel = np.ones((3, 3), dtype=np.float32)
    out = convolve2d(img, kernel, padding=1)
    assert out.shape == (4, 4)


# ---------------------------------------------------------------------------
# dtype promotion
# ---------------------------------------------------------------------------


def test_convolve2d_promotes_int_image_with_float_kernel():
    img = np.ones((3, 3), dtype=np.int32)
    kernel = np.full((2, 2), 0.5, dtype=np.float32)
    out = convolve2d(img, kernel)
    assert np.issubdtype(out.dtype, np.floating)
    np.testing.assert_allclose(out, np.full((2, 2), 2.0))


# ---------------------------------------------------------------------------
# Kernel-flip property (true convolution, matches scipy_convolve2d)
# ---------------------------------------------------------------------------


def test_convolve2d_flips_kernel_before_summing():
    """An asymmetric kernel + impulse should expose the flip."""
    img = np.zeros((3, 3), dtype=np.float32)
    img[0, 0] = 1.0
    kernel = np.array([[1, 10, 100]], dtype=np.float32)
    out = convolve2d(img, kernel)
    # Flipped kernel = [[100, 10, 1]]
    # Window at (0, 0) = img[0:1, 0:3] = [1, 0, 0]
    # out[0, 0] = 100*1 + 10*0 + 1*0 = 100   (cross-correlation would give 1)
    assert out[0, 0] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_convolve2d_rejects_1d_image():
    with pytest.raises(ValueError):
        convolve2d(np.zeros(5), np.zeros((2, 2)))


def test_convolve2d_rejects_3d_image():
    with pytest.raises(ValueError):
        convolve2d(np.zeros((4, 4, 3)), np.zeros((2, 2)))


def test_convolve2d_rejects_1d_kernel():
    with pytest.raises(ValueError):
        convolve2d(np.zeros((4, 4)), np.zeros(3))


def test_convolve2d_rejects_zero_strides():
    with pytest.raises(ValueError):
        convolve2d(np.zeros((4, 4)), np.zeros((2, 2)), strides=0)


def test_convolve2d_rejects_negative_padding():
    with pytest.raises(ValueError):
        convolve2d(np.zeros((4, 4)), np.zeros((2, 2)), padding=-1)


def test_convolve2d_rejects_kernel_larger_than_padded_image():
    with pytest.raises(ValueError):
        convolve2d(np.zeros((2, 2)), np.zeros((3, 3)))


# ---------------------------------------------------------------------------
# scipy_convolve2d (only present if scipy is installed)
# ---------------------------------------------------------------------------


def test_scipy_convolve2d_matches_manual_calculation():
    pytest.importorskip("scipy.signal")
    from chd_toolkits.core import scipy_convolve2d  # noqa: WPS433

    img = np.array([[1, 2], [3, 4]], dtype=np.float32)
    kernel = np.array([[1, 0], [0, 1]], dtype=np.float32)
    # mode='valid' → (1,1) output; flipped kernel == kernel (palindrome 2x2 here):
    # [[1,0],[0,1]] · [[1,2],[3,4]] sum = 1 + 4 = 5
    out = scipy_convolve2d(img, kernel, mode="valid")
    assert out.shape == (1, 1)
    assert out[0, 0] == pytest.approx(5.0)


def test_scipy_convolve2d_and_convolve2d_agree_on_asymmetric_kernel():
    pytest.importorskip("scipy.signal")
    from chd_toolkits.core import scipy_convolve2d  # noqa: WPS433

    rng = np.random.default_rng(seed=42)
    img = rng.random((6, 6), dtype=np.float32)
    kernel = np.array(
        [[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=np.float32
    )
    naive = convolve2d(img, kernel)
    sci = scipy_convolve2d(img, kernel, mode="valid")
    np.testing.assert_allclose(naive, sci, rtol=1e-5)
