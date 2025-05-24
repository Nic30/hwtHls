from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator


class ComponentGeneratorMUL_HL(ComponentGenerator):
    """
    A generator for MUL_HL (multiplication which may have result wider than operands)
    :note: this default version just construct multiplication on RTL level without
        any other transformation
    """
    IS_SIGNED = False

    @override
    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        p: "VirtualHlsPlatform" = self.platform
        assert len(node.dependsOn) == 2, node
        realClkPeriod = node.netlist.realTimeClkPeriod
        return p.get_op_realization(HwtOps.MUL, None, max(d._dtype.bit_length() for d in node.dependsOn), 2,
                                    realClkPeriod)

    @override
    def toRtlForNode(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        i0, i1 = (allocator.rtlAllocHlsNetNodeOutInTime(dep, t) for dep, t in zip(node.dependsOn, node.scheduledIn))
        assert isinstance(i0, TimeIndependentRtlResourceItem), self
        assert isinstance(i1, TimeIndependentRtlResourceItem), self
        out = node._outputs[0]
        outTy = out._dtype
        signed0, width0, signed1, width1, widthRes = node.operatorSpecialization
        assert i0.data._dtype.bit_length() == width0
        assert i1.data._dtype.bit_length() == width1
        
        res = i0.data._cast_sign(signed0)._ext(outTy.bit_length()) * \
              i1.data._cast_sign(signed1)._ext(outTy.bit_length())
        res = res._extOrTrunc(widthRes)
        # register output of Crc for others to connect
        assert len(node._outputs) == 1
        res = allocator.rtlRegisterOutputRtlSignal(
            out, res, False, False, False)

        node._isRtlAllocated = True
        return res
