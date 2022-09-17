from typing import Union, Optional, Generator

from hwt.hdl.types.hdlType import HdlType
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict, \
    InputTimeGetter
from hwtHls.netlist.nodes.orderable import HOrderingVoidT
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    link_hls_nodes, HlsNetNodeOutLazy
from hwtHls.netlist.scheduler.clk_math import epsilon
from hwtHls.platform.opRealizationMeta import OpRealizationMeta


IO_COMB_REALIZATION = OpRealizationMeta(outputWireDelay=epsilon)


class HlsNetNodeExplicitSync(HlsNetNode):
    """
    This node represents just wire in scheduled graph which has an extra synchronization conditions.
    :see: :class:`hwtLib.handshaked.streamNode.StreamNode`

    This node is used to stall/drop/not-require some data based on external conditions.

    :ivar extraCond: an input for a flag which must be true to allow the transaction (is blocking until 1)
    :ivar skipWhen: an input for a flag which marks that this write should be skipped and transaction
                    will not be performed but the control flow will continue
    :ivar _associatedReadSync: a node which reads if this node is activated and working
    """

    def __init__(self, netlist: "HlsNetlistCtx", dtype: HdlType):
        HlsNetNode.__init__(self, netlist, name=None)
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None
        self._init_extraCond_skipWhen()
        self._addInput("dataIn")
        self._addOutput(dtype, "dataOut")
        self._addOutput(HOrderingVoidT, "orderingOut")

    def _init_extraCond_skipWhen(self):
        self.extraCond: Optional[HlsNetNodeIn] = None
        self.skipWhen: Optional[HlsNetNodeIn] = None

    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        for i in self._inputs:
            if i.in_i != 0 and i not in (self.extraCond, self.skipWhen):
                yield i

    def getOrderingOutPort(self) -> HlsNetNodeOut:
        return self._outputs[1]

    def allocateRtlInstance(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        assert type(self) is HlsNetNodeExplicitSync, self
        op_out = self._outputs[0]

        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass
        # synchronization applied in allocator additionally, we just pass the data
        v = allocator.instantiateHlsNetNodeOut(self.dependsOn[0])
        allocator.netNodeToRtl[op_out] = v
        for conrol in self.dependsOn[1:]:
            conrol.obj.allocateRtlInstance(allocator)

        return v

    def add_control_extraCond(self, en: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        i = self.extraCond
        if i is None:
            self.extraCond = i = self._addInput("extraCond")
            link_hls_nodes(en, i)
        else:
            # create "and" of existing and new extraCond and use it instead
            cur = self.dependsOn[i.in_i]
            en = self.netlist.builder.buildAnd(cur, en)
            i.replaceDriver(en)

    def add_control_skipWhen(self, skipWhen: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        i = self.skipWhen
        if i is None:
            self.skipWhen = i = self._addInput("skipWhen")
            link_hls_nodes(skipWhen, i)
        else:
            cur = self.dependsOn[i.in_i]
            skipWhen = self.netlist.builder.buildOr(cur, skipWhen)
            i.replaceDriver(skipWhen)

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def _scheduleAlapCompactionInputTimeGetter(self, i: HlsNetNodeIn, asapSchedule: SchedulizationDict):
        if i.obj is self._associatedReadSync:
            t = None
            assert len(i.obj.usedBy) == 1
            for uses in i.obj.usedBy:
                for dependentIn in uses:
                    dependentIn: HlsNetNodeIn
                    iT = dependentIn.obj.scheduleAlapCompaction(asapSchedule, None)[dependentIn.in_i]
                    if t is None:
                        t = iT
                    else:
                        t = min(t, iT)

            if t is None:
                t = asapSchedule[self][0]
            
            return t
        else:
            return i.obj.scheduleAlapCompaction(asapSchedule, None)[i.in_i]

    def scheduleAlapCompaction(self,
        asapSchedule:SchedulizationDict,
        inputTimeGetter:Optional[InputTimeGetter]):
        if inputTimeGetter is None:
            inputTimeGetter = self._scheduleAlapCompactionInputTimeGetter

        return HlsNetNode.scheduleAlapCompaction(self, asapSchedule, inputTimeGetter)

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d}"
        else:
            return (f"<{self.__class__.__name__:s} {self._id:d} in={self.dependsOn[0]}, "
                    f"extraCond={None if self.extraCond is None else self.dependsOn[self.extraCond.in_i]}, "
                    f"skipWhen={None if self.skipWhen is None else self.dependsOn[self.skipWhen.in_i]}>")

