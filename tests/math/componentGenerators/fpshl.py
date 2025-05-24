from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.code import OP_SHL
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION


class ComponentGeneratorFP_SHL(ComponentGenerator):
    INT_OP = (OP_SHL, OP_SHL)  # signed, unsigned

    @override
    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        sh = node.dependsOn[1]
        cfg: HFloatTmpConfig = node.operatorSpecialization
        netlist = node.netlist
        if cfg.isInQFormat:
            if isinstance(sh.obj, HlsNetNodeConst):
                return EMPTY_OP_REALIZATION  # will be just concatenation
            else:
                op = self.INT_OP[0] if cfg.hasSign else self.INT_OP[1]
                return netlist.platform.get_op_realization(
                    op, None,
                    cfg.exponentOrIntWidth + cfg.mantissaOrFracWidth, 2,
                    netlist.realTimeClkPeriod)

        raise NotImplementedError(node)

    @staticmethod
    def _toRtlForNode_getInputDeps(node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
        assert len(node.dependsOn) == 2, node
        dep0, dep1 = node.dependsOn

        assert dep0 is not None, ("All inputs must be connected", node, node.dependsOn)
        assert dep1 is not None, ("All inputs must be connected", node, node.dependsOn)
        _i0 = allocator.rtlAllocHlsNetNodeOutInTime(dep0, node.scheduledIn[0])
        _i1 = allocator.rtlAllocHlsNetNodeOutInTime(dep1, node.scheduledIn[1])
        assert isinstance(_i0, TimeIndependentRtlResourceItem), (dep0, _i0)
        assert isinstance(_i1, TimeIndependentRtlResourceItem), (dep1, _i1)
        return _i0, _i1

    @staticmethod
    def _toRtlForNode_registerOutput(node: HlsNetNodeOperator, allocator: "ArchElement", outSig: RtlSignal) -> None:
        out = node._outputs[0]
        # register output for others to connect
        assert len(node._outputs) == 1
        assert out._dtype.bit_length() == outSig._dtype.bit_length(), (out, out._dtype, outSig._dtype)
        res = allocator.rtlRegisterOutputRtlSignal(
            out, outSig, False, False, False)

        node._isRtlAllocated = True
        return res

    @override
    def toRtlForNode(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        _i0, _sh = self._toRtlForNode_getInputDeps(node, allocator)
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()
            if isinstance(_sh.data, HConst):
                sh = int(_sh.data)
                outSig = _i0.data << sh
            else:
                if OP_SHL in node.netlist.platform._componentGenerators:
                    raise NotImplementedError(node)
                outSig = HOperatorNode.withRes(OP_SHL, (_i0.data, _sh.data), _i0.data._dtype)
        else:
            raise NotImplementedError(node)

        return self._toRtlForNode_registerOutput(node, allocator, outSig)

