from typing import Optional

from hwt.hdl.types.hdlType import HdlType
from hwtHls.netlist.nodes.node import HlsNetNode, OutputMinUseTimeGetter
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
        assert clkCnt > 0, clkCnt 
        self._clkCnt = clkCnt
        self._addInput(None)
        self._addOutput(dtype, None)
        
    def resolve_realization(self):
        self.assignRealization(OpRealizationMeta(0, 0, 0, self._clkCnt))

    def scheduleAlapCompaction(self, endOfLastClk: int, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]):
        return HlsNetNode.scheduleAlapCompactionMultiClock(self, endOfLastClk, outputMinUseTimeGetter)

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
