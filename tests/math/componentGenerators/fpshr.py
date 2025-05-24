from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.pyUtils.typingFuture import override
from hwtHls.code import OP_LSHR, OP_ASHR
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from tests.math.componentGenerators.fpshl import ComponentGeneratorFP_SHL


class ComponentGeneratorFP_SHR(ComponentGeneratorFP_SHL):
    INT_OP = (OP_ASHR, OP_LSHR)

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
                if cfg.hasSign:
                    outSig = (_i0.data._signed() >> sh)._vec()
                else:
                    outSig = _i0.data >> sh
            else:
                op = self.INT_OP[0] if cfg.hasSign else self.INT_OP[1]
                if op in node.netlist.platform._componentGenerators:
                    raise NotImplementedError(node)
                outSig = HOperatorNode.withRes(op, (_i0.data, _sh.data), _i0.data._dtype)

        else:
            raise NotImplementedError(node)

        return self._toRtlForNode_registerOutput(node, allocator, outSig)

