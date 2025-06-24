#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
from typing import Union

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from tests.math.fixp.cordicHybridLut import ANY_FP_VALUE, Cordic, \
    CORDIC_COORDINATE_MODE, CORDIC_MODE
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp


class CordicAtan2(Cordic):
    """
    atan2 is a mathematical function which calculates a phase from polar coordinates
    x represents real part and y imaginary part of the vecotor,
    result of the atan2 is an agle, but register x of cordic implementation also computes
    the length of the vector.

    https://www.mathworks.com/matlabcentral/fileexchange/19316-fixed-point-atan2-using-cordic    
    * https://github.com/l3VGV/cordic_atan2/blob/master/main.c
    * alternative version with multiplication https://github.com/MartinStokroos/fastCORDIC/blob/master/src/cordic.cpp
    * alternative aprox version with div https://github.com/l3VGV/fxpt_atan2/blob/master/main.c#L49
    * alternative version with https://github.com/stefan-zobel/speedy-math/blob/master/src/main/java/math/fast/JafamaFastMath.java#L413
    
    :note: Seemingly simple variant described in following article does not work.
        An Overview of the Atan2 Cordic Implementation in Digital Hardware,
        Document: 94, www.signal-processing.net, Andreas Schwarzinger Date: November 16, 2019
        http://signal-processing.net/PDF/Doc%2051%20-%20Atan2%20Cordic%20Algorithm.pdf
    """

    def __init__(self, ITERATION_COUNT:int, STAGES_IN_LUT:int=0, loopPragmaGetter=lambda:None):
        if STAGES_IN_LUT:
            raise NotImplementedError()
        Cordic.__init__(self, ITERATION_COUNT, STAGES_IN_LUT=STAGES_IN_LUT, loopPragmaGetter=loopPragmaGetter)

    @hlsBytecode
    @staticmethod
    def getQuadrant(x: ANY_FP_VALUE, y: ANY_FP_VALUE) -> Union[HBitsRtlSignal, HBitsConst]:
        qudrantT = HBits(2)
        t = qudrantT.from_py
        quadrant = t(None)
        if (x >= 0.) & (y >= 0.):
            quadrant = t(0)
        elif (x < 0.) & (y >= 0.):
            quadrant = t(1)
        elif (x < 0.) & (y < 0.):
            quadrant = t(2)
        elif (x >= 0.) & (y < 0.):
            quadrant = t(3)
        return quadrant

    @hlsBytecode
    @staticmethod
    def mapToQuadrant0(x: ANY_FP_VALUE, y: ANY_FP_VALUE, quadrant: Union[HBitsRtlSignal, HBitsConst])\
            -> tuple[ANY_FP_VALUE, ANY_FP_VALUE]:
        xOut = x
        yOut = y
        if quadrant._eq(0):
            pass
        elif quadrant._eq(1):
            xOut = y
            yOut = -x
        elif quadrant._eq(2):
            xOut = -x
            yOut = -y
        else:
            xOut = -y
            yOut = x

        return xOut, yOut

    # def runCordicRotationAtan2(self, y: ANY_FP_VALUE, x: ANY_FP_VALUE) -> tuple[ANY_FP_VALUE, ANY_FP_VALUE]:
    #    """
    #    based on:
    #    An Overview of the Atan2 Cordic Implementation in Digital Hardware,
    #    Document: 94, www.signal-processing.net, Andreas Schwarzinger Date: November 16, 2019
    #    http://signal-processing.net/PDF/Doc%2051%20-%20Atan2%20Cordic%20Algorithm.pdf
    #     """
    #    iterations = self.ITERATION_COUNT
    #    _f = HFloatTmp.from_py
    #    total_rotation = _f(0.0)
    #    for _i in hwrange(iterations):
    #        i = _i._zext(_i._dtype.bit_length() + 2)._cast_sign(True)
    #        shift = _f(2.) ** -i
    #        x_shifted = x * shift
    #        y_shifted = y * shift
    #        x_new = HFloatTmp.from_py(None)
    #        y_new = HFloatTmp.from_py(None)
    #
    #        # yShiftedLeft = y * (HFloatTmp.from_py(2.) ** i)
    #        # print("cmp", float(yShiftedLeft), float(x))
    #        # print("cmp", int(i), float(y), float(x_shifted))
    #        # if yShiftedLeft >= x:  # check if vector is large enough for this stage
    #        if y >= x_shifted:
    #            # print("runCordicRotationAtan2", _i)
    #            x_new = x + y_shifted
    #            y_new = y - x_shifted
    #            atanDiff = math.atan(-HFloatTmp.from_py(2.) ** -i)
    #            print("atanDiff:", int(i), (float(atanDiff) / math.pi) * 180, float(atanDiff))
    #            total_rotation = -atanDiff
    #        else:
    #            x_new = x
    #            y_new = y
    #
    #        x, y = x_new, y_new
    #
    #    # x == sqrt(x**2+y**2) == length(vec2(y, x)) = math.hypot(y, x)
    #    return total_rotation

    @hlsBytecode
    @staticmethod
    def undoQadrantRemap(total_rotation: ANY_FP_VALUE,
                       quadrant: Union[HBitsRtlSignal, HBitsConst],
                       isZero: Union[bool, HBitsRtlSignal, HBitsConst]) -> ANY_FP_VALUE:
        """
        Final normalization based on quadrant and total rotation
        """
        if isZero:
            total_rotation = HFloatTmp.from_py(0.0)
        elif quadrant._eq(0):
            pass
        elif quadrant._eq(1):
            total_rotation += math.pi / 2
        elif quadrant._eq(2):
            total_rotation -= math.pi
        else:
            # quadrant == 3
            total_rotation -= math.pi / 2

        return total_rotation

    @hlsBytecode
    def atan2(self, _y: ANY_FP_VALUE, _x: ANY_FP_VALUE) -> tuple[ANY_FP_VALUE, ANY_FP_VALUE]:
        """
        atan2 function based on Cordic alogorithm
        """
        if isinstance(_y, float):
            T_INTERNAL = None
            y = _y
            x = _x
            isZero = (y == 0.) & (x == 0.)
        else:
            T_INTERNAL = _y._dtype
            y = _y._auto_cast(HFloatTmp)
            x = _x._auto_cast(HFloatTmp)
            isZero = (y._eq(0.)) & (x._eq(0.))

        inline = PyBytecodeInline
        quadrant = inline(self.getQuadrant)(x, y)
        x0, y0 = inline(self.mapToQuadrant0)(x, y, quadrant)
        z0 = HFloatTmp.from_py(0)
        _thetaROM = self.getThetaROM(CORDIC_COORDINATE_MODE.CIRCULAR)
        if T_INTERNAL is None:
            thetaROM = _thetaROM
        else:
            thetaROM = HFloatTmp[len(_thetaROM)].from_py(_thetaROM)
        # https://doi.org/10.1049/el.2017.2090
        # z0 = 0, x0 = x, y0 = y
        # di = −sign(yi )
        # x_{i+1} = x_i − d_i * y_i * 2**-i
        # y_{i+1} = y_i + d_i * x_i * 2**-i
        # z_{i+1} = z_i − d_i * atan(2**-i)
        vec_length, _, atan2Tmp = inline(self.runCordicSteps)(
            CORDIC_MODE.VECTORING,
            CORDIC_COORDINATE_MODE.CIRCULAR,
            x0, y0, z0, 0, thetaROM, loopPragmaGetter=self.loopPragmaGetter)
        atan2 = inline(self.undoQadrantRemap)(atan2Tmp, quadrant, isZero)
        return atan2, vec_length

