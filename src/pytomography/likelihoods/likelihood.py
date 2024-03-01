from __future__ import annotations
import pytomography
from pytomography.projectors import SystemMatrix
import torch

class Likelihood:
    def __init__(
        self,
        system_matrix: SystemMatrix,
        projections: torch.Tensor,
        additive_term: torch.Tensor = None
        ) -> None:
        """Generic likelihood class in PyTomography. Subclasses may implement specific likelihoods with methods to compute the likelihood itself as well as particular gradients of the likelihood 

        Args:
            system_matrix (SystemMatrix): The system matrix modeling the particular system whereby the projections were obtained
            projections (torch.Tensor): Acquired data
            additive_term (torch.Tensor, optional): Additional term added after forward projection by the system matrix. This term might include things like scatter and randoms. Defaults to None.
        """
        self.system_matrix = system_matrix
        self.projections = projections
        self.FP = None # stores current state of forward projection
        if type(additive_term) is torch.Tensor:
            self.additive_term = additive_term.to(projections.device).to(pytomography.dtype)
        else:
            self.additive_term = torch.zeros(projections.shape).to(projections.device).to(pytomography.dtype)
        self.n_subsets_previous = -1
    
    def _set_n_subsets(
        self,
        n_subsets: int
        )-> None:
        """Sets the number of subsets to be used when computing the likelihood

        Args:
            n_subsets (int): Number of subsets
        """
        self.n_subsets = n_subsets
        self.system_matrix.set_n_subsets(n_subsets)
        if self.n_subsets_previous!=self.n_subsets:
            self.norm_BPs = []
            for k in range(self.n_subsets):
                self.norm_BPs.append(self.system_matrix.compute_normalization_factor(k))
        self.n_subsets_previous = n_subsets
        
    def compute_gradient(self, *args, **kwargs):
        r"""Function used to compute the gradient of the likelihood :math:`\nabla_{f} L(g|f)`

        Raises:
            NotImplementedError: Must be implemented by sub classes
        """
        raise NotImplementedError("Compute gradient not implemented for this likelihood function")
    
    def compute_gradient_ff(self, *args, **kwargs):
        r"""Function used to compute the second order gradient (with respect to the object twice) of the likelihood :math:`\nabla_{ff} L(g|f)`

        Raises:
            NotImplementedError: Must be implemented by sub classes
        """
        raise NotImplementedError("gradient_ff not implemented for this likelihood function")
    
    def compute_gradient_gf(self, *args, **kwargs):
        r"""Function used to compute the second order gradient (with respect to the object then image) of the likelihood :math:`\nabla_{gf} L(g|f)`

        Raises:
            NotImplementedError: Must be implemented by sub classes
        """
        raise NotImplementedError("gradient_gf not implemented for this likelihood function")