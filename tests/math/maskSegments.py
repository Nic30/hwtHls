from hwt.code import split_to_segments
from hwt.hdl.operatorDefs import HOperatorDef, HwtOps
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta


def _OP_MASK_SEGMENTS_DoesNotUseLLVMOperator(*args):
    raise NotImplementedError("This is intended for use only in HlsNetlist")


def _OP_MASK_SEGMENTS(dataIn: AnyHBitsValue, maskIn: AnyHBitsValue):
    w = dataIn._dtype.bit_length()
    segCnt = maskIn._dtype.bit_length()
    zero = HBits(w // segCnt).from_py(0)
    return [en._ternary(d, zero) for en, d in zip(maskIn, split_to_segments(segCnt, w // segCnt))]


# inputs: dataInVec, maskBitVec, output: [ inp if en else 0 for en, inp in zip(maskBitVec, dataInVec)]
OP_MASK_SEGMENTS = HOperatorDef(_OP_MASK_SEGMENTS_DoesNotUseLLVMOperator, idStr="OP_MASK_SEGMENTS")


class MaskSegmentsComponentGenerator(ComponentGenerator):
    """
    Component generator for OP_MASK_SEGMENTS
    """

    @override
    def resolveRealizationOfNode(self, node:"HlsNetNode") -> ComponentRealizationMeta:
        dataIn, maskIn = node.dependsOn
        w = dataIn._dtype.bit_length()
        bit_length = w // maskIn._dtype.bit_length()
        netlist = node.netlist
        r = netlist.platform.get_op_realization(
                        HwtOps.TERNARY, None, bit_length,
                        2, netlist.realTimeClkPeriod)
        return ComponentRealizationMeta.fromOpRealization(r)

    def toRtlForNode(self, node:"HlsNetNode", allocator:"ArchElement") -> None:
        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        operands: list[TimeIndependentRtlResourceItem] = []
        for (dep, t) in zip(node.dependsOn, node.scheduledIn):
            assert dep is not None, ("All inputs must be connected", node, node.dependsOn)
            _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, t, node)
            assert isinstance(_o, TimeIndependentRtlResourceItem), (dep, _o)
            operands.append(_o)

        dataIn, maskIn = node.dependsOn
        w = dataIn._dtype.bit_length()
        item_cnt = maskIn._dtype.bit_length()
        bit_length = w // item_cnt
        # construct input mask logic
        for i, m, o in zip(split_to_segments(operands[0].data, bit_length), operands[1].data, node._outputs):
            v = m._sext(bit_length) & i
            allocator.rtlRegisterOutputRtlSignal(o, v, False, False, False)
        node._isRtlAllocated = True
        return []
