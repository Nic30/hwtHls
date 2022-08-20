from hwt.hdl.types.hdlType import HdlType
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict
from hwtHls.platform.opRealizationMeta import OpRealizationMeta


class HlsNetNodeDelayClkTick(HlsNetNode):
    """
    This node represents just wire in scheduled graph which.
    Main purpose of this node is to explicitly mark the presence of the wire in a specific architectural element.
    Which would be complicated without the node which occupies a specific section of the wire as multiple segments of the wire
    may be passed by multiple ArchElement instances in non trivial matter.

    :ivar clkCnt: length of this delay in clock period count
    """

    def __init__(self, netlist:"HlsNetlistCtx", clkCnt: int, dtype: HdlType, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._clkCnt = clkCnt
        self._addInput(None)
        self._addOutput(dtype, None)

    def resolve_realization(self):
        return OpRealizationMeta((0,), (0,), (0,), (self._clkCnt,))

    def scheduleAlapCompaction(self, asapSchedule:SchedulizationDict):
        return HlsNetNode.scheduleAlapCompactionMultiClock(self, asapSchedule)

    def allocateRtlInstance(self, allocator:"ArchElement"):
        op_out = self._outputs[0]

        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass

        # synchronization applied in allocator additionally, we just pass the data
        v = allocator.instantiateHlsNetNodeOut(self.dependsOn[0])
        allocator.netNodeToRtl[op_out] = v

        return v
