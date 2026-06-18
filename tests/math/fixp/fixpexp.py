#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from itertools import zip_longest
import math
from typing import Callable, Union

from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hwParam import HwParam
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from pyMathBitPrecise.bit_utils import mask
from tests.math.componentGenerators._genericHwModules import _FpAlu1HwModule
from tests.math.fixp.fixpConst import HFixedPointQConst
from tests.math.fixp.fixpRtlSignal import HFixedPointQRtlSignal
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp


# https://doi.org/10.4467/2353737XCT.18.059.8371  https://repozytorium.biblos.pk.edu.pl/redo/resources/28202/file/suwFiles/MorozL_CordicMethod.pdf
# x_1 = P, y_1 = 0, z_1 = phi, x_{m+1} ~= cosh(phi), y_{m+1} ~= sinh(phi), for phi in [0, 1.118]
# cosh(phi) + sinh(phi) = exp(phi)
# cosh(phi) - sinh(phi) = exp(-phi)
# https://stackoverflow.com/questions/53736820/fixed-point-approximation-of-2x-with-input-range-of-s5-26
# https://en.wikipedia.org/wiki/BKM_algorithm
def fixp_exp_generateTable(t: HFixedPointQ, maxTableAddrWidth: int, width: int, fn: Callable[[float], float]):
    """
    Generate lookup tables for individual bit slices of input value
    """
    maxVal = float(t.getMaxValue())
    tables = []
    for tableI in range(math.ceil(width / maxTableAddrWidth)):
        tableScale = 2 ** (tableI * maxTableAddrWidth - t.frac_bit_length)
        table = []
        assert width - tableI * maxTableAddrWidth >= 0
        tableAddrWidth = min(maxTableAddrWidth, width - tableI * maxTableAddrWidth)
        for i in range(2 ** tableAddrWidth):
            v = fn(i * tableScale)
            v = min(v, maxVal)  # v may actually be > max value because
            # the boundary from results start to always overflow does not need to be 2**x
            table.append(v)

        tables.append(table)

    return tables


class FixpExp():
    """
    An object with methods to compute arbitrary exp function e.g. exp(x) with the base e, exp2(x) with the base 2.0
    
    :note: the internal computation method uses product of partial terms. To achieve full 0.5 precission
        on representable range it is required that term min value * term max value have all bits which will
        be used in ressult correct.
    
    """

    def __init__(self, T: HFixedPointQ, maxTableAddrWidth:int,
                 EXP_FUNCTION=math.exp,
                 LOG_FUNCTION=math.log):
        self.maxTableAddrWidth = maxTableAddrWidth
        self.EXP_FUNCTION = EXP_FUNCTION
        self.LOG_FUNCTION = LOG_FUNCTION
        t = T
        isSigned = t.signed
        maxIntVal = mask(t.int_bit_length - (1 if isSigned else 0))
        maxIntBitsUntilAlwaysOverlows = math.ceil(math.log2(math.ceil(self.LOG_FUNCTION(maxIntVal))))
        assert maxIntBitsUntilAlwaysOverlows <= t.int_bit_length
        width = maxIntBitsUntilAlwaysOverlows + t.frac_bit_length
        numWidth = t.int_bit_length + t.frac_bit_length
        # tables for positive powers are limited because if power exceeds some number of bits
        # it can not fit into result and is inf
        tables = fixp_exp_generateTable(t, maxTableAddrWidth, width, self.EXP_FUNCTION)
        if isSigned:
            tablesInv = fixp_exp_generateTable(
                t,
                maxTableAddrWidth,
                numWidth,
                lambda x: math.exp(-x))
        else:
            tablesInv = []

        self.width = width
        self.numWidth = numWidth
        self.maxIntBitsUntilAlwaysOverlows = maxIntBitsUntilAlwaysOverlows
        self.tables = tables
        self.tablesInv = tablesInv

    def fixpexp_tabularized(self, x: Union[HFixedPointQConst, HFixedPointQRtlSignal]):
        """
        This function cuts bits of x to individual exponents for them there is a lookup table
        to get partial exp(x) and then all partial exp(x) are multiplied to get final value.
        There may be N tables, maximum table size is controlled by maxTableAddrWidth parameter
        
        .. code-block::text
            Product Rule     a**(x + y)            = a**x * a**y
            e.g.    exp(x) = exp(int(x) + frac(x)  = exp(int(x)) * exp(frac(x))
    
        """

        _f = HFloatTmp.from_py
        maxIntBitsUntilAlwaysOverlows = self.maxIntBitsUntilAlwaysOverlows
        maxTableAddrWidth = self.maxTableAddrWidth
        numWidth = self.numWidth
        width = self.width
        tables = self.tables
        tablesInv = self.tablesInv
        t: HFixedPointQ = x._dtype
        isSigned = t.signed

        isCompileTimeEvaluated = isinstance(x, HConst)
        if isCompileTimeEvaluated:
            xAsFloat = float(x)
        else:
            xAsFloat = x._explicit_cast(HFloatTmp)

        xRaw = x._reinterpret_cast(HBits(numWidth))
        res = _f(1.0)
        xNegative = xAsFloat < 0.0
        if maxIntBitsUntilAlwaysOverlows != t.int_bit_length and xAsFloat > (2. ** maxIntBitsUntilAlwaysOverlows):
            res = t.getMaxValue()._explicit_cast(HFloatTmp)
        else:
            xRawInv = -xRaw
            # query each table with bits extracted from input value and compute product of all results
            for tableI, (table, tableInv) in enumerate(zip_longest(tables, tablesInv)):
                # :note: there may be less items in "tables" because from some number the result is "inf" and
                #  the tables are not build for values pass this threshold
                if t is None or table is None:
                    assert isSigned, "There could be more tables for -x only if the x is signed"
                    v = _f(1.0)
                else:
                    highBitI = min(width, (tableI + 1) * maxTableAddrWidth)
                    lowBitI = (tableI * maxTableAddrWidth)
                    assert lowBitI < width, (width, tableI, lowBitI)
                    bitSliceForThisTable = slice(highBitI, lowBitI)
                    xBits = xRaw[bitSliceForThisTable]
                    if isCompileTimeEvaluated:
                        xBits = int(xBits)
                    else:
                        # convert table from python to hw compatible type
                        # so compiler does not work with each number separately
                        table = HFloatTmp[len(table)].from_py(table)

                    v = table[xBits]
                    del table
                    del xBits  # delete because width may differ between iterations which would raise type error

                if isSigned:
                    bitSliceForThisTable = slice(min(numWidth, (tableI + 1) * maxTableAddrWidth), (tableI * maxTableAddrWidth))
                    xInvBits = xRawInv[bitSliceForThisTable]
                    if isCompileTimeEvaluated:
                        xInvBits = int(xInvBits)
                    else:
                        tableInv = HFloatTmp[len(tableInv)].from_py(tableInv)

                    vInv = tableInv[xInvBits]
                    del tableInv

                    if xNegative:
                        res *= vInv
                    else:
                        res *= v
                    del vInv
                    del xInvBits
                else:
                    res *= v
                del v
        try:
            return res._explicit_cast(t)
        except:
            return t.getMaxValue()


@serializeParamsUniq
class FixpExpTabularizedHwModule(_FpAlu1HwModule):

    def hwConfig(self) -> None:
        _FpAlu1HwModule.hwConfig(self)
        self.T = HFixedPointQ(8, 16)
        self.MAX_TABLE_ADDR_WIDTH = HwParam(8)

    @hlsBytecode
    def aluFn(self, x):
        outT = self._getTypeOfIo(self.data_out)
        fixpexp = FixpExp(self.T, self.MAX_TABLE_ADDR_WIDTH)
        return PyBytecodeInline(fixpexp.fixpexp_tabularized)(x._reinterpret_cast(self.T))._reinterpret_cast(outT)


@serializeParamsUniq
class FixpExp2TabularizedHwModule(FixpExpTabularizedHwModule):

    @hlsBytecode
    def aluFn(self, x):
        outT = self._getTypeOfIo(self.data_out)
        fixpexp = FixpExp(self.T, self.MAX_TABLE_ADDR_WIDTH, EXP_FUNCTION=lambda x: 2.**x, LOG_FUNCTION=math.log2)
        return PyBytecodeInline(fixpexp.fixpexp_tabularized)(x._reinterpret_cast(self.T))._reinterpret_cast(outT)


@serializeParamsUniq
class FixpExp10TabularizedHwModule(FixpExpTabularizedHwModule):

    @hlsBytecode
    def aluFn(self, x):
        outT = self._getTypeOfIo(self.data_out)
        fixpexp = FixpExp(self.T, self.MAX_TABLE_ADDR_WIDTH, EXP_FUNCTION=lambda x: 10.**x, LOG_FUNCTION=math.log10)
        return PyBytecodeInline(fixpexp.fixpexp_tabularized)(x._reinterpret_cast(self.T))._reinterpret_cast(outT)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.installMathLib import installMathLibComponentGenerators

    m = FixpExpTabularizedHwModule()
    m.CLK_FREQ = int(1e6)
    platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                          llvmCliArgs=[
                              # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                              # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                          ]
                          )
    installMathLibComponentGenerators(platform)
    print(to_rtl_str(m, target_platform=platform))

