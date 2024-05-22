from typing import Union, Optional, Generator, Tuple

from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIOs.std import HwIORdVldSync, HwIODataRd, HwIODataVld
from hwt.hwIO import HwIO
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering, HVoidData, \
    HdlType_isVoid
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HlsNetNodeOrderable
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    link_hls_nodes, HlsNetNodeOutLazy
from hwtHls.netlist.scheduler.clk_math import epsilon
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.typingFuture import override


IO_COMB_REALIZATION = OpRealizationMeta(outputWireDelay=epsilon)


class HlsNetNodeExplicitSync(HlsNetNodeOrderable):
    """
    This node represents just wire in scheduled graph which has an extra synchronization conditions.
    :see: :class:`hwtLib.handshaked.streamNode.StreamNode`

    This node is used to stall/drop/not-require some data based on external conditions.
    
    Explicit sync flag combinations (both flags are optional)
    ---------------------------------------------|
    | extra cond | skip when | meaning for read  |
    ==============================================
    | 0          | 0         | block             |
    | 1          | 0         | accept            |
    | 0          | 1         | skip read/peek    |
    | 1          | 1         | read non blocking |
    ----------------------------------------------


    :ivar extraCond: an input for a flag which must be true to allow the transaction (is blocking until 1)
    :ivar skipWhen: an input for a flag which marks that this write should be skipped and transaction
                    will not be performed but the control flow will continue
    :ivar _associatedReadSync: A node which use only during optimization phase, it reads _validNB of this node.
    :ivar _orderingOut: an output used for ordering connections
    :ivar _dataVoidOut: an output which is used for data connection of a void type,
        this is used to represent the ordering after data dependency was optimized out, but previously was there.
    :ivar _inputOfCluster: an input which is connected to HlsNetNodeIoCluster node in which it is an input
    :ivar _outputOfCluster: an input which is connected to HlsNetNodeIoCluster node in which it is an output
    :ivar _ready: output with "ready" signal for writes this signalizes that the write was successful.
        Reading of this port requires write to be performed.
    :ivar _readyNB: same as "_ready" but reading this does not cause write from main interface.
    :ivar _valid: output with "valid" signal for reads which signalizes that the read was successful.
        Reading of this port requires read to be performed.
    :ivar _validNB: same as "_valid" but reading this does not cause read from main interface.
    :note: _valid/_ready and _validNB/_readyNB holds the same value, the NB variant can be read without triggering the operation,
        _valid/_valid requires operation to be performed and comes out as a part of the data.
    :note: _valid for read means that the read was triggered and the returned data is available.
    :note: _valid for writes is always 1 (because direction of signal is from the operation itself to read)
    :note: _ready for read is always 1 (because direction of signal is from the operation itself to write)
    :note: _ready for write means the write was performed
    :attention: Internal channels can have _rtlUseReady and _rtlUseValid set to False and still have RTL valid/ready.
        If write does not have extraCond and _rtlUseValid=False then there is no RTL valid.
        If _rtlUseValid is False and there is extraCond present (on write node) there is a valid in RTL
        but it is not driven from handshake logic but it is used to pass skipWhen/extraCond to receiver.
        Same applies to read, ready and _rtlUseReady.
    """
    _PORT_ATTR_NAMES = ["_valid", "_validNB", "_ready", "_readyNB", "extraCond", "skipWhen", "_orderingOut",
                        "_dataVoidOut", "_outputOfCluster", "_inputOfCluster"]

    def __init__(self, netlist: "HlsNetlistCtx", dtype: HdlType, name:Optional[str]=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None
        self._initCommonPortProps(None)
        self._addInput("dataIn")
        self._addOutput(dtype, "dataOut")

    def _initCommonPortProps(self, io: Optional[HwIO]):
        self._valid: Optional[HlsNetNodeOut] = None
        self._validNB: Optional[HlsNetNodeOut] = None
        self._ready: Optional[HlsNetNodeOut] = None
        self._readyNB: Optional[HlsNetNodeOut] = None

        self.extraCond: Optional[HlsNetNodeIn] = None
        self.skipWhen: Optional[HlsNetNodeIn] = None
        self._orderingOut: Optional[HlsNetNodeOut] = None
        self._dataVoidOut: Optional[HlsNetNodeOut] = None
        self._outputOfCluster: Optional[HlsNetNodeIn] = None
        self._inputOfCluster: Optional[HlsNetNodeIn] = None
        self._rtlUseReady = io is None or isinstance(io, (HwIORdVldSync, HwIODataRd))
        self._rtlUseValid = io is None or isinstance(io, (HwIORdVldSync, HwIODataVld))

    @override
    def clone(self, memo:dict, keepTopPortsConnected: bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNodeOrderable.clone(self, memo, keepTopPortsConnected)
        if isNew:
            for attrName in self._PORT_ATTR_NAMES:
                a = getattr(self, attrName)
                if a is not None:
                    setattr(y, attrName, y._inputs[a.in_i] if isinstance(a, HlsNetNodeIn) else y._outputs[a.out_i])
        return y, isNew

    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        nonOrderingInputs = (self._inputs[0], self.extraCond, self.skipWhen, self._inputOfCluster, self._outputOfCluster)
        for i in self._inputs:
            if i not in nonOrderingInputs:
                assert HdlType_isVoid(self.dependsOn[i.in_i]._dtype), i
                yield i

    def _addValid(self):
        assert self._valid is None, (self, "Already present")
        self._valid = self._addOutput(BIT, "valid", addDefaultScheduling=True)

    def _addValidNB(self):
        assert self._validNB is None, (self, "Already present")
        self._validNB = self._addOutput(BIT, "validNB", addDefaultScheduling=True)

    def getValid(self):
        if not self.hasValid():
            self._addValid()

        return self._valid

    def getValidNB(self):
        if not self.hasValidNB():
            self._addValidNB()

        return self._validNB

    def hasValid(self):
        return self._valid is not None

    def hasValidNB(self):
        return self._validNB is not None

    def hasAnyUsedValidPort(self):
        for valid in (self._valid, self._validNB):
            if valid is not None and self.usedBy[valid.out_i]:
                return True
        return False

    def hasValidOnlyToPassFlags(self):
        """
        :see: note at the end of doc for :class:`~.HlsNetNodeExplicitSync`
        """
        if self._rtlUseValid:
            return False

        for valid in (self._valid, self._validNB):
            if valid and self.usedBy[valid.out_i]:
                return True

        return False

    def hasAnyFormOfValidPort(self):
        return self._rtlUseValid or self.hasValid() or self.hasValidNB()

    def _addReady(self):
        assert self._ready is None, (self, "Already present")
        self._ready = self._addOutput(BIT, "ready", addDefaultScheduling=True)

    def _addReadyNB(self):
        assert self._readyNB is None, (self, "Already present")
        self._readyNB = self._addOutput(BIT, "readyNB", addDefaultScheduling=True)

    def getReady(self):
        if not self.hasReady():
            self._addReady()

        return self._ready

    def getReadyNB(self):
        if not self.hasReadyNB():
            self._addReadyNB()

        return self._readyNB

    def hasReady(self):
        return self._ready is not None

    def hasReadyNB(self):
        return self._readyNB is not None

    def hasAnyUsedReadyPort(self):
        for ready in (self._ready, self._readyNB):
            if ready is not None and self.usedBy[ready.out_i]:
                return True
        return False

    def hasReadyOnlyToPassFlags(self):
        """
        :see: note at the end of doc for :class:`~.HlsNetNodeExplicitSync`
        """
        if self._rtlUseReady:
            return False

        for ready in (self._ready, self._readyNB):
            if ready and self.usedBy[ready.out_i]:
                return True

        return False

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
            o = self._dataVoidOut = self._addOutput(HVoidData, "dataVoidOut", addDefaultScheduling=True)
        return o

    def getOrderingOutPort(self) -> HlsNetNodeOut:
        o = self._orderingOut
        if o is None:
            o = self._orderingOut = self._addOutput(HVoidOrdering, "orderingOut", addDefaultScheduling=True)
        return o

    def getInputOfClusterPort(self) -> HlsNetNodeIn:
        i = self._inputOfCluster
        if i is None:
            i = self._inputOfCluster = self._addInput("inputOfCluster", addDefaultScheduling=True)
        return i

    def getOutputOfClusterPort(self) -> HlsNetNodeIn:
        i = self._outputOfCluster
        if i is None:
            i = self._outputOfCluster = self._addInput("outputOfCluster", addDefaultScheduling=True)
        return i

    def getExtraCondDriver(self) -> Optional[HlsNetNodeOut]:
        if self.extraCond is None:
            return None
        else:
            return self.dependsOn[self.extraCond.in_i]

    def getSkipWhenDriver(self) -> Optional[HlsNetNodeOut]:
        if self.skipWhen is None:
            return None
        else:
            return self.dependsOn[self.skipWhen.in_i]

    @override
    def _removeInput(self, index:int):
        iObj = self._inputs[index]
        if self.extraCond is iObj:
            self.extraCond = None
        elif self.skipWhen is iObj:
            self.skipWhen = None
        elif self._inputOfCluster is iObj:
            self._inputOfCluster = None
            # raise AssertionError("_inputOfCluster input port can not be removed because the cluster must be always present")
        elif self._outputOfCluster is iObj:
            self._outputOfCluster = None
            # raise AssertionError("_outputOfCluster input port can not be removed because the cluster must be always present")
        return HlsNetNodeOrderable._removeInput(self, index)

    @override
    def _removeOutput(self, index:int):
        oObj = self._outputs[index]
        if oObj is self._orderingOut:
            self._orderingOut = None
        elif oObj is self._dataVoidOut:
            self._dataVoidOut = None

        return HlsNetNodeOrderable._removeOutput(self, index)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        raise AssertionError("This node should be translated to channel communication and is not intended for RTL")

    def addControlSerialExtraCond(self, en: Union[HlsNetNodeOut, HlsNetNodeOutLazy], addDefaultScheduling:bool=False):
        """
        Add additional extraCond flag and if there was already some flag join them as if they were in sequence.
        """
        i = self.extraCond
        if i is None:
            self.extraCond = i = self._addInput("extraCond", addDefaultScheduling=addDefaultScheduling)
            link_hls_nodes(en, i)
        else:
            # create "and" of existing and new extraCond and use it instead
            cur = self.dependsOn[i.in_i]
            if cur is en:
                return  # no need to update
            en = self.netlist.builder.buildAnd(cur, en)
            if en is not cur:
                i.replaceDriver(en)

    def addControlSerialSkipWhen(self, skipWhen: Union[HlsNetNodeOut, HlsNetNodeOutLazy], addDefaultScheduling:bool=False):
        """
        Add additional skipWhen flag and if there was already some flag join them as if they were in sequence.
        """
        i = self.skipWhen
        if i is None:
            self.skipWhen = i = self._addInput("skipWhen", addDefaultScheduling=addDefaultScheduling)
            link_hls_nodes(skipWhen, i)
        else:
            cur = self.dependsOn[i.in_i]
            if cur is skipWhen:
                return  # no need to update
            skipWhen = self.netlist.builder.buildOr(cur, skipWhen)
            if cur is not skipWhen:
                i.replaceDriver(skipWhen)

    @override
    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def __repr__(self, minify=False):
        if minify:
            if self.name is None:
                return f"<{self.__class__.__name__:s} {self._id:d}>"
            else:
                return f"<{self.__class__.__name__:s} {self._id:d} \"{self.name:s}\">"
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
            name = f' \"{self.name:s}\"' if self.name else ''
            return (f"<{self.__class__.__name__:s} {self._id:d}{name:s} in={HlsNetNodeOut._reprMinified(dep)}, "
                    f"extraCond={HlsNetNodeOut._reprMinified(ec)}, "
                    f"skipWhen={HlsNetNodeOut._reprMinified(sw)}>")

