from typing import Optional, Union

from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.types.bits import HBits
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.code import OP_SHL
from hwtHls.llvm.llvmIr import HFloatTmpConfig, MachineRegisterInfo, MachineInstr, Register
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION, \
    ComponentRealizationMeta
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MirToHlsNetlistTranslatedInstrOpsT
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.componentGenerators._llvmIrInterpretFP import  \
    ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatInt, \
    ComponentGeneratorForUnSpecializedHwtHlsFpIntrinsicBinary_FloatInt


class ComponentGeneratorFP_SHL_UNSPECIALIZED(ComponentGeneratorForUnSpecializedHwtHlsFpIntrinsicBinary_FloatInt):
    """
    Unspecialized version of ComponentGeneratorFP_SHL
    """

    @override
    @staticmethod
    def evalFn(v: float, sh:int) -> float:
        return v * (2.0 ** sh)


class ComponentGeneratorFP_SHL(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatInt):
    """
    Shift left for FP numbers (x*2**sh)
    """
    INT_OP = (OP_SHL, OP_SHL)  # signed, unsigned
    evalFn = staticmethod(ComponentGeneratorFP_SHL_UNSPECIALIZED.evalFn)

    def _getOp(self, cfg: HFloatTmpConfig) -> HOperatorNode:
        return self.INT_OP[0] if cfg.hasSign else self.INT_OP[1]

    @override
    def resolveRealizationOfLlvmMirMachineInstr(self, MRI: MachineRegisterInfo,
                                                netlist: HlsNetlistCtx, instr: MachineInstr) -> ComponentRealizationMeta:
        cfg: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, instr.getNumOperands() - HFloatTmpConfig.MEMBER_CNT - 1)
        shOp = instr.getOperand(2)
        shIsConst = shOp.isCImm()
        return self.resolveRealizationForHlsNetlist(netlist, cfg, shIsConst)

    def resolveRealizationForHlsNetlist(self, netlist: HlsNetlistCtx,
                                cfg: HFloatTmpConfig, shIsConst: bool) -> ComponentRealizationMeta:
        if cfg.isInQFormat:
            if shIsConst:
                return ComponentRealizationMeta.fromOpRealization(EMPTY_OP_REALIZATION)  # will be just concatenation
            else:
                op = self._getOp(cfg)
                return ComponentRealizationMeta.fromOpRealization(netlist.platform.get_op_realization(
                    op, None,
                    cfg.exponentOrIntWidth + cfg.mantissaOrFracWidth, 2,
                    netlist.realTimeClkPeriod))

        raise NotImplementedError(cfg)

    @override
    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        sh = node.dependsOn[1]
        cfg: HFloatTmpConfig = node.operatorSpecialization
        shIsConst = isinstance(sh.obj, HlsNetNodeConst)
        return self.resolveRealizationForHlsNetlist(node.netlist, cfg, shIsConst)

    @override
    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        return ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatInt.llvmMirInterpretDecode(
            self, interpret, MRI, instr, rhsIsSigned=False, evalFn=self.evalFn)

    @override
    def llvmMirToHlsNetlist(self,
                            mirToNetlist: HlsNetlistAnalysisPassMirToNetlist,
                            builder: HlsNetlistBuilder,
                            mbMeta: MachineBasicBlockMeta,
                            allBlockingLoadAck: Optional[HlsNetNodeOutAny],
                            name: Optional[str],
                            instr: MachineInstr,
                            dst: Union[Register, tuple[Register]],
                            ops: MirToHlsNetlistTranslatedInstrOpsT) -> Optional[HlsNetNodeOutAny]:
        # enCond = ops[0]
        cfg, ops = ComponentGeneratorFp._llvmMirExtractHFloatTmpConfigFromOps(ops, True)
        cfg: HFloatTmpConfig
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()
            op = self._getOp(cfg)
            if op in self.platform._componentGenerators:
                raise NotImplementedError(instr)
            v, sh = ops
            shMaxWidth = log2ceil(v._dtype.bit_length() + 1)
            sh = builder.buildTruncOrZExt(sh, shMaxWidth)
            res = builder.buildOp(op, None, HBits(cfg.getBitWidth()), v, sh, name=name)
            mirToNetlist.valCache.add(mbMeta.block, dst, res, True)
        else:
            raise NotImplementedError()

        return allBlockingLoadAck

    @staticmethod
    def _toRtlForNode_getInputDeps(node: HlsNetNodeOperator, allocator: ArchElement) -> None:
        assert len(node.dependsOn) == 2, node
        dep0, dep1 = node.dependsOn

        assert dep0 is not None, ("All inputs must be connected", node, node.dependsOn)
        assert dep1 is not None, ("All inputs must be connected", node, node.dependsOn)
        _i0 = allocator.rtlAllocHlsNetNodeOutInTime(dep0, node.scheduledIn[0], node)
        _i1 = allocator.rtlAllocHlsNetNodeOutInTime(dep1, node.scheduledIn[1], node)
        assert isinstance(_i0, TimeIndependentRtlResourceItem), (dep0, _i0)
        assert isinstance(_i1, TimeIndependentRtlResourceItem), (dep1, _i1)
        return _i0, _i1

    @staticmethod
    def _toRtlForNode_registerOutput(node: HlsNetNodeOperator, allocator: ArchElement, outSig: RtlSignal) -> None:
        out = node._outputs[0]
        # register output for others to connect
        assert len(node._outputs) == 1
        assert out._dtype.bit_length() == outSig._dtype.bit_length(), (out, out._dtype, outSig._dtype)
        res = allocator.rtlRegisterOutputRtlSignal(
            out, outSig, False, False, False)

        node._isRtlAllocated = True
        return res

    @override
    def toRtlForNode(self, node: HlsNetNodeOperator, allocator: ArchElement) -> None:
        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        _i0, _sh = self._toRtlForNode_getInputDeps(node, allocator)
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            op = self._getOp(cfg)
            if isinstance(_sh.data, HConst):
                sh = int(_sh.data)
                if cfg.hasSign:
                    outSig = op._evalFn(_i0.data._signed(), sh)._vec()
                else:
                    outSig = op._evalFn(_i0.data, sh)
            else:
                if op in self.platform._componentGenerators:
                    raise NotImplementedError(node)
                outSig = HOperatorNode.withRes(op, (_i0.data, _sh.data), _i0.data._dtype)

        else:
            raise NotImplementedError(node)

        return self._toRtlForNode_registerOutput(node, allocator, outSig)

