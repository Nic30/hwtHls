#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import replaceHlsNetNodeOperatorWithHwModule
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.architecture.componentGenerators.ctpop import Ctpop
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtLib.logic.countLeading import countBits


@serializeParamsUniq
class CountLeadingZeros(_BaseALU1HwModule):

    @override
    def hwDeclr(self):
        Ctpop.hwDeclr(self)

    @hlsBytecode
    def aluFn(self, inp: HBitsRtlSignal):
        return countBits(inp, 0, True)


@serializeParamsUniq
class CountTrailingZeros(CountLeadingZeros):

    @hlsBytecode
    def aluFn(self, inp: HBitsRtlSignal):
        return countBits(inp, 0, False)


@serializeParamsUniq
class CountLeadingOnes(CountLeadingZeros):

    @hlsBytecode
    def aluFn(self, inp: HBitsRtlSignal):
        return countBits(inp, 1, True)


@serializeParamsUniq
class CountTrailingOnes(CountLeadingZeros):

    @hlsBytecode
    def aluFn(self, inp: HBitsRtlSignal):
        return countBits(inp, 1, False)


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
