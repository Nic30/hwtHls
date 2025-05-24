"""
Common opengl functions and datatypes defined at the top of HFloatTmp data type.
"""
from hwt.doc_markers import hwt_expr_producer
from hwt.mainBases import RtlSignalBase
from hwt.math import hMin, hMax
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import sqrt

# https://github.com/lzw545/opengg
# https://github.com/ToNi3141/Rasterix
__f = HFloatTmp.from_py


@hwt_expr_producer
def dot(x: RtlSignalBase["HArray[HFloatTmp]"], y: RtlSignalBase["HArray[HFloatTmp]"]):
    """
    https://registry.khronos.org/OpenGL-Refpages/gl4/html/dot.xhtml
    :returns: dot products of two equally sized vectors x[0]*y[0]+x[1]*y[1]...
    """
    res = None
    for _x, _y in zip(x, y):
        if res is None:
            res = _x * _y
        else:
            res = res + _x * _y

    return res


@hwt_expr_producer
def cross(x:RtlSignalBase["HArray[HFloatTmp]"], y: RtlSignalBase["HArray[HFloatTmp]"]):
    """
    :returns: cross product of two vectors
    https://registry.khronos.org/OpenGL-Refpages/gl4/html/cross.xhtml
    """
    assert len(x) == 3, x
    assert len(y) == 3, y

    return x.__class__(
        x[1] * y[2] - y[1] * x[2],
        x[2] * y[0] - y[2] * x[0],
        x[0] * y[1] - y[0] * x[1],
    )


@hwt_expr_producer
def reflect(I: RtlSignalBase["HArray[HFloatTmp]"], N: RtlSignalBase["HArray[HFloatTmp]"]):
    """
    :param I: incident vector
    :param N: normal vector 
    :returns: reflection direction

    :attention: N should be normalized in order to achieve the desired result. 
    """
    return I - __f(2.0) * dot(N, I) * N


@hwt_expr_producer
def refract(I: RtlSignalBase["HArray[HFloatTmp]"], N: RtlSignalBase["HArray[HFloatTmp]"], eta: RtlSignalBase[HFloatTmp]):
    """
    :param I: incident vector.
    :param N: normal vector.
    :param eta: ratio of indices of refraction. 
    
    :returns: refraction vector
    https://registry.khronos.org/OpenGL-Refpages/gl4/html/refract.xhtml
    """
    k = 1.0 - eta * eta * (1.0 - dot(N, I) * dot(N, I))
    if isinstance(k, float):
        if k < 0.:
            return I.__class__(__f(0.0))
        else:
            return  eta * I - (eta * dot(N, I) + sqrt(k)) * N

    R1 = eta * I - (eta * dot(N, I) + sqrt(k)) * N
    return I.__class__(
        *((k < 0.0)._ternary(__f(0.0), r1) for r1 in R1)
    )


@hwt_expr_producer
def length(v: RtlSignalBase[HFloatTmp]):
    return sqrt(dot(v, v))


@hwt_expr_producer
def normalize(v: RtlSignalBase["HArray[HFloatTmp]"]):
    """
    https://registry.khronos.org/OpenGL-Refpages/gl4/html/normalize.xhtml
    :returns: a vector with the same direction as its parameter, v, but with length 1. 
    """
    magnitudeInv = __f(1.0) / length(v)
    return v * magnitudeInv


@hwt_expr_producer
def distance(p0: RtlSignalBase[HFloatTmp], p1: RtlSignalBase[HFloatTmp]):
    """
    https://registry.khronos.org/OpenGL-Refpages/gl4/html/distance.xhtml
    """
    return length(p0 - p1)


@hwt_expr_producer
def mix(x: RtlSignalBase[HFloatTmp], y: RtlSignalBase[HFloatTmp], a: RtlSignalBase[HFloatTmp]):
    """
    linear interpolation between x and y using a to weight between them.
    The return value is computed as x*(1-a)+y*a. 
    :param x: start of the range in which to interpolate
    :param y: end of the range in which to interpolate
    :param a: value to use to interpolate between x and y 
    """
    return x * (__f(1.0) - a) + y * a


@hwt_expr_producer
def clamp(x: RtlSignalBase[HFloatTmp],
          minVal: RtlSignalBase[HFloatTmp],
          maxVal: RtlSignalBase[HFloatTmp]):
    """
    clamp — constrain a value to lie between two further values
    clamp returns the value of x constrained to the range minVal to maxVal. The returned value is computed as min(max(x, minVal), maxVal). 
    """
    return hMin(hMax(x, minVal), maxVal)


@hwt_expr_producer
def smoothstep(edge0: RtlSignalBase[HFloatTmp],
               edge1: RtlSignalBase[HFloatTmp],
               x: RtlSignalBase[HFloatTmp]):
    """
    smoothstep — perform Hermite interpolation between two values
    https://registry.khronos.org/OpenGL-Refpages/gl4/html/smoothstep.xhtml
    
    :param edge0: Specifies the value of the lower edge of the Hermite function.
    :param edge1: Specifies the value of the upper edge of the Hermite function.
    :param x: Specifies the source value for interpolation. 
    """
    t = clamp((x - edge0) / (edge1 - edge0), __f(0.0), __f(1.0))
    return t * t * (__f(3.0) - __f(2.0) * t)
