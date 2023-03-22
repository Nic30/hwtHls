from typing import Union, Optional, Generator

from hwt.hdl.types.hdlType import HdlType
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HVoidOrdering, HVoidData, HlsNetNodeOrderable, \
    HdlType_isVoid
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    link_hls_nodes, HlsNetNodeOutLazy
from hwtHls.netlist.scheduler.clk_math import epsilon
from hwtHls.platform.opRealizationMeta import OpRealizationMeta

IO_COMB_REALIZATION = OpRealizationMeta(outputWireDelay=epsilon)


class HlsNetNodeExplicitSync(HlsNetNodeOrderable):
    """
    This node represents just wire in scheduled graph which has an extra synchronization conditions.
    :see: :class:`hwtLib.handshaked.streamNode.StreamNode`

    This node is used to stall/drop/not-require some data based on external conditions.

    :ivar extraCond: an input for a flag which must be true to allow the transaction (is blocking until 1)
    :ivar skipWhen: an input for a flag which marks that this write should be skipped and transaction
                    will not be performed but the control flow will continue
    :ivar _associatedReadSync: a node which reads if this node is activated and working
    :ivar _orderingOut: an output used for ordering connections
    :ivar _dataVoidOut: an output which is used for data connection of a void type,
        this is used to represent the ordering after data dependency was optimized out, but previously was there.
    :ivar _inputOfCluster: an input which is connected to HlsNetNodeIoCluster node in which it is an input
    :ivar _outputOfCluster: an input which is connected to HlsNetNodeIoCluster node in which it is an output
    """

    def __init__(self, netlist: "HlsNetlistCtx", dtype: HdlType, name:Optional[str]=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None
        self._initCommonPortProps()
        self._addInput("dataIn")
        self._addOutput(dtype, "dataOut")

    def _initCommonPortProps(self):
        self.extraCond: Optional[HlsNetNodeIn] = None
        self.skipWhen: Optional[HlsNetNodeIn] = None
        self._orderingOut: Optional[HlsNetNodeOut] = None
        self._dataVoidOut: Optional[HlsNetNodeOut] = None
        self._outputOfCluster: Optional[HlsNetNodeIn] = None
        self._inputOfCluster: Optional[HlsNetNodeIn] = None

    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        nonOrderingInputs = (self._inputs[0], self.extraCond, self.skipWhen, self._inputOfCluster, self._outputOfCluster)
        for i in self._inputs:
            if i not in nonOrderingInputs:
                assert HdlType_isVoid(self.dependsOn[i.in_i]._dtype), i
                yield i

    def getDataVoidOutPort(self) -> HlsNetNodeOut:
        """
        Get port which used for data dependency which is of a void type.
        """
        if self._outputs:
            o = self._outputs[0]
            if o._dtype == HVoidData:
                return o
        o = self._dataVoidOut
        if o is None:
            o = self._dataVoidOut = self._addOutput(HVoidData, "dataVoidOut")
        return o

    def getOrderingOutPort(self) -> HlsNetNodeOut:
        o = self._orderingOut
        if o is None:
            o = self._orderingOut = self._addOutput(HVoidOrdering, "orderingOut", addDefaultScheduling=True)
        return o

    def getInputOfClusterPort(self):
        i = self._inputOfCluster
        if i is None:
            i = self._inputOfCluster = self._addInput("inputOfCluster", addDefaultScheduling=True)
        return i

    def getOutputOfClusterPort(self):
        i = self._outputOfCluster
        if i is None:
            i = self._outputOfCluster = self._addInput("outputOfCluster", addDefaultScheduling=True)
        return i

    def _removeInput(self, i:int):
        iObj = self._inputs[i]
        if self.extraCond is iObj:
            self.extraCond = None
        elif self.skipWhen is iObj:
            self.skipWhen = None
        elif self._inputOfCluster is iObj:
            raise AssertionError("_inputOfCluster input port can not be removed because the cluster must be always present")
        elif self._outputOfCluster is iObj:
            raise AssertionError("_outputOfCluster input port can not be removed because the cluster must be always present")
        return HlsNetNodeOrderable._removeInput(self, i)

    def _removeOutput(self, i:int):
        oObj = self._outputs[i]
        if oObj is self._orderingOut:
            self._orderingOut = None
        elif oObj is self._dataVoidOut:
            self._dataVoidOut = None

        return HlsNetNodeOrderable._removeOutput(self, i)

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

    def addControlSerialExtraCond(self, en: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        """
        Add additional extraCond flag and if there was already some flag join them as if they were in sequence.
        """
        i = self.extraCond
        if i is None:
            self.extraCond = i = self._addInput("extraCond")
            link_hls_nodes(en, i)
        else:
            # create "and" of existing and new extraCond and use it instead
            cur = self.dependsOn[i.in_i]
            en = self.netlist.builder.buildAnd(cur, en)
            if en is not cur:
                i.replaceDriver(en)

    def addControlSerialSkipWhen(self, skipWhen: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        """
        Add additional skipWhen flag and if there was already some flag join them as if they were in sequence.
        """
        i = self.skipWhen
        if i is None:
            self.skipWhen = i = self._addInput("skipWhen")
            link_hls_nodes(skipWhen, i)
        else:
            cur = self.dependsOn[i.in_i]
            skipWhen = self.netlist.builder.buildOr(cur, skipWhen)
            if cur is not skipWhen:
                i.replaceDriver(skipWhen)

    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d}"
        else:
            dep = self.dependsOn[0]
            if self.extraCond is None:
                ec = None
            else:
                ec = self.dependsOn[self.extraCond.in_i]
            if self.skipWhen is None:
                sw = None
            else:
                sw = self.dependsOn[self.skipWhen.in_i]
            return (f"<{self.__class__.__name__:s} {self._id:d} in={'None' if dep is None else f'{dep.obj._id}:{dep.out_i}'}, "
                    f"extraCond={None if ec is None else f'{ec.obj._id}:{ec.out_i}'}, "
                    f"skipWhen={None if sw is None else f'{sw.obj._id}:{sw.out_i}'}>")

