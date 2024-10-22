from math import ceil
from typing import Optional, Callable

from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.schedulableNode import OutputMinUseTimeGetter, \
    SchedTime
from hwtHls.platform.opRealizationMeta import OpRealizationMeta


class HlsNetNodeDelayClkTick(HlsNetNode):
    """
    This node represents just wire in scheduled graph which.
    Main purpose of this node is to explicitly mark the presence of the wire in a specific architectural element.
    Which would be complicated without the node which occupies a specific section of the wire as multiple segments of the wire
    may be passed by multiple ArchElement instances in non trivial matter.

    :ivar clkCnt: length of this delay in clock period count
    """

    def __init__(self, netlist:HlsNetlistCtx,
                 dtype: HdlType,
                 clkCnt: int, 
                 normalizedOutDelay: SchedTime=0,
                 name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        assert clkCnt >= 0, clkCnt
        self._clkCnt = clkCnt
        self._outputWireDelay = normalizedOutDelay
        self._addInput(None)
        self._addOutput(dtype, None)

    @override
    def resolveRealization(self):
        self.assignRealization(OpRealizationMeta(0, 0, self._outputWireDelay, self._clkCnt))

    @override
    def scheduleAlapCompaction(self,
                               endOfLastClk: SchedTime,
                               outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                               excludeNode: Optional[Callable[[HlsNetNode], bool]]):
        return HlsNetNode.scheduleAlapCompactionMultiClock(self, endOfLastClk, outputMinUseTimeGetter, excludeNode)

    @override
    def rtlAlloc(self, allocator:"ArchElement"):
        assert not self._isRtlAllocated
        op_out = self._outputs[0]
        # synchronization applied in allocator additionally, we just pass the data
        v = allocator.rtlAllocHlsNetNodeOut(self.dependsOn[0])
        allocator.netNodeToRtl[op_out] = v
        self._isRtlAllocated = True
        return v

    @override
    def splitOnClkWindows(self):
        """
        Create a new 1 clk instance for every time occupied by this and link them together.
        The original node will be the last in chain.
        """
        clkPeriod = self.netlist.normalizedClkPeriod
        start = self.scheduledIn[0] // clkPeriod
        times = range(ceil(self.scheduledOut[0] / clkPeriod) + 1, start)
        # generate parts from remaining times
        last = None
        dtype = self._outputs[0]._dtype
        for t in times:
            raise NotImplementedError()
            yield self.__class__(self.netlist, dtype)