from typing import Optional

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.llvm.llvmIr import HFloatTmpConfig, Instruction
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from pyDigitalWaveTools.vcd.writer import VcdWriter
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary
from tests.math.componentGenerators.fpshl import ComponentGeneratorFP_SHL
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import OP_FNEG


class ComponentGeneratorFNEG_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    @staticmethod
    def evalFn(x):
        return -x


class ComponentGeneratorFNEG(ComponentGeneratorFp):
    HWT_OPERATOR = HwtOps.MINUS_UNARY
    opDef = OP_FNEG

    @override
    def llvmIrInterpretDecode(self, interpret: LlvmIrInterpret, instr: Instruction) -> LlvmIrInstrFunction:
        assert instr.getType().isDoubleTy(), instr
        _v, = interpret._decodeInstArguments(instr.iterOperandValues())
        vIsConst = isinstance(_v, HConst)

        def _opcode_FNeg(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if vIsConst:
                v = _v
            else:
                v = regs[_v]

            if v._is_full_valid():
                v = -v
            else:
                v = HFloatTmp.from_py(None)

            interpret._storeInstrResult(waveLog, nowTime, regs, instr, v)

        return _opcode_FNeg

    def resolveRealizationForHlsNetlist(self, netlist: HlsNetlistCtx,
                                        cfg: HFloatTmpConfig) -> ComponentRealizationMeta:
        if cfg.isInQFormat:
            r = self.platform.get_op_realization(HwtOps.MINUS_UNARY, None, cfg.getBitWidth(), 1, netlist.realTimeClkPeriod)
        else:
            r = self.platform.get_op_realization(HwtOps.NOT, None, cfg.getBitWidth(), 1, netlist.realTimeClkPeriod)

        r = ComponentRealizationMeta.fromOpRealization(r)
        return r

    def toHwtCompatibleOperatorBeforeScheduling(self, node:HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if not cfg.isInQFormat:
            builder = HlsNetlistBuilderWithWorklist(node.getHlsNetlistBuilder(), worklist)
            res = self.hlsNetlist_buildFNeg(cfg, node, builder, node.dependsOn[0])
            debugTracer = node.netlist.dbgSubmoduleBuidTracer
            with debugTracer.scoped(self, node):
                debugTracer.log(("replacing with", res))
                replaceOperatorNodeWith(node, res, worklist)
                return True

        return False

    def hlsNetlist_buildFNeg(self, cfg: HFloatTmpConfig, nodeForDebug: HlsNetNodeOperator,
                             builder: HlsNetlistBuilderWithWorklist, op: HlsNetNodeOut):
        assert cfg.hasSign, (nodeForDebug, cfg)
        opMsb = builder.buildGetMsb(op)
        opMsb_n = builder.buildNot(opMsb)
        valueWidth = cfg.getBitWidth() - 1
        opVal = builder.buildIndexConstSlice(HBits(valueWidth), op, valueWidth, 0)
        opNeg = builder.buildConcat(opVal, opMsb_n)
        return opNeg

    @override
    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) == 1, node
        w = node.dependsOn[0]._dtype.bit_length()
        freq = node.netlist.realTimeClkPeriod
        p = self.platform
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()
            return p.get_op_realization(self.HWT_OPERATOR, None, w, 1, freq)
        else:
            raise NotImplementedError()

    def _toRtlForNode_getInputDeps(self, node: HlsNetNodeOperator, allocator: ArchElement) -> None:
        assert len(node.dependsOn) == 1, node
        dep0, = node.dependsOn

        assert dep0 is not None, ("All inputs must be connected", node, node.dependsOn)
        _i0 = allocator.rtlAllocHlsNetNodeOutInTime(dep0, node.scheduledIn[0], node)
        assert isinstance(_i0, TimeIndependentRtlResourceItem), (dep0, _i0)
        return _i0

    @override
    def toRtlForNode(self, node: HlsNetNodeOperator, allocator: ArchElement) -> None:
        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        _i0 = self._toRtlForNode_getInputDeps(node, allocator)
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()
            outSig = self.HWT_OPERATOR._evalFn(_i0.data)
        else:
            raise NotImplementedError()

        return ComponentGeneratorFP_SHL._toRtlForNode_registerOutput(node, allocator, outSig)

