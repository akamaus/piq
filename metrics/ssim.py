""" This module implements Structural Similarity (SSIM) index in PyTorch.

Implementation of classes and functions from this module are inspired by Gongfan Fang's implementation:
https://github.com/VainF/pytorch-msssim
"""
import torch

import torch.nn.functional as F

from typing import Union


def structural_similarity(x: torch.Tensor, y: torch.Tensor, win_size: int = 11, win_sigma: float = 1.5,
                          data_range: Union[int, float] = 255, size_average: bool = True, full: bool = False,
                          k1: float = 0.01, k2: float = 0.03) -> torch.Tensor:
    """Interface of Structural Similarity (SSIM) index.

    Args:
        x: Batch of images. Required to be 4D, channels first (N,C,H,W).
        y: Batch of images. Required to be 4D, channels first (N,C,H,W).
        win_size: The side-length of the sliding window used in comparison. Must be an odd value.
        win_sigma: Sigma of normal distribution.
        data_range: Value range of input images (usually 1.0 or 255).
        size_average: If size_average=True, ssim of all images will be averaged as a scalar.
        full: Return sc or not.
        k1: Algorithm parameter, K1 (small constant, see [1]).
        k2: Algorithm parameter, K2 (small constant, see [1]).
            Try a larger K2 constant (e.g. 0.4) if you get a negative or NaN results.

    Returns:
        Value of Structural Similarity (SSIM) index.

    References:
        .. [1] Wang, Z., Bovik, A. C., Sheikh, H. R., & Simoncelli, E. P.
           (2004). Image quality assessment: From error visibility to
           structural similarity. IEEE Transactions on Image Processing,
           13, 600-612.
           https://ece.uwaterloo.ca/~z70wang/publications/ssim.pdf,
           :DOI:`10.1109/TIP.2003.819861`
    """
    assert len(x.shape) == 4, f'Input images must be 4D tensors, got images of shape {x.shape}.'
    assert x.type() == y.type(), f'Input images must have the same dtype, got {x.type()} and {y.type()}.'
    assert x.shape == y.shape, f'Input images must have the same dimensions, got {x.shape} and {y.shape}.'
    assert win_size % 2 == 1, f'Window size must be odd, got {win_size}.'

    win = __fspecial_gauss_1d(win_size, win_sigma)
    win = win.repeat(x.shape[1], 1, 1, 1)

    ssim_val, cs = __compute_ssim(x=x,
                                  y=y,
                                  win=win,
                                  data_range=data_range,
                                  size_average=False,
                                  full=True,
                                  k1=k1,
                                  k2=k2)
    if size_average:
        ssim_val = ssim_val.mean()
        cs = cs.mean()

    if full:
        return ssim_val, cs

    return ssim_val


def __fspecial_gauss_1d(size: int, sigma: float) -> torch.Tensor:
    """ Creates a 1-D gauss kernel.

    Args:
        size: The size of gauss kernel.
        sigma: Sigma of normal distribution.

    Returns:
        A 1D kernel.
    """
    coords = torch.arange(size).to(dtype=torch.float)
    coords -= size//2

    g = torch.exp(-(coords**2) / (2*sigma**2))
    g /= g.sum()

    return g.unsqueeze(0).unsqueeze(0)


def __compute_ssim(x: torch.Tensor, y: torch.Tensor, win: torch.Tensor, data_range: Union[float, int] = 255,
                   size_average: bool = True, full: bool = False, k1: float = 0.01, k2: float = 0.03) -> torch.Tensor:
    """Calculate Structural Similarity (SSIM) index for X and Y.

    Args:
        x: Batch of images, (N,C,H,W).
        y: Batch of images, (N,C,H,W).
        win: 1-D gauss kernel.
        data_range: Value range of input images (usually 1.0 or 255).
        size_average: If size_average=True, ssim of all images will be averaged as a scalar.
        full: Return sc or not.
        k1: Algorithm parameter, K1 (small constant, see [1]).
        k2: Algorithm parameter, K2 (small constant, see [1]).
            Try a larger K2 constant (e.g. 0.4) if you get a negative or NaN results.

    Returns:
        Value of Structural Similarity (SSIM) index.
    """
    c1 = (k1 * data_range)**2
    c2 = (k2 * data_range)**2

    win = win.to(x.device, dtype=x.dtype)

    mu1 = __gaussian_filter(x, win)
    mu2 = __gaussian_filter(y, win)

    mu1_sq = mu1.pow(2)
    mu2_sq = mu2.pow(2)
    mu1_mu2 = mu1 * mu2

    compensation = 1.0
    sigma1_sq = compensation * (__gaussian_filter(x * x, win) - mu1_sq)
    sigma2_sq = compensation * (__gaussian_filter(y * y, win) - mu2_sq)
    sigma12   = compensation * (__gaussian_filter(x * y, win) - mu1_mu2)

    # Set alpha = beta = gamma = 1.
    cs_map = (2 * sigma12 + c2) / (sigma1_sq + sigma2_sq + c2)
    ssim_map = ((2 * mu1_mu2 + c1) / (mu1_sq + mu2_sq + c1)) * cs_map

    if size_average:
        ssim_val = ssim_map.mean()
        cs = cs_map.mean()
    else:
        # Reduce along CHW.
        ssim_val = ssim_map.mean(-1).mean(-1).mean(-1)
        cs = cs_map.mean(-1).mean(-1).mean(-1)

    if full:
        return ssim_val, cs

    return ssim_val


def __gaussian_filter(to_blur: torch.Tensor, window: torch.Tensor) -> torch.Tensor:
    """ Blur input with 1-D kernel.

    Args:
        to_blur: A batch of tensors to be blured.
        window: 1-D gauss kernel.

    Returns:
        A batch of blurred tensors.
    """
    _, n_channels, _, _ = to_blur.shape
    out = F.conv2d(to_blur, window, stride=1, padding=0, groups=n_channels)
    out = F.conv2d(out, window.transpose(2, 3), stride=1, padding=0, groups=n_channels)
    return out