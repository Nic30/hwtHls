from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.scheduler.clk_math import RealTimeEpsilon
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta


class ComponentGeneratorZExt(ComponentGenerator):
    """
    A generator for ZExt
    """
    IS_SIGNED = False

    @override
    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) == 1, node
        return OpRealizationMeta(outputWireDelay=RealTimeEpsilon)

    @override
    def toRtlForNode(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        dep = node.dependsOn[0]
        assert dep is not None, ("All inputs must be connected", node, node.dependsOn)
        _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, node.scheduledIn[0])
        assert isinstance(_o, TimeIndependentRtlResourceItem), (dep, _o)
        out = node._outputs[0]
        res = dep._ext(out._dtype.bit_length(), self.IS_SIGNED)

        # register output of Crc for others to connect
        assert len(node._outputs) == 1
        res = allocator.rtlRegisterOutputRtlSignal(
            out, res, False, False, False)

        node._isRtlAllocated = True
        return res


class ComponentGeneratorSExt(ComponentGeneratorZExt):
    """
    A generator for sExt
    """
    IS_SIGNED = True
