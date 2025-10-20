from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import replaceHlsNetNodeWithExpression
from hwtHls.code import OP_ROL, OP_SHL, OP_ROR, OP_LSHR, OP_ASHR
from hwtHls.netlist.builder import HlsNetlistBuilder, \
    HlsNetlistBuilderWithWorklist
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator


class ComponentGeneratorFshl(ComponentGenerator):
    """
    A generator for fshl (funnel shift left)
    """

    def resolveRealizationOfNode(self, node: HlsNetNodeOperator, rotOp:HOperatorDef=OP_ROL, shOp:HOperatorDef=OP_SHL) -> None:
        src0, src1, _ = node.dependsOn
        isRotate = src0 == src1
        netlist = node.netlist
        platform: "VirtualHlsPlatform" = netlist.parentHwModule._target_platform
        width = src0._dtype.bit_length()
        if isRotate:
            r = platform.get_op_realization(rotOp, None, width, 2, netlist.realTimeClkPeriod)
        else:
            r = platform.get_op_realization(shOp, None, 2 * width, 3, netlist.realTimeClkPeriod)

        return r

    @staticmethod
    def _assertIsConcat(n: HlsNetNode):
        assert isinstance(n, HlsNetNodeOperator) and n.operator == HwtOps.CONCAT, n
        return True

    @staticmethod
    def _assertIsConcatAnyShiftOrIndex(n: HlsNetNode):
        assert isinstance(n, HlsNetNodeOperator) and n.operator in (HwtOps.CONCAT,
                                                                    HwtOps.INDEX,
                                                                    OP_LSHR,
                                                                    OP_ASHR,
                                                                    OP_SHL,
                                                                    OP_ROL,
                                                                    OP_ROR), n
        return True

    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist:SetList["HlsNetNode"]):
        src0, src1, sh = node.dependsOn
        builder: HlsNetlistBuilder = node.getHlsNetlistBuilder()
        builder = HlsNetlistBuilderWithWorklist(builder, worklist)
        nodeOut = node._outputs[0]
        isRotateLeft = src0 == src1
        if isRotateLeft:
            newO = builder.buildOp(OP_ROL, None, nodeOut._dtype, src0, sh, name=node.name)
            newNodeCnt = 1
        else:
            # (Concat(src0, src1) << sh)[:width]
            newConc = builder.buildConcat(src1, src0)  # lowest bits first
            newShVal = builder.buildOp(OP_SHL, None, newConc._dtype, (newConc, sh))
            width0 = src0._dtype.bit_length()
            width1 = src1._dtype.bit_length()
            _worklist = []
            newO = builder.buildIndexConstSlice(nodeOut._dtype, newShVal, width0 + width1, width1, _worklist, None, name=node.name)
            assert not _worklist
            newNodeCnt = 3

        replaceHlsNetNodeWithExpression(node, newO, newNodeCnt, self._assertIsConcatAnyShiftOrIndex, worklist)
        return True


class ComponentGeneratorFshr(ComponentGeneratorFshl):

    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        return ComponentGeneratorFshl.resolveRealizationOfNode(self, node, OP_ROR, OP_LSHR)

    def toHwtCompatibleOperatorAfterScheduling(self, node: "HlsNetNodeOperator", worklist:SetList["HlsNetNode"]):
        src0, src1, sh = node.dependsOn
        builder: HlsNetlistBuilder = node.getHlsNetlistBuilder()
        builder = HlsNetlistBuilderWithWorklist(builder, worklist)
        nodeOut = node._outputs[0]
        isRotateRight = src0 == src1
        if isRotateRight:
            newO = builder.buildOp(OP_ROR, None, nodeOut._dtype, src0, sh, name=node.name)
            newNodeCnt = 1
        else:
            # (Concat(src1, src0) >> sh)[width:]
            newConc = builder.buildConcat(src0, src1)  # lowest bits first
            newShVal = builder.buildOp(OP_LSHR, None, newConc._dtype, (newConc, sh))
            width0 = src0._dtype.bit_length()
            _worklist = []
            newO = builder.buildIndexConstSlice(nodeOut._dtype, newShVal, width0, 0, _worklist, None, name=node.name)
            assert not _worklist
            newNodeCnt = 3

        replaceHlsNetNodeWithExpression(node, newO, newNodeCnt, self._assertIsConcatAnyShiftOrIndex, worklist)
        return True
