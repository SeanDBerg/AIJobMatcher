"""
Utility module to provide basic numpy-like functionality without requiring numpy
"""
import math
import random

class NumpyArray:
    """
    A simple class that mimics numpy arrays for our specific use case
    """
    def __init__(self, data):
        self.data = data
        self.shape = (len(data),)
        
    def __repr__(self):
        return f"NumpyArray(shape={self.shape})"
    
    def __getitem__(self, index):
        return self.data[index]

def zeros(size):
    """
    Create an array of zeros
    
    Args:
        size: Integer size of array
        
    Returns:
        NumpyArray of zeros
    """
    return NumpyArray([0.0] * size)

def random_randn(size):
    """
    Generate an array of random values from a normal distribution
    
    Args:
        size: Integer size of array
        
    Returns:
        NumpyArray of random values
    """
    # Box-Muller transform to generate normally distributed random numbers
    def box_muller():
        u1 = random.random()
        u2 = random.random()
        z0 = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        return z0
    
    return NumpyArray([box_muller() for _ in range(size)])

def mean(array, axis=0):
    """
    Calculate the mean of an array along a specified axis
    
    Args:
        array: List of arrays or NumpyArray
        axis: Axis along which to calculate mean
        
    Returns:
        NumpyArray containing the mean values
    """
    if axis == 0:
        # Calculate mean along the first axis
        # Assuming all arrays have the same length
        if not array:
            return NumpyArray([])
        
        if isinstance(array[0], NumpyArray):
            result = [0.0] * len(array[0].data)
            for arr in array:
                for i, val in enumerate(arr.data):
                    result[i] += val
            
            for i in range(len(result)):
                result[i] /= len(array)
                
            return NumpyArray(result)
        else:
            # Simple list case
            return NumpyArray([sum(array) / len(array)])
    else:
        raise ValueError(f"Unsupported axis: {axis}")

def norm(vector):
    """
    Calculate the L2 norm (Euclidean norm) of a vector
    
    Args:
        vector: NumpyArray or list
        
    Returns:
        Float representing the L2 norm
    """
    if isinstance(vector, NumpyArray):
        data = vector.data
    else:
        data = vector
        
    return math.sqrt(sum(x*x for x in data))