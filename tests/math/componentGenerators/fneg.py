from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.architecture.componentGenerator import ComponentGenerator
from tests.math.componentGenerators.fpshl import ComponentGeneratorFP_SHL


class ComponentGeneratorFNEG(ComponentGenerator):
    HWT_OPERATOR = HwtOps.MINUS_UNARY

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

    def _toRtlForNode_getInputDeps(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
        assert len(node.dependsOn) == 1, node
        dep0, = node.dependsOn

        assert dep0 is not None, ("All inputs must be connected", node, node.dependsOn)
        _i0 = allocator.rtlAllocHlsNetNodeOutInTime(dep0, node.scheduledIn[0])
        assert isinstance(_i0, TimeIndependentRtlResourceItem), (dep0, _i0)
        return _i0

    @override
    def toRtlForNode(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
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

