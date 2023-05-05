from math import ceil
from typing import Optional, List

from hwt.hdl.types.hdlType import HdlType
from hwtHls.netlist.nodes.node import HlsNetNode, HlsNetNodePartRef
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import OutputMinUseTimeGetter
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

    def resolveRealization(self):
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

    def createSubNodeRefrenceFromPorts(self, beginTime: int, endTime: int,
                                       inputs: List[HlsNetNodeIn], outputs: List[HlsNetNodeOut]) -> "HlsNetNodePartRef":
        return HlsNetNodeDelayPartRef(self.netlist, self, beginTime // self.netlist.normalizedClkPeriod)

    def partsComplement(self, otherParts: List["HlsNetNodePartRef"]):
        """
        :see: :meth:`HlsNetNode.partsComplement`
        """
        clkPeriod = self.netlist.normalizedClkPeriod
        start = self.scheduledIn[0] // clkPeriod
        times = iter(range(start, ceil(self.scheduledOut[0] / clkPeriod) + 1))
        # walk trough the parts and generate new parts for clock indexes which are missing
        for p in sorted(otherParts, key=lambda p: p.clkI):
            try:
                t = next(times)
            except StopIteration:
                raise AssertionError(self, "otherParts contains more elements than it is required", otherParts)
            if p.clkI != t:
                assert p.clkI > t, (self, otherParts)
                for clkI in range(t, p.clkI):
                    try:
                        t = next(times)
                    except StopIteration:
                        raise AssertionError(self, "otherParts contains more elements than it is required", otherParts)
                    yield HlsNetNodeDelayPartRef(self.netlist, self, clkI)

        # generate parts from remaining times
        for t in times:
            yield HlsNetNodeDelayPartRef(self.netlist, self, clkI)


class HlsNetNodeDelayPartRef(HlsNetNodePartRef):

    def __init__(self, netlist:"HlsNetlistCtx", parentNode:HlsNetNode, clkI: int, name:str=None):
        HlsNetNodePartRef.__init__(self, netlist, parentNode, name=name)
        self.clkI = clkI

    def iterChildReads(self):
        return
        yield

    def iterChildWrites(self):
        return
        yield

    def allocateRtlInstance(self, allocator:"ArchElement"):
        try:
            return allocator.netNodeToRtl[self]
        except KeyError:
            res = allocator.netNodeToRtl[self] = []
            return res

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} for {self.parentNode._id:d} clkI={self.clkI:d}>"
