from functools import reduce
from itertools import islice
import math
from typing import Union, Optional, Sequence

from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.mainBases import RtlSignalBase
from hwt.math import log2ceil
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.hwenumerate import hwenumerate
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInline, \
    PyBytecodeBlockLabel, PyBytecodePreprocHwCopy
from hwtHls.llvm.llvmIr import HFloatTmpSaturation, HFloatTmpRounding
from tests.math.fixp.cordicAngleNormalization import anglePiRadsTo0_to_2, \
    getOctantPiRads, normalizeOctantPiradsTo0_to_0_25, ANY_FP_VALUE, \
    radsToPiRads
from tests.math.fixp.fixpResize import fixp_resize
from tests.math.fixp.fixpRtlSignal import HFixedPointQRtlSignal
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpConst import HFloatTmpConst


class CORDIC_MODE:
    ROTATION = 0
    VECTORING = 1


class CORDIC_COORDINATE_MODE:
    CIRCULAR = 1
    HYPERBOLIC = -1
    LINEAR = 0

""" 
https://eprints.soton.ac.uk/267873/1/tcas1_cordic_review.pdf
https://www.mathworks.com/help/fixedpoint/ref/cordiccexp.html

.. table:: CORDIC function configuration overview
    
    ====== =========== ========== ==========  =====  ===================== ================= ===============
     m           Mode        xin        yin    zin                xR                     yR         zR
    ====== =========== ========== ==========  =====  ===================== ================= ===============
     1(C)   rotation          1          0      θ                   cos θ             sin θ    
    -1(H)   rotation          1          0      θ                  cosh θ            sinh θ    
    -1(H)   rotation          a          a      θ                   ae**θ             ae**θ    
     1(C)   vectoring         1          a     π/2         sqrt(a**2 + 1)                          cot−1(a)
    -1(H)   vectoring         1          a      0     K*sqrt(x**2 + y**2)                          tan-1(a)
    -1(H)   vectoring         a          1      0          sqrt(a**2 − 1)                         coth−1(a)
    -1(H)   vectoring     a + 1      a − 1      0               2*sqrt(a)                           ln(a)/2
    -1(H)   vectoring   a + 1/4    a − 1/4      0                 sqrt(a)                           ln(a/4)
    -1(H)   vectoring     a + b      a - b      0              2*sqrt(ab)                         ln(a/b)/2
    -1(C)   vectoring      real       imag      0     sqrt(im**2 + re**2)                     atan2(im, re)
    ====== =========== ========== ==========  =====  ===================== ================= ===============

.. code-block:: text
   tan(z) = sin(z)/cos(z)
   tanh(z) = sinh(z)/cosh(z)
   ln(w) = 2 tanh-1(|(w-1)/(w+1)|)
   log_b(w) = K * ln(w)
   w**t = e**(t*ln(w))
   cos-1(w) = tan-1(sqrt(1-w**2)/w)
   sin-1(w) = tan-1(w/sqrt(1-w**2))
   cosh-1 = ln(w+sqrt(1-w**2))
   sinh-1 = ln(w+sqrt(1+w**2))
   sqrt(w) = sqrt((w+0.25)**2 - (w -0.25)**2)
:note: previous equations extracted from http://www.ee.ic.ac.uk/pcheung/teaching/ee3_DSD/6-sine%20generation.pdf
   
   
:note: Inverse trigonometric functions have several equivalent notations atan(x) = arctan(x) = tan-1(x) 
* https://eclipse.umbc.edu/robucci/cmpeRSD/Lectures/Lecture20__CORDIC/

:note: Square root https://ww2.mathworks.cn/help/fixedpoint/ug/compute-square-root-using-cordic.html
"""
# https://doi.org/10.4467/2353737XCT.18.059.8371  https://repozytorium.biblos.pk.edu.pl/redo/resources/28202/file/suwFiles/MorozL_CordicMethod.pdf
# x_1 = P, y_1 = 0, z_1 = phi, x_{m+1} ~= cosh(phi), y_{m+1} ~= sinh(phi), for phi in [0, 1.118]
# cosh(phi) + sinh(phi) = exp(phi)
# cosh(phi) - sinh(phi) = exp(-phi)

# table+taylor https://hdl-modules.com/modules/sine_generator/sine_generator.html
#    https://github.com/hdl-modules/hdl-modules/blob/main/modules/sine_generator/src/sine_calculator.vhd
#    https://github.com/hdl-modules/hdl-modules/blob/main/modules/sine_generator/src/sine_lookup.vhd
#    https://github.com/hdl-modules/hdl-modules/blob/main/modules/sine_generator/src/taylor_expansion_core.vhd
# https://vlsiuniverse.com/verilog-code-for-sine-cos-and-tan-cordic/
# taylor https://www.pjrc.com/high-precision-sine-wave-synthesis-using-taylor-series/
# https://github.com/alireza-shirzad/Cordic_tanh
# Trigonometrical Addition Theorems https://amycoders.org/tutorials/sintables.html
# cordic for floating point https://docs.amd.com/v/u/en-US/xapp552-cordic-floating-point-operations


class Cordic():
    """
    COordinate Rotation DIgital Computer
    is a simple and efficient algorithm to calculate trigonometric functions,
    hyperbolic functions, square roots, multiplications, divisions, and exponentials and
    logarithms with arbitrary base, typically converging with one digit (or bit) per iteration.
    
    This implementations supports LUT table for several first iteration. This implementation is often called hybrid cordic.
    Based on: FPGA-Efficient Hybrid LUT/CORDIC Architecture https://doi.org/10.1007/978-3-540-30117-2_102
    
    :note: Theta ROM is is build for angles rotated in each step.
    :note: K is a gain of cordic algorithm, it is a constant computed from number of iterations.
        It is used to normalize output values to get real output or to modify inputs to get real outputs.
    
    
    :see: https://github.com/kevinpt/vhdl-extras/blob/master/rtl/extras/cordic.vhdl
          VUTBR/FIT/INC course
          https://github.com/yyhsieh/HLS_CORDIC
          https://github.com/ZipCPU/cordic
          https://zipcpu.com/dsp/2017/08/26/quarterwave.html
          https://www.vlsiuniverse.com/verilog-code-for-sine-cos-and-tan-cordic/
          https://web.cs.ucla.edu/digital_arithmetic/files/ch11.pdf
          http://www.ee.ic.ac.uk/pcheung/teaching/ee3_DSD/6-sine%20generation.pdf
          https://github.com/kevinpt/vhdl-extras/blob/master/rtl/extras/cordic.vhdl
          https://github.com/cebarnes/cordic
          https://people.eecs.berkeley.edu/~newton/Classes/EE290sp99/lectures/ee290aSp996_1/cordic_chap24.pdf
    
    :note: there are many online cordic calculators e.g.: https://g2384.github.io/work/cordic.html
    :note: computes 1bit per iteration
    :note: CORDIC is an acronym for COordinate Rotation DIgital Computer
    :attention: For hyperbolic CORDIC-based algorithms, such as square root,
        certain iterations (i=4,13,40,121,…,k,3k+1,…) are repeated to achieve result convergence.
        J.S. Walther, "A Unified Algorithm for Elementary Functions," Conference Proceedings,
        Spring Joint Computer Conference, May 1971, pp. 379-385.
    
    :ivar ITERATION_COUNT: total number of iterations of cordic loop (including STAGES_IN_LUT), each iteration computes 1 bit of value
        so ITERATION_COUNT = precision
    :ivar STAGES_IN_LUT: number of cordic stages precomputed in LUT, the LUT holds 2**STAGES_IN_LUT items
    """

    def __init__(self, ITERATION_COUNT:int, STAGES_IN_LUT:int=0, loopPragmaGetter=lambda: None):
        assert STAGES_IN_LUT >= 0, STAGES_IN_LUT
        assert ITERATION_COUNT > 0 and STAGES_IN_LUT <= ITERATION_COUNT, (ITERATION_COUNT, STAGES_IN_LUT)
        self.ITERATION_COUNT = ITERATION_COUNT
        self.STAGES_IN_LUT = STAGES_IN_LUT
        self.loopPragmaGetter = loopPragmaGetter

    @staticmethod
    def getHyberbolicIterationCount(iterations: int):
        # j = 1
        # for i in range(1, iterations + 1):
        #    if i == 3 * j + 1:
        #        j += 1
        j = iterations - 1 // 3 + 1
        cnt = iterations + j
        return cnt

    def getThetaROM(self, mode: CORDIC_MODE, scale: float=1.) -> list[float]:
        """
        Angle table for 1s octant 0 to pi/4 rads (0-45)
        
        :param scale: for radians use 1., for pi radians use  1./math.pi
        """
        iterations = range(self.ITERATION_COUNT)
        if mode == CORDIC_COORDINATE_MODE.CIRCULAR:
            return [math.atan(2 ** (-i)) * scale for i in iterations]
        elif mode == CORDIC_COORDINATE_MODE.HYPERBOLIC:
            # In hyperbolic mode, iterations 4, 13, 40, 121, ..., j, 3j+1,...
            # must be repeated, there is a method to modify K to compensate for that
            # https://en.wikibooks.org/wiki/Digital_Circuits/CORDIC
            # https://web.cs.ucla.edu/digital_arithmetic/files/ch11.pdf p25 must begin from j=1
            lut: list[tuple[int, float]] = []
            j = 1
            for i in range(1, self.ITERATION_COUNT + 1):
                v = math.atanh(2 ** (-i)) * scale
                lut.append((i, v))
                if i == 3 * j + 1:
                    lut.append((i, v))
                    j += 1

            return lut

        elif mode == CORDIC_COORDINATE_MODE.LINEAR:
            return [(2. ** (-i)) * scale for i in iterations]
        else:
            return AssertionError("Invalid coordinateMode", mode)

    def getK(self) -> float:
        """
        Base gain of cordic
        """
        K = 1.0
        for i in range(self.ITERATION_COUNT):
            K *= 1. / math.sqrt(1. + 2. ** (-2 * i))
        return K

    def getK_forNoDivCosSin(self) -> float:
        """
        Variant of :meth:`~.getK` which computes initialization of X in a way that final division by K is not
        required and X and Y are directly holding the value of cos(a), sin(a)
        """
        # :note: K is independent of the angular units
        return reduce(lambda a, b: a * b, [math.cos(t) for t in self.getThetaROM(CORDIC_COORDINATE_MODE.CIRCULAR)], 1.0)

    @hlsBytecode
    @staticmethod
    def runCordicSteps(mode: CORDIC_MODE,
                 coordinateMode: CORDIC_COORDINATE_MODE,
                 x: ANY_FP_VALUE, y: ANY_FP_VALUE, z: ANY_FP_VALUE,
                 stepOffset: int,
                 thetaRom:Sequence[HFloatTmpConst],
                 loopPragmaGetter=lambda: None, dbgInPy=False):
        """
        Simulate CORDIC iterations from index start to stop-1.
        :param dbgInPy: turn off redundant casts if running with just pythonic values in simulation.
        """
        # for i in range(start, stop):
        #    sigma = 1. if z >= 0 else -1.
        #    factor = 2. ** (-i)
        #    x_new = x - sigma * y * factor
        #    y_new = y + sigma * x * factor
        #    z = z - sigma * thetaROM[i]
        #    x, y = x_new, y_new
        if dbgInPy:
            _f = lambda v: v
            # _range = range(start, stop)
            # _range = hwrange(start, stop)
            thetaRomIt = enumerate(thetaRom)
        else:
            _f = HFloatTmp.from_py
            indexWidth = log2ceil(stepOffset + len(thetaRom) + 1)
            thetaRomIt = hwenumerate(thetaRom)

        for _i, theta in thetaRomIt:
            PyBytecodeBlockLabel("cordic.mainLoop")
            # :attention: -i overflows because i is unsigned
            # :attention: 2.0 value usually does not fit to fp type because it is crodic uses (1.0,  -1.0) range
            #             but this pattern is recognized for hwtHls.fp.shr so no overflow error should appear
            if dbgInPy:
                i = _i + stepOffset
            else:
                i = _i._zext(indexWidth) + stepOffset
            
            xDivided = x / (_f(2.0) ** i)  # x * 2 ** (-i)
            yDivided = (y / (_f(2.0) ** i)) * _f(coordinateMode)  # y * 2 ** (-i)
            if mode == CORDIC_MODE.ROTATION:
                d = z < 0.0
            else:
                d = y >= 0.0
            
            if d:
                PyBytecodeBlockLabel("cordic.mainLoop.clockwise")
                # in rotation, y < 0 in vectoring -> clockwise
                x += yDivided
                y -= xDivided
                z += theta
            else:
                PyBytecodeBlockLabel("cordic.mainLoop.counterClockwise")
                # in vectoring -> counter-clockwise
                x -= yDivided
                y += xDivided
                z -= theta

            # print(float(x), float(y), float(z))
            PyBytecodeBlockLabel("cordic.mainLoop.latch")
            loopPragmaGetter()

        return x, y, z

    # @hlsBytecode
    # @staticmethod
    # def runCordicSteps(mode: CORDIC_MODE,
    #             coordinateMode: CORDIC_COORDINATE_MODE,
    #             x: ANY_FP_VALUE, y: ANY_FP_VALUE, z: ANY_FP_VALUE,
    #             thetaRomEnumeratedIterator: Generator[tuple[int, float], None, None],
    #             loopPragmaGetter=lambda: None):
    #    """
    #    Simulate CORDIC iterations from index start to stop-1.
    #    :param dbgInPy: turn off redundant casts if running with just pythonic values in simulation.
    #    """
    #    # for i in range(start, stop):
    #    #    sigma = 1. if z >= 0 else -1.
    #    #    factor = 2. ** (-i)
    #    #    x_new = x - sigma * y * factor
    #    #    y_new = y + sigma * x * factor
    #    #    z = z - sigma * thetaROM[i]
    #    #    x, y = x_new, y_new
    #
    #    # :note: for atan2 y=imaginary, x=real
    #    _f = HFloatTmp.from_py
    #    for i, theta in thetaRomEnumeratedIterator:
    #        PyBytecodeBlockLabel("cordic.mainLoop")
    #        # :attention: -i overflows because i is unsigned
    #        # :attention: 2.0 value usually does not fit to fp type because it is crodic uses (1.0,  -1.0) range
    #        #             but this pattern is recognized for hwtHls.fp.shr so no overflow error should appear
    #        xDivided = x / (_f(2.0) ** i)  # x * 2 ** (-i)
    #        yDivided = (y / (_f(2.0) ** i)) * _f(coordinateMode)  # y * 2 ** (-i)
    #        if mode == CORDIC_MODE.ROTATION:
    #            d = z < 0.0
    #        else:
    #            d = y >= 0.0
    #        if d:
    #            PyBytecodeBlockLabel("cordic.mainLoop.clockwise")
    #            # in rotation, y < 0 in vectoring -> clockwise
    #            x += yDivided
    #            y -= xDivided
    #            z += theta
    #        else:
    #            PyBytecodeBlockLabel("cordic.mainLoop.counterClockwise")
    #            # in vectoring -> counter-clockwise
    #            x -= yDivided
    #            y += xDivided
    #            z -= theta
    #
    #        # print(float(x), float(y), float(z))
    #        PyBytecodeBlockLabel("cordic.mainLoop.latch")
    #        loopPragmaGetter()
    #
    #    return x, y, z

    def build_LUT(self,
                  mode: CORDIC_MODE,
                  coordinateMode: CORDIC_COORDINATE_MODE,
                  STAGES_IN_LUT: int,
                  thetaROM: list[float],
                  K: float,
                  maxAngle=math.pi / 4.) -> list[tuple[float, float, float, float]]:
        """
        The LUT covers angles uniformly from 0 to maxAngle, (that means that on index size-1 there is value for maxAngle)
        maxAngle typically equals π/4 if lut is build for radians or 1/4 if for pi radians.
        Compute cordic output table for nominal angles.
        """
        lut = []
        LUT_size = 2 ** STAGES_IN_LUT
        angleStep = maxAngle / (LUT_size - 1)
        for i in range(LUT_size):
            # nominal_angle = (i / (LUT_size - 1)) * maxAngle
            nominal_angle = i * angleStep

            x0, y0, z0 = K, 0.0, nominal_angle
            x_lut, y_lut, z_lut = self.runCordicSteps(
                mode, coordinateMode,
                x0, y0, z0,
                0,
                islice(thetaROM, 0, STAGES_IN_LUT),
                dbgInPy=True)
            x_lut = float(x_lut)
            y_lut = float(y_lut)
            lut.append((nominal_angle, x_lut, y_lut, z_lut))

        return lut

    @hwt_expr_producer
    def _getLutIndex(self, _anglePiRad0to0_25: Union[HFixedPointQRtlSignal, float], T: Optional[HdlType]):
        STAGES_IN_LUT = self.STAGES_IN_LUT
        # Map the input angle (in pi-units) to a LUT index.
        # Since the LUT covers [0, 0.25], we use:
        # LUT_size = 2 ** STAGES_IN_LUT
        # select STAGES_IN_LUT bits starting from bit -2 (bit representing 0.25) downto least significant bits
        # if T is None:
        #     index = int(round((_anglePiRad0to0_25 / 0.25) * (LUT_size - 1)))
        #     # (x * (size - 1) + (size / 2)) >> STAGES_IN_LUT;
        #     # index = max(0, min(index, LUT_size - 1)) # not required as the anglePiRad is already in range 0-0.25
        # else:
        # convert to fixedpoint to select bits for digits 0.25 and lower STAGES_IN_LUT bits
        index_t = HFixedPointQ(1, 2 + self.STAGES_IN_LUT + 1)
        indexBits = (_anglePiRad0to0_25._auto_cast(T)
                     if T is not None else
                     _anglePiRad0to0_25)\
            ._auto_cast(index_t)\
            ._reinterpret_cast(HBits(index_t.bit_length()))
        # from range [0, size] to range [0, size-1]
        #
        # round((x / size) * (size - 1))
        # # assume size is power of 2
        # # div to shift
        # scale = log2(size)
        # round((x >> scale) * (size - 1))
        #
        # *0b10000 vs
        # *0b01111
        # x*(size-1) = (x<<log2(size)) - x
        # round((x >> scale) * ((1<<scale) - 1))
        # round((x >> scale) * (1<<scale) - 1 * (x >> scale)))
        # round(x - (x >> scale))

        # extract x from index bits + 1 bit for rounding
        indexLutBits = indexBits[index_t.bit_length() - 2:]  # discard bits for 1, 0.5
        # x - (x >> scale)
        index = (indexLutBits - (indexLutBits >> STAGES_IN_LUT))
        # round(x - (x >> scale))
        indexRounded = fixp_resize(index,
                             HFixedPointQ(1 + STAGES_IN_LUT, 1),
                             HFixedPointQ(STAGES_IN_LUT, 0),
                             roundingOverride=HFloatTmpRounding.ROUND_HALF_EVEN,
                             saturationOverride=HFloatTmpSaturation.SATURATE_NONE)
        if isinstance(indexRounded, HConst):
            LUT_size = 2 ** STAGES_IN_LUT
            indexRef = int(round((_anglePiRad0to0_25 / 0.25) * (LUT_size - 1)))
            # [todo] the difference is because division part is rounded differently
            #        now it is not clear if reference or previous code is more precise
            assert abs(int(indexRounded) - indexRef) <= 1, (indexRounded, indexRef)
        return indexRounded

    @staticmethod
    def _getInternalType(T: HFixedPointQ):
        """
        Cordic must internally use wider to achieve full accuracy:
        https://upload.wikimedia.org/wikiversity/en/0/0d/CORDIC.VHDL.1.A.20111110.pdf
        log n + 2 extra bits n bit accuracy after n iterations
        4 bit accuracy after 4 iterations 4 + log2(4) + 2 = 8bit datapath
        8 bit accuracy after 8 iterations 8 + log2(8) + 2 = 13 
        16 bit accuracy after 16 iterations 16 + log2(16) + 2 = 22
        https://eclipse.umbc.edu/robucci/cmpeRSD/Lectures/Lecture20__CORDIC/
        https://people.ece.cornell.edu/land/courses/ece4760/Math/FixedPointTrigonometry.pdf
        """
        return HFixedPointQ(2, T.frac_bit_length + log2ceil(T.frac_bit_length) + 2,
                            signed=True,
                            rounding=HFloatTmpRounding.ROUND_FLOOR,
                            saturation=HFloatTmpSaturation.SATURATE_NONE)

    @hlsBytecode
    @classmethod
    def _normalizeAnglePiRads0to0_25(cls, anglePiRadAnyRange: ANY_FP_VALUE):
        # :var T_INTERNAL:  type for internal computation, (T_INTERNAL is larger than io type)
        if isinstance(anglePiRadAnyRange, float):
            T = None
            T_INTERNAL = None
            anglePiRad0to2 = float(anglePiRadsTo0_to_2(anglePiRadAnyRange))
        else:
            T = anglePiRadAnyRange._dtype
            T_INTERNAL = cls._getInternalType(T)
            _anglePiRad0to2Tmp = PyBytecodeInline(anglePiRadsTo0_to_2)(anglePiRadAnyRange)

            # needs range reduction
            _anglePiRad0to2 = _anglePiRad0to2Tmp\
                ._auto_cast(T)\
                ._auto_cast(T._createMutated(int_bit_length=3, signed=True))

            T_OCT_NORM = _anglePiRad0to2._dtype._createMutated(int_bit_length=3, signed=True)
            T = T._createMutated(int_bit_length=2, signed=True)

            anglePiRad0to2 = _anglePiRad0to2._auto_cast(HFloatTmp)

        octant = getOctantPiRads(anglePiRad0to2 if T is None else anglePiRad0to2._auto_cast(T_OCT_NORM))
        swapXY, negateX, negateY, _anglePiRad0to0_25Tmp = PyBytecodeInline(normalizeOctantPiradsTo0_to_0_25)(
            octant, anglePiRad0to2)

        if T is None:
            _anglePiRad0to0_25 = _anglePiRad0to0_25Tmp
            assert float(_anglePiRad0to0_25) >= 0. and float(_anglePiRad0to0_25) <= 0.25, (_anglePiRad0to2, octant, _anglePiRad0to0_25)
            _anglePiRad0to0_25 = HFloatTmp.from_py(_anglePiRad0to0_25)
        else:
            assert _anglePiRad0to0_25Tmp._dtype == HFloatTmp, (_anglePiRad0to0_25Tmp._dtype, T)
            _anglePiRad0to0_25 = _anglePiRad0to0_25Tmp._auto_cast(T_OCT_NORM)._auto_cast(T_INTERNAL)._auto_cast(HFloatTmp)

        return swapXY, negateX, negateY, _anglePiRad0to0_25, T_INTERNAL

    def cosSinPi(self, anglePiRadAnyRange: ANY_FP_VALUE) -> tuple[ANY_FP_VALUE, ANY_FP_VALUE]:
        """
        same as :meth:`~.cosSin` just angle in in pi radians (2 = 360°)
        """
        mode = CORDIC_MODE.ROTATION
        coordinateMode = CORDIC_COORDINATE_MODE.CIRCULAR
        STAGES_IN_LUT = self.STAGES_IN_LUT
        swapXY, negateX, negateY, _anglePiRad0to0_25, T_INTERNAL = PyBytecodeInline(self._normalizeAnglePiRads0to0_25)(anglePiRadAnyRange)

        _thetaROM = self.getThetaROM(coordinateMode, scale=1. / math.pi)
        K = self.getK_forNoDivCosSin()
        if STAGES_IN_LUT:
            PyBytecodeBlockLabel("Cordic.cosSinPi.lutIndex")
            index = self._getLutIndex(_anglePiRad0to0_25, T_INTERNAL)
            _lut = self.build_LUT(mode, coordinateMode, STAGES_IN_LUT, _thetaROM, K, maxAngle=0.25)  # 1/4 for pi rads
            if T_INTERNAL is None:
                lut = _lut
                index = int(index)
            else:
                PyBytecodeBlockLabel("Cordic.cosSinPi.lutPrepare")
                lut = HStruct(
                    (T_INTERNAL, "nominal_angle"),
                    (T_INTERNAL, "x"),
                    (T_INTERNAL, "y"),
                    (T_INTERNAL, "z")
                )[len(_lut)].from_py(_lut)

            _nominal_angle, _x0, _y0, _z0 = lut[index]
            if T_INTERNAL is None:
                nominal_angle = _nominal_angle
                x0 = _x0
                y0 = _y0
                z0 = _z0
            else:
                PyBytecodeBlockLabel("Cordic.cosSinPi.cordicInit")
                nominal_angle = _nominal_angle._auto_cast(HFloatTmp)
                x0 = _x0._auto_cast(HFloatTmp)
                y0 = _y0._auto_cast(HFloatTmp)
                z0 = _z0._auto_cast(HFloatTmp)

            PyBytecodeBlockLabel("Cordic.cosSinPi.z0resolve")
            # The difference between the desired angle and the LUT's nominal angle
            # is added to the residual from the LUT simulation.
            z0 += _anglePiRad0to0_25 - nominal_angle

        else:
            PyBytecodeBlockLabel("Cordic.cosSinPi.noLut")
            if T_INTERNAL is None:
                _f = lambda v: v
            else:
                _f = HFloatTmp.from_py

            x0 = _f(K)
            y0 = _f(0.0)
            z0 = _anglePiRad0to0_25

        if self.ITERATION_COUNT > STAGES_IN_LUT:
            PyBytecodeBlockLabel("Cordic.cosSinPi.cordic")
            _thetaROM = _thetaROM[STAGES_IN_LUT:]  # cut off values already used in LUT stages
            if T_INTERNAL is None:
                thetaROM = _thetaROM
            else:
                thetaROM = HFloatTmp[len(_thetaROM)].from_py(_thetaROM)

            x_final, y_final, _ = PyBytecodeInline(self.runCordicSteps)(
                mode, coordinateMode,
                x0, y0, z0,
                STAGES_IN_LUT,
                thetaROM,
                loopPragmaGetter=self.loopPragmaGetter,
                dbgInPy=T_INTERNAL is None)
        else:
            x_final, y_final = x0, y0

        if swapXY:
            PyBytecodeBlockLabel("Cordic.cosSinPi.swapXY")
            if T_INTERNAL is None:
                copy = lambda x:x
            else:
                # the copy is necessary because otherwise both will be y_final because we are working with references
                copy = PyBytecodePreprocHwCopy

            x_final, y_final = copy(y_final), copy(x_final)

        if negateX:
            x_final = -x_final

        if negateY:
            y_final = -y_final

        PyBytecodeBlockLabel("Cordic.cosSinPi.finalization")
        if T_INTERNAL is None:
            return x_final, y_final
        else:
            # cast from HFloatTmp to concrete fp type
            outT = T_INTERNAL._createMutated(rounding=HFloatTmpRounding.ROUND_HALF_EVEN)
            T_OUT = anglePiRadAnyRange._dtype
            return (
                x_final._auto_cast(T_INTERNAL)._auto_cast(outT)._auto_cast(T_OUT),
                y_final._auto_cast(T_INTERNAL)._auto_cast(outT)._auto_cast(T_OUT)
            )

    def cosSin(self, angleRad: ANY_FP_VALUE) -> tuple[ANY_FP_VALUE, ANY_FP_VALUE]:
        """
        Compute (cos(angle), sin(angle)) using a hybrid LUT/CORDIC approach.

        :param angle: input angle in radians (2pi = 360°)
        
        :returns: tuple (cos(angle), sin(angle))
        """

        STAGES_IN_LUT = self.STAGES_IN_LUT
        if STAGES_IN_LUT or (\
             not isinstance(angleRad, RtlSignalBase) and\
             not isinstance(angleRad._dtype, HFixedPointQ) and\
             angleRad._dtype.int_bit_length <= 1):
            # if is not Q1.x the input may be out of range of cordic
            # rather than native range reduction to 1 to pi/4 radians it is more easy to convert it to pi*radians
            # and perform reduction there

            # divide by pi at the input because we would have to do this anyway to resolve index to LUT
            # or to normalize input to correct octants
            anglePiRadAnyRange = radsToPiRads(angleRad)
            return PyBytecodeInline(self.cosSinPi)(anglePiRadAnyRange)

        else:
            # only normalized Q1.x
            mode = CORDIC_MODE.ROTATION
            coordinateMode = CORDIC_COORDINATE_MODE.CIRCULAR
            # build table for pi rads in order to avoid division by pi at input
            _thetaROM = self.getThetaROM(coordinateMode)
            if isinstance(angleRad, float):
                T = None
                _f = lambda v: v
                thetaROM = _thetaROM
                _angleRad = angleRad
            else:
                T = angleRad._dtype
                T_INTERNAL = self._getInternalType(T)
                _angleRad = angleRad._auto_cast(T_INTERNAL)
                _f = HFloatTmp.from_py
                thetaROM = HFloatTmp[len(_thetaROM)].from_py(_thetaROM)

            assert len(thetaROM) == self.ITERATION_COUNT
            # Compute overall gain K.
            K = self.getK_forNoDivCosSin()
            x0 = _f(K)
            y0 = _f(0.0)
            z0 = _angleRad
            x_final, y_final, _ = PyBytecodeInline(self.runCordicSteps)(
                mode, coordinateMode,
                x0, y0, z0,
                0,
                thetaROM,  # 0, self.ITERATION_COUNT
                loopPragmaGetter=self.loopPragmaGetter)

            if T is None:
                return x_final, y_final
            else:
                # cast from HFloatTmp to concrete fp type
                outT = T_INTERNAL._createMutated(rounding=HFloatTmpRounding.ROUND_HALF_EVEN)
                return (
                    x_final._auto_cast(T_INTERNAL)._auto_cast(outT)._auto_cast(T),
                    y_final._auto_cast(T_INTERNAL)._auto_cast(outT)._auto_cast(T)
                )
