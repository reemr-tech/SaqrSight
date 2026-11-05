"""Load downloaded embedding pickles without allowing arbitrary code execution.

The NewsCLIPpings embedding files are dicts of numpy arrays. Only the numpy globals needed to
rebuild arrays are permitted; any other global in the file raises an error instead of running.
"""
import pickle

import numpy as np

_ALLOWED = {
    ("numpy.core.multiarray", "_reconstruct"): np._core.multiarray._reconstruct,
    ("numpy._core.multiarray", "_reconstruct"): np._core.multiarray._reconstruct,
    ("numpy.core.multiarray", "scalar"): np._core.multiarray.scalar,
    ("numpy._core.multiarray", "scalar"): np._core.multiarray.scalar,
    ("numpy", "ndarray"): np.ndarray,
    ("numpy", "dtype"): np.dtype,
}


class _Restricted(pickle.Unpickler):
    def find_class(self, module, name):
        try:
            return _ALLOWED[(module, name)]
        except KeyError:
            raise pickle.UnpicklingError(f"blocked global {module}.{name}") from None


def load(path):
    with open(path, "rb") as f:
        return _Restricted(f).load()
