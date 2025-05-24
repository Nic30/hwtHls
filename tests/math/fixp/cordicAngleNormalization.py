import math
from typing import Union

from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b0, b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.llvm.llvmIr import HFloatTmpSaturation, HFloatTmpRounding
from tests.math.fixp.fixpRtlSignal import HFixedPointQRtlSignal
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fp.fptypes import IEEE754Fp, IEEE754FpValue
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import frem

ANY_FP_VALUE = Union[float, HFixedPointQRtlSignal, IEEE754FpValue]

#  /*
#   * Range reduces input to between 0 and pi/2 by
#   * solving for k and r in x = k*(pi/2) + r
#   */
#  template<int W, int I, int Wo>
#  void circ_range_redux( ap_ufixed<W,I> x,
#                         ap_uint<2> &k,
#                         ap_ufixed<Wo,1> &r) {
#
#    ap_ufixed<(Wo+I),0> inv_pi2("0x0.A2F9836E4E43FC715BBF"); // 2/pi
#    ap_ufixed<Wo+1,1> pi2("1.5707963267948966192313216916397514420985846996876"); // pi/2
#    ap_ufixed<Wo+I,I> prod = x * inv_pi2;
#    ap_uint<I> kint = prod;
#
#    k = kint;
#    r = x - kint * pi2;
#  };


def sin_withNormalization0_to_0_25(x:float):
    """
    This is a reference function for hw implementations of range normalized sin/cos functions.
    Its purpose is to document normalization algorithm in easy to read form.
    """
    # Normalize the angle to the range [0, 2*pi]
    # :note: negate in cases like sin(a+pi)    = -sin(a)
    # :note: swap in cases like   sin(a+-pi/2) = +-cos(a)
    x = x % (2 * math.pi)
    assert x >= 0., x
    pi = math.pi
    octantSize = pi / 4

    def cos(x):
        assert x >= 0. and x <= octantSize, x
        return math.cos(x)

    def sin(x):
        assert x >= 0. and x <= octantSize, x
        return math.sin(x)

    def _s(res):
        assert math.fabs(res - math.sin(x)) < 0.001, ("pirads:", x / pi, "rads", x, "res:", res, "sin(x):", math.sin(x))
        return res

    # 1. there are actually only few possibilities, the number must be in range in 0 to 0.25
    #    to achieve this x - octantBegin or reflect it by octantEnd - x
    #    (when debugging, if the result is not inversion or negation it means the value should be reflected)
    # 2. The value can be only sin or cos
    # 3. Value can be negated or not
    if x < 1 * octantSize:
        # 1. quadrant [0, pi/4],        [  0, 45], [0.0 , 0.25]
        return sin(x)
    elif x < 2 * octantSize:
        # 2. quadrant [pi/4, pi/2],     [ 45, 90], [0.25, 0.5]
        return _s(cos(2 * octantSize - x))
    elif x < 3 * octantSize:
        # 3. quadrant [pi/2, 3*pi/4],   [ 90, 135], [0.5 , 0.75]
        return _s(cos(-2 * octantSize + x))
    elif x < 4 * octantSize:
        # 4. quadrant [3*pi/4, pi],     [135, 180], [0.75, 1.0]
        return _s(sin(4 * octantSize - x))
    elif x < 5 * octantSize:
        # 5. quadrant [pi, 5*pi/4],     [180, 225], [1.0 , 1.25]
        return _s(-sin(-4 * octantSize + x))
    elif x < 6 * octantSize:
        # 6. quadrant [5*pi/4, 3*pi/2], [225, 270], [1.25, 1.5]
        return _s(-cos(6 * octantSize - x))
    elif x < 7 * octantSize:
        # 7. quadrant [3*pi/2, 7*pi/4], [270, 315], [1.5 , 1.75]
        return _s(-cos(-6 * octantSize + x))
    else:
        # 8. quadrant [7*pi/4, 2*pi],   [315, 360], [1.75, 2.0]
        return _s(-sin(8 * octantSize - x))


@hlsBytecode
def anglePiRadsTo0_to_2(anglePiRads):
    PyBytecodeBlockLabel("anglePiRadsTo0_to_2")
    if isinstance(anglePiRads, float) or anglePiRads._dtype == HFloatTmp:
        origTy = None
        _anglePiRads = anglePiRads
    else:
        origTy = anglePiRads._dtype
        _anglePiRads = anglePiRads._auto_cast(HFloatTmp)

    normalized_angle = frem(_anglePiRads, 2.)
    if normalized_angle < 0.:
        normalized_angle += 2

    if origTy is None:
        return normalized_angle
    else:
        return normalized_angle._auto_cast(origTy)


@hwt_expr_producer
def radsToPiRads(angleRad):
    """
    Conversion to pi*radians is beneficial when doing range reduction
    which would otherwise require 2x multiplication.
    .. code-block::c
        int k = (int)(x * (1. / (2. * PI)));
        xNew = x - (float)k * 2. * PI;
    
    if angle is converted to pi radians the range reduction is just truncatenation of msb bits.
    """
    return angleRad * (1. / math.pi)


@hwt_expr_producer
def getOctantPiRads(anglePiRads: Union[HBitsRtlSignal, float]) -> ANY_FP_VALUE:
    """
    :param anglePiRads: positive angle in pi*radians, may
    :note: pi*radians number format is also known as Daggett angle format
    """
    if isinstance(anglePiRads, float):
        assert anglePiRads >= 0.
        anglePiRads = HFloatTmp.from_py(anglePiRads)
    else:
        assert anglePiRads._dtype != HFloatTmp, "It must not be HFloatTmp because we need to cast it to a different type, for this purpose we need original type not HFloatTmp"

    if isinstance(anglePiRads._dtype, (HFixedPointQ, IEEE754Fp)) and\
            anglePiRads._dtype.saturation != HFloatTmpSaturation.SATURATE_NONE:
        raise NotImplementedError("[todo] cast out saturation before conversion to Q")

    Q2_2 = HFixedPointQ(2, 2,
                        saturation=HFloatTmpSaturation.SATURATE_NONE,
                        rounding=HFloatTmpRounding.ROUND_FLOOR)
    return anglePiRads\
            ._auto_cast(Q2_2)\
            ._reinterpret_cast(HBits(4))[3:]


def cordic_withNormalization0_to_0_25(x:float) -> tuple[float, bool, bool, bool]:
    """
    This is a reference function for hw implementations of range normalized sin/cos functions.
    Its purpose is to document normalization algorithm in easy to read form.
    :returns: xOut, swapXY (swap sin-cos), negateX, negateY
    """
    # Normalize the angle to the range [0, 2*pi]
    # :note: negate in cases like sin(a+pi)    = -sin(a)
    # :note: swap in cases like   sin(a+-pi/2) = +-cos(a)
    x = x % 2
    assert x >= 0., x
    octantSize = 1. / 4

    # 1. there are actually only few possibilities, the number must be in range in 0 to 0.25
    #    to achieve this x - octantBegin or reflect it by octantEnd - x
    #    (when debugging, if the result is not inversion or negation it means the value should be reflected)
    # 2. The value can be only sin or cos
    # 3. Value can be negated or not
    if x < 1 * octantSize:
        # 1. quadrant [0, pi/4],        [  0, 45], [0.0 , 0.25]
        return x, False, False, False
    elif x < 2 * octantSize:
        # 2. quadrant [pi/4, pi/2],     [ 45, 90], [0.25, 0.5]
        return 2 * octantSize - x, True, False, False
    elif x < 3 * octantSize:
        # 3. quadrant [pi/2, 3*pi/4],   [ 90, 135], [0.5 , 0.75]
        return -2 * octantSize + x, True, True, False
    elif x < 4 * octantSize:
        # 4. quadrant [3*pi/4, pi],     [135, 180], [0.75, 1.0]
        return 4 * octantSize - x, False, True, False
    elif x < 5 * octantSize:
        # 5. quadrant [pi, 5*pi/4],     [180, 225], [1.0 , 1.25]
        return -4 * octantSize + x, False, True, True
    elif x < 6 * octantSize:
        # 6. quadrant [5*pi/4, 3*pi/2], [225, 270], [1.25, 1.5]
        return 6 * octantSize - x, True, True, True
    elif x < 7 * octantSize:
        # 7. quadrant [3*pi/2, 7*pi/4], [270, 315], [1.5 , 1.75]
        return -6 * octantSize + x, True, False, True
    else:
        # 8. quadrant [7*pi/4, 2*pi],   [315, 360], [1.75, 2.0]
        return 8 * octantSize - x, False, False, True


@hlsBytecode
def normalizeOctantPiradsTo0_to_0_25(octant: HBitsRtlSignal, z: ANY_FP_VALUE):
    """
    Modify the x,y,z cordic variables to compute result using angle in (-0.25,0.25) (-pi/4 to pi/4 if z was in radians)
    for input z in range (0-2) (based on sin symetries)
    
    :param octant: 3 integer bits from z (bit 0, bit -1, bit -2) (bits for 1, 0.5, 0.25)
    :note: needs at least signed Q3.x number because constants are +- 2.

    https://github.com/cebarnes/cordic/blob/master/cordic.v#L63
    https://github.com/kevinpt/vhdl-extras/blob/master/rtl/extras/cordic.vhdl#L333
    https://zipcpu.com/dsp/2017/08/30/cordic.html , https://github.com/ZipCPU/cordic/blob/master/rtl/seqcordic.v#L126
    """
    assert isinstance(z, float) or z._dtype == HFloatTmp, z._dtype
    swapXY = b0
    # :note: negate in cases like sin(a+pi)    = -sin(a)
    # :note: swap in cases like   sin(a+-pi/2) = +-cos(a)
    # :note: X stores cos(z), Y stores sin(z)
    negateX = b0
    negateY = b0
    octantSize = 0.25
    zOut = z
    if octant._eq(0b000):  #  [  0, 45], [0.0 , 0.25]
        PyBytecodeBlockLabel("normalizeOctantPiradsTo0_to_0_25.octant0")

    elif octant._eq(0b001):  # [ 45, 90], [0.25, 0.5]
        PyBytecodeBlockLabel("normalizeOctantPiradsTo0_to_0_25.octant1")
        swapXY = b1
        zOut = 2 * octantSize - z

    elif octant._eq(0b010):  # [ 90, 135], [0.5 , 0.75]
        PyBytecodeBlockLabel("normalizeOctantPiradsTo0_to_0_25.octant2")
        swapXY = b1
        negateX = b1
        zOut = -2 * octantSize + z

    elif octant._eq(0b011):  # [135, 180], [0.75, 1.0]
        PyBytecodeBlockLabel("normalizeOctantPiradsTo0_to_0_25.octant3")
        negateX = b1
        zOut = 4 * octantSize - z

    elif octant._eq(0b100):  # [180, 225], [1.0 , 1.25]
        PyBytecodeBlockLabel("normalizeOctantPiradsTo0_to_0_25.octant4")
        negateX = b1
        negateY = b1
        zOut = -4 * octantSize + z

    elif octant._eq(0b101):  # [225, 270], [1.25, 1.5]
        PyBytecodeBlockLabel("normalizeOctantPiradsTo0_to_0_25.octant5")
        negateX = b1
        negateY = b1
        swapXY = b1
        zOut = 6 * octantSize - z

    elif octant._eq(0b110):  # [270, 315], [1.5 , 1.75]
        PyBytecodeBlockLabel("normalizeOctantPiradsTo0_to_0_25.octant6")
        negateY = b1
        swapXY = b1
        zOut = -6 * octantSize + z

    elif octant._eq(0b111):  # [315, 360], [1.75, 2.0]
        PyBytecodeBlockLabel("normalizeOctantPiradsTo0_to_0_25.octant7")
        negateY = b1
        zOut = 8 * octantSize - z
    
    #if isinstance(z, float):
    #    if z == octantSize:
    #        swapXY = ~swapXY
    #else:
    #    if zOut._eq(octantSize):
    #        swapXY = ~swapXY
    #zOut = fmod(zOut, 0.25)
    return swapXY, negateX, negateY, zOut

