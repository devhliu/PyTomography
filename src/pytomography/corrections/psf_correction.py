from __future__ import annotations
import torch
import torch.nn as nn
import numpy as np
from pytomography.utils import get_distance, compute_pad_size
from pytomography.corrections import CorrectionNet
from pytomography.metadata import ObjectMeta, ImageMeta, PSFMeta

def get_PSF_transform(
    sigma: np.array,
    kernel_size: int,
    kernel_dimensions: str ='2D',
    delta: float = 1e-9,
    device='cpu'
    ) -> torch.nn.Conv2d:
    """Creates a 2D convolutional layer that is used for PSF correction

    Args:
        sigma (array): Array of length Lx corresponding to blurring (sigma of Gaussian) as a function of distance from scanner
        kernel_size (int): Size of the kernel used in each layer. Needs to be large enough to cover most of Gaussian
        delta (float, optional): Used to prevent division by 0 when sigma=0. Defaults to 1e-9.
        device (str, optional): Pytorch device used for computation. Defaults to 'cpu'.
        kernel_dimensions (str, optional): Whether or not blurring is done independently in each transaxial slice ('1D') or
                                            if blurring is done between transaxial slices ('2D'). Defaults to '2D'.

    Returns:
        torch.nn.Conv2d: Convolutional neural network layer used to apply blurring to objects of shape [batch_size, Lx, Ly, Lz]
    """
    N = len(sigma)
    layer = torch.nn.Conv2d(N, N, kernel_size, groups=N, padding='same',
                            padding_mode='replicate', bias=0, device=device)
    x_grid, y_grid = torch.meshgrid(2*[torch.arange(-int(kernel_size//2), int(kernel_size//2)+1)],
                                    indexing='ij')
    x_grid = x_grid.unsqueeze(dim=0).repeat((N,1,1))
    y_grid = y_grid.unsqueeze(dim=0).repeat((N,1,1))
    sigma = torch.tensor(sigma, dtype=torch.float32).reshape((N,1,1))
    kernel = torch.exp(-(x_grid**2 + y_grid**2) / (2*sigma**2 + delta))
    if kernel_dimensions=='1D':
        kernel[y_grid!=0] = 0
    kernel = kernel / kernel.sum(axis=(1,2)).reshape(N,1,1)
    layer.weight.data = kernel.unsqueeze(dim=1).to(device)
    return layer

class PSFCorrectionNet(CorrectionNet):
    """Correction network used to correct PSF correction in projection operators. In particular, this network is used with other correction networks to model :math:`c` in :math:`\sum_i c_{ij} a_i` (forward projection) and :math:`\sum c_{ij} b_j` (back projection). The smoothing kernel used to apply PSF modeling uses a Gaussian kernel with width :math:`\sigma` dependent on the distance of the point to the detector; that information is specified in the ``PSFMeta`` parameter. 

        Args:
            psf_meta (PSFMeta): Metadata corresponding to the parameters of PSF blurring
            device (str, optional): Pytorch device used for computation. Defaults to 'cpu'.
        """
    def __init__(
        self,
        psf_meta: PSFMeta, 
        device: str = 'cpu'
    ) -> None:
        """Initializer that sets corresponding psf parameters"""
        super(PSFCorrectionNet, self).__init__(device)
        self.psf_meta = psf_meta

    def initialize_network(
        self,
        object_meta: ObjectMeta,
        image_meta: ImageMeta
    ) -> None:
        """Function used to initalize the correction network using corresponding object and image metadata

        Args:
            object_meta (ObjectMeta): Object metadata.
            image_meta (ImageMeta): Image metadata.
        """
        super(PSFCorrectionNet, self).initialize_network(object_meta, image_meta)
        self.layers = {}
        for radius in np.unique(image_meta.radii):
            sigma = self.get_sigma(radius, object_meta.dx, object_meta.shape, self.psf_meta.collimator_slope, self.psf_meta.collimator_intercept)
            self.layers[radius] = get_PSF_transform(sigma/object_meta.dx, self.psf_meta.kernel_size, kernel_dimensions=self.psf_meta.kernel_dimensions, device=self.device)
    
    def get_sigma(
        self,
        radius: float,
        dx: float,
        shape: tuple,
        collimator_slope: float,
        collimator_intercept: float
    ) -> np.array:
        """Uses PSF Meta data information to get blurring :math:`\sigma` as a function of distance from detector. It is assumed that ``sigma=collimator_slope*d + collimator_intercept`` where :math:`d` is the distance from the detector.

        Args:
            radius (float): The distance from the detector
            dx (float): Transaxial plane pixel spacing
            shape (tuple): Tuple containing (Lx, Ly, Lz): dimensions of object space 
            collimator_slope (float): See collimator intercept
            collimator_intercept (float): Collimator slope and collimator intercept are defined such that sigma(d) = collimator_slope*d + collimator_intercept
            where sigma corresponds to sigma of a Gaussian function that characterizes blurring as a function of distance from the detector.

        Returns:
            array: An array of length Lx corresponding to blurring at each point along the 1st axis in object space
        """
        dim = shape[0] + 2*compute_pad_size(shape[0])
        distances = get_distance(dim, radius, dx)
        sigma = collimator_slope * distances + collimator_intercept
        return sigma
    @torch.no_grad()
    def forward(
		self,
		object_i: torch.Tensor,
		i: int, 
		norm_constant: torch.Tensor | None = None
	) -> torch.tensor:
        """Applies PSF correction for the situation where an object is being detector by a detector at the :math:`+x` axis.

        Args:
            object_i (torch.tensor): Tensor of size [batch_size, Lx, Ly, Lz] being projected along its first axis
			i (int): The projection index: used to find the corresponding angle in image space corresponding to object i
			norm_constant (torch.tensor, optional): A tensor used to normalize the output during back projection. Defaults to None.

        Returns:
            torch.tensor: Tensor of size [batch_size, Lx, Ly, Lz] such that projection of this tensor along the first axis corresponds to
			an PSF corrected projection.
        """
        return self.layers[self.image_meta.radii[i]](object_i)