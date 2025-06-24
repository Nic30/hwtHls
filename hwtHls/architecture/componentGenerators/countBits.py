#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type

from hwt.code import Concat
from hwt.hdl.commonConstants import b0
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.mainBases import RtlSignalBase
from hwt.math import isPow2, log2ceil
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import replaceHlsNetNodeOperatorWithHwModule
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.architecture.componentGenerators.ctpop import Ctpop
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from pyMathBitPrecise.bit_utils import mask, next_power_of_2


# https://electronics.stackexchange.com/questions/196914/verilog-synthesize-high-speed-leading-zero-count
# https://content.sciendo.com/view/journals/jee/66/6/article-p329.xml?language=en
# [1]. Nebojša Z. Milenković and Vladimir V. Stanković and Miljana Lj. Milić, “MODULAR DESIGN OF FAST LEADING ZEROS COUNTING CIRCUIT”, Journal of ELECTRICAL ENGINEERING, VOL. 66, NO. 6, 2015, 329–333
# https://github.com/tomverbeure/math?tab=readme-ov-file#leading-zero-counter-lzc-and-leading-zero-anticipor-lza
@hlsBytecode
def _countLeadingRecurse(dataIn: RtlSignalBase[HBits], bitValToCount: int):
    """
    Construct a balanced tree for counter of leading 0/1

    :attention: result is not final result, it is only for 0 to width-1 values

    """
    assert bitValToCount in (0, 1), bitValToCount
    inWidth = dataIn._dtype.bit_length()
    if inWidth == 2:
        if bitValToCount == 0:
            return ~dataIn[1]
        else:
            return dataIn[1]
    else:
        assert inWidth > 2, inWidth
        assert inWidth % 2 == 0, inWidth
        lhs = dataIn[:inWidth // 2]
        rhs = dataIn[inWidth // 2:]
        if bitValToCount == 0:
            leftFull = lhs._eq(0)
        else:
            leftFull = lhs._eq(mask(lhs._dtype.bit_length()))

        in_ = lhs._dtype.from_py(None)
        if leftFull:
            in_ = rhs
        else:
            in_ = lhs

        halfCount = PyBytecodeInline(_countLeadingRecurse)(in_, bitValToCount)
        return Concat(leftFull, halfCount)


@hlsBytecode
def _countTrailingRecurse(dataIn: RtlSignalBase[HBits], bitValToCount: int):
    """
    Version of :func:`~._countLeadingRecurse` which counts from the back of the vector (upper bits first)
    """
    assert bitValToCount in (0, 1), bitValToCount
    inWidth = dataIn._dtype.bit_length()
    if inWidth == 2:
        if bitValToCount == 0:
            return ~dataIn[0]
        else:
            return dataIn[0]
    else:
        assert inWidth > 2, inWidth
        assert inWidth % 2 == 0, inWidth
        lhs = dataIn[:inWidth // 2]
        rhs = dataIn[inWidth // 2:]
        if bitValToCount == 0:
            leftFull = rhs._eq(0)
        else:
            leftFull = rhs._eq(mask(rhs._dtype.bit_length()))

        in_ = rhs._dtype.from_py(None)
        if leftFull:
            in_ = lhs
        else:
            in_ = rhs

        halfCount = PyBytecodeInline(_countTrailingRecurse)(in_, bitValToCount)
        return Concat(leftFull, halfCount)


@hlsBytecode
def countBits(dataIn: RtlSignalBase[HBits], bitValToCount: int, leading: bool):
    """
    :param bitValToCount: parameter to switch between count of zeros and ones
    :param leading: flag which switches between leading (from MSB side) and trailing (from LSB side) count
    :returns: number of bits set to bitValToCount value
    """
    inWidth = dataIn._dtype.bit_length()
    assert bitValToCount in (0, 1), bitValToCount
    assert isinstance(leading, bool), leading

    if bitValToCount == 0:
        full = dataIn._eq(0)
    else:
        full = dataIn._eq(mask(inWidth))

    countFn = _countLeadingRecurse if leading else _countTrailingRecurse
    halfCount = PyBytecodeInline(countFn)(dataIn, bitValToCount)
    dataOut = HBits(log2ceil(inWidth + 1)).from_py(None)
    if full:
        # all bits are of counted value -> return max value
        dataOut = inWidth
    else:
        dataOut = Concat(b0, halfCount)

    return dataOut


@serializeParamsUniq
class CountLeadingZeros(_BaseALU1HwModule):

    @override
    def hwDeclr(self):
        Ctpop.hwDeclr(self)

    def _trimToOutSize(self, isExactlyPow2: bool, result: RtlSignalBase) -> RtlSignalBase:
        """
        Trim result in the case that input had to be extended to work correctly with bit count algorithm
        """
        if isExactlyPow2:
            return result
        else:
            return result._trunc(self._getTypeOfIo(self.data_out).bit_length())

    @hlsBytecode
    def aluFn(self, inp: HBitsRtlSignal):
        DATA_WIDTH = self.T.bit_length()
        isExactlyPow2 = isPow2(DATA_WIDTH)
        if isExactlyPow2:
            _i = inp
        else:
            nextPow2 = next_power_of_2(DATA_WIDTH, 64)
            # add padding from LSB, 1 is neutral element
            _i = Concat(inp, HBits(nextPow2 - DATA_WIDTH).getAllOnesValue())
        res = PyBytecodeInline(countBits)(_i, 0, True)
        return self._trimToOutSize(isExactlyPow2, res)


@serializeParamsUniq
class CountTrailingZeros(CountLeadingZeros):

    @hlsBytecode
    def aluFn(self, inp: HBitsRtlSignal):
        DATA_WIDTH = self.T.bit_length()
        isExactlyPow2 = isPow2(DATA_WIDTH)
        if isExactlyPow2:
            _i = inp
        else:
            nextPow2 = next_power_of_2(DATA_WIDTH, 64)
            # add padding from MSB, 1 is neutral element
            _i = Concat(HBits(nextPow2 - DATA_WIDTH).getAllOnesValue(), inp)
        res = PyBytecodeInline(countBits)(_i, 0, False)
        return self._trimToOutSize(isExactlyPow2, res)


@serializeParamsUniq
class CountLeadingOnes(CountLeadingZeros):

    @hlsBytecode
    def aluFn(self, inp: HBitsRtlSignal):
        DATA_WIDTH = self.T.bit_length()
        isExactlyPow2 = isPow2(DATA_WIDTH)
        if isExactlyPow2:
            _i = inp
        else:
            nextPow2 = next_power_of_2(DATA_WIDTH, 64)
            # add padding from LSB, 0 is neutral element
            _i = Concat(inp, HBits(nextPow2 - DATA_WIDTH).from_py(0))
        res = PyBytecodeInline(countBits)(_i, 1, True)
        return self._trimToOutSize(isExactlyPow2, res)


@serializeParamsUniq
class CountTrailingOnes(CountLeadingZeros):

    @hlsBytecode
    def aluFn(self, inp: HBitsRtlSignal):
        DATA_WIDTH = self.T.bit_length()
        isExactlyPow2 = isPow2(DATA_WIDTH)
        if isExactlyPow2:
            _i = inp
        else:
            nextPow2 = next_power_of_2(DATA_WIDTH, 64)
            # add padding from MSB, 0 is neutral element
            _i = Concat(HBits(nextPow2 - DATA_WIDTH).from_py(0), inp)
        res = PyBytecodeInline(countBits)(_i, 1, False)
        return self._trimToOutSize(isExactlyPow2, res)


class ComponentGeneratorBitcount(ComponentGenerator):
    """
    A generator for ctpop, ctlz, cttz, ctlo, ctto and alike
    """

    def __init__(self, platform: "VirtualHlsPlatform", _operatorModuleCls: Type[CountLeadingZeros], genNamePrefix:str, moduleName:str):
        super().__init__(platform, genNamePrefix, moduleName)
        self._operatorModuleCls = _operatorModuleCls
        self.schedulingCache: dict[int, OpRealizationMeta] = {}

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, ty:HBits, realization:OpRealizationMeta):
        hwModule = self._operatorModuleCls()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) == 1, node
        return self.resolveRealizationForHlsNetlist(node.netlist, node.dependsOn[0]._dtype)

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx", T: HBits) -> None:
        cacheKey = T.bit_length()
        try:
            return self.schedulingCache[cacheKey]
        except KeyError:
            pass

        # run compilation of IntDiv HwModule to resolve scheduling properties
        hwModule = self._getConfiguredHwModule(netlist.realTimeClkPeriod, T, None)
        _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
            netlist.parentHwModule, hwModule,
            netlist.dbgSubmoduleBuidTracer, cacheKey)
        return r

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        T = node.dependsOn[0]._dtype
        realization = self.schedulingCache[T.bit_length()]
        hwModule = self._getConfiguredHwModule(freq, T, realization)
        compBuilder = self.getComponentBuilder(node)
        replaceHlsNetNodeOperatorWithHwModule(
            compBuilder, node, hwModule,
            worklist
        )
        return True

    @override
    def toRtlForNode(self, node:"HlsNetNode", allocator:"ArchElement") -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)
    # @override
    # def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
    #    assert len(node.dependsOn) == 1, node
    #    w = node.dependsOn[0]._dtype.bit_length()
    #    # layer is composed of eq+mux, nested layer works with half-width
    #    delay = 0.0
    #    freq = node.netlist.realTimeClkPeriod
    #    p = self.platform
    #    while w > 2:
    #        r = p.get_op_realization(HwtOps.EQ, None, w, 2, freq)
    #        assert r.hasOnlyInputWireDelay(), r
    #        delay += r.inputWireDelay
    #        r = p.get_op_realization(HwtOps.TERNARY, None, log2ceil(w + 1), 2, freq)
    #        assert r.hasOnlyInputWireDelay(), r
    #        delay += r.inputWireDelay
    #        w //= 2
    #
    #    r = OpRealizationMeta(inputWireDelay=delay)
    #    return r

    # @override
    # def toRtlForNode(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
    #    assert not node._isMarkedRemoved, node
    #    assert not node._isRtlAllocated, node
    #    assert len(node.dependsOn) == 1
    #    dep = node.dependsOn[0]
    #    assert dep is not None, ("All inputs must be connected", node, node.dependsOn)
    #    _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, node.scheduledIn[0])
    #    assert isinstance(_o, TimeIndependentRtlResourceItem), (dep, _o)
    #    netlist = node.netlist
    #    cb = AbstractComponentBuilder(netlist.parentHwModule, None, self._genNamePrefix)
    #
    #    m = self._operatorModuleCls()
    #    m.CLK_FREQ = int(period_to_freq(node.netlist.realTimeClkPeriod * Time.s))
    #    m.DATA_WIDTH = node.dependsOn[0]._dtype.bit_length()
    #    name = self._moduleName
    #    if node.name:
    #        name = f"{name:s}_{node.name:s}"
    #    name = cb._findSuitableName(name)
    #    setattr(cb.parent, name, m)
    #    cb._propagateClkRstn(m)
    #
    #    # connect inputs of Crc instance
    #    m.data_in(_o.data)
    #
    #    out = node._outputs[0]
    #    # register output of Crc for others to connect
    #    assert len(node._outputs) == 1
    #    res = allocator.rtlRegisterOutputRtlSignal(
    #        out, m.data_out._sig, False, False, False)
    #
    #    node._isRtlAllocated = True
    #    return res


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    import sys

    sys.setrecursionlimit(int(1e6))
    m = CountLeadingZeros()
    m.T = HBits(11)

    print(to_rtl_str(m, target_platform=Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
