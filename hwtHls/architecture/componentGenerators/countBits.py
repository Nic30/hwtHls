#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type, Optional, Union

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.defs import BIT
from hwt.math import log2ceil
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import replaceHlsNetNodeOperatorWithHwModule
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.architecture.componentGenerators.ctpop import Ctpop
from hwtHls.code import OP_CTTZ, zext, OP_CTLZ, OP_CTPOP
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.llvm.llvmIr import MachineRegisterInfo, MachineInstr, Register, TargetInstrInfo
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, HlsNetNodeOut
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MirToHlsNetlistTranslatedInstrOpsT
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
    _opDef: HOperatorDef = None
    _operatorModuleCls: Type[CountLeadingZeros] = None

    def __init__(self, platform: "VirtualHlsPlatform", genNamePrefix:str, moduleName:str):
        super().__init__(platform, genNamePrefix, moduleName)
        assert self._operatorModuleCls is not None, self
        assert self._opDef is not None
        self.schedulingCache: dict[int, tuple[ComponentRealizationMeta,# seen from inside
                                              ComponentRealizationMeta # seen from outside
                                              ]] = {}
        self.llvmMirInterpretDecode = makeDecode_bitcounts(self._opDef)

    @override
    def llvmMirToHlsNetlist(self,
                        mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                        builder: "HlsNetlistBuilder",
                        mbMeta: "MachineBasicBlockMeta",
                        allBlockingLoadAck: Optional[HlsNetNodeOutAny],
                        name: Optional[str],
                        instr: MachineInstr,
                        dst: Union[Register, tuple[Register]],
                        ops: MirToHlsNetlistTranslatedInstrOpsT) -> Optional[HlsNetNodeOutAny]:
        resT = HBits(log2ceil(ops[0]._dtype.bit_length() + 1))
        assert allBlockingLoadAck is not None, instr
        # mirToNetlist._translateOperator(
        #    builder, mirToNetlist.valCache, mbMeta.block,
        #    name, self.opDef, opSpecialization, resT, dst, ops)
        mb = mbMeta.block
        opDef = self._opDef
        valCache = mirToNetlist.valCache
        assert isinstance(dst, Register), instr
        # res = builder.buildOp(opDef, opSpecialization, resT, *ops, name=name)
        # valCache.add(mb, dst, res, True)
        resT = (resT, BIT)
        ops.append(allBlockingLoadAck)
        opSpecialization = None
        res = builder.buildOpManyDst(opDef, opSpecialization, resT, *ops, name=name)
        res._inputs[1].name = "reqEn"
        for dstReg, nodeOut, outName in zip((dst, None), res._outputs, ["cnt", "reqDone"]):
            nodeOut: HlsNetNodeOut
            nodeOut.name = outName
            if dstReg is not None:
                valCache.add(mb, dstReg, nodeOut, True)
            else:
                allBlockingLoadAck = builder.buildAnd(allBlockingLoadAck, nodeOut)

        return allBlockingLoadAck

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, ty:HBits, realization:ComponentRealizationMeta):
        hwModule = self._operatorModuleCls()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) <= 2, node
        return self.resolveRealizationForHlsNetlist(node.netlist, node.dependsOn[0]._dtype)

    @override
    def resolveRealizationOfLlvmMirMachineInstr(self, MRI: MachineRegisterInfo,
                                                netlist: "HlsNetlistCtx", instr: MachineInstr) -> ComponentRealizationMeta:
        T = HBits(MRI.getType(instr.getOperand(0).getReg()).getScalarSizeInBits())
        return self.resolveRealizationForHlsNetlist(netlist, T)

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx", T: HBits) -> None:
        cacheKey = T.bit_length()
        try:
            return self.schedulingCache[cacheKey][1]
        except KeyError:
            pass

        # run compilation of IntDiv HwModule to resolve scheduling properties
        hwModule = self._getConfiguredHwModule(netlist.realTimeClkPeriod, T, None)
        _, _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
            netlist.parentHwModule, hwModule,
            netlist.dbgSubmoduleBuidTracer, cacheKey)
        return r

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        T = node.dependsOn[0]._dtype
        realizationSeenFromIn, realizationSeenFromOut = self.schedulingCache[T.bit_length()]
        hwModule = self._getConfiguredHwModule(freq, T, realizationSeenFromIn)
        compBuilder = self.getComponentBuilder(node)
        replaceHlsNetNodeOperatorWithHwModule(
            compBuilder, node, hwModule,
            worklist
        )
        if realizationSeenFromOut.fitsIntoSingleClockWindow():
            assert hwModule.getHlsOpRealizationMeta()[1].fitsIntoSingleClockWindow(), (hwModule, realizationSeenFromOut, hwModule.hlsOpRealizationMeta)
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


def makeDecode_bitcounts(opDef: HOperatorDef):

    # G_ bitcounts require zext of result to match width of src operand
    def _decodeOpcode_G_bitcounts(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        dst, _src0 = interpret._decodeInstArguments(MRI, instr, instr.operands())
        src0IsConst = isinstance(_src0, HConst)
        evalFn = opDef._evalFn
        if TargetInstrInfo.isGenericOpcode(instr.getOpcode().value):

            # resTy = HBits(log2ceil(w + 1))
            def _opcode_G_bitcounts(nowTime: int, regs: list[HConst]):
                if src0IsConst:
                    src0 = _src0
                else:
                    src0 = regs[_src0]

                if src0._dtype.signed is not None:
                    src0 = src0._cast_sign(None)

                res = evalFn(src0)
                w = res._dtype.bit_length()
                srcWidth = src0._dtype.bit_length()
                if w != srcWidth:
                    assert w < srcWidth
                    res = zext(res, srcWidth)

                regs[dst] = res

            return _opcode_G_bitcounts

        else:

            def _opcode_arithUnary(nowTime: int, regs: list[HConst]):
                if src0IsConst:
                    src0 = _src0
                else:
                    src0 = regs[_src0]
                if src0._dtype.signed is not None:
                    src0 = src0._cast_sign(None)
                res = evalFn(src0)
                regs[dst] = res

            return _opcode_arithUnary

    return _decodeOpcode_G_bitcounts


class ComponentGeneratorCTTZ(ComponentGeneratorBitcount):
    _opDef = OP_CTTZ
    _operatorModuleCls = CountTrailingZeros


class ComponentGeneratorCTLZ(ComponentGeneratorBitcount):
    _opDef = OP_CTLZ
    _operatorModuleCls = CountLeadingZeros


class ComponentGeneratorCTPOP(ComponentGeneratorBitcount):
    _opDef = OP_CTPOP
    _operatorModuleCls = Ctpop


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
