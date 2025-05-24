from hwt.hdl.operatorDefs import HOperatorDef
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from tests.math.componentGenerators.fadd import ComponentGeneratorFADD
from tests.math.componentGenerators.fpshl import ComponentGeneratorFP_SHL


class ComponentGeneratorFCMP(ComponentGeneratorFADD):

    def __init__(self, platform:"DefaultHlsPlatform", genNamePrefix:str, moduleName:str,
                 HWT_OPERATOR_UNSIGNED: HOperatorDef,
                 HWT_OPERATOR_SIGNED:HOperatorDef):
        ComponentGeneratorFADD.__init__(self, platform, genNamePrefix, moduleName)
        self.HWT_OPERATOR_UNSIGNED = HWT_OPERATOR_UNSIGNED
        self.HWT_OPERATOR_SIGNED = HWT_OPERATOR_SIGNED

    @override
    def toHwtCompatibleOperatorBeforeScheduling(self, node:HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
        return False

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        return False

    @override
    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) == 2, node
        w = node.dependsOn[0]._dtype.bit_length()
        realClkPeriod = node.netlist.realTimeClkPeriod
        p = self.platform
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()
            if cfg.hasSign:
                op = self.HWT_OPERATOR_SIGNED
            else:
                op = self.HWT_OPERATOR_UNSIGNED

            return p.get_op_realization(op, None, w, 2, realClkPeriod)
        else:
            raise NotImplementedError()

    @override
    def toRtlForNode(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        _i0, _i1 = ComponentGeneratorFP_SHL._toRtlForNode_getInputDeps(node, allocator)
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError(node, cfg)

            if cfg.hasSign:
                op = self.HWT_OPERATOR_SIGNED
            else:
                op = self.HWT_OPERATOR_UNSIGNED

            outSig = op._evalFn(_i0.data, _i1.data)
            width = _i0.data._dtype.bit_length()
            assert outSig._dtype.bit_length() == 1, (
                "result of FCMP must be 1b wide",
                outSig._dtype, width, node, cfg)
        else:
            # netlist = node.netlist
            raise NotImplementedError()

        return ComponentGeneratorFP_SHL._toRtlForNode_registerOutput(node, allocator, outSig)
