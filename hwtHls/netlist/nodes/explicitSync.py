from typing import Union, Optional, Generator, Tuple

from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.hwIOs.std import HwIORdVldSync, HwIODataRd, HwIODataVld
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering, HVoidData, \
    HdlType_isVoid
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HlsNetNodeOrderable
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    HlsNetNodeOutLazy
from hwtHls.netlist.scheduler.clk_math import epsilon
from hwtHls.platform.opRealizationMeta import OpRealizationMeta


IO_COMB_REALIZATION = OpRealizationMeta(outputWireDelay=epsilon)


class HlsNetNodeExplicitSync(HlsNetNodeOrderable):
    """
    This node is a base class for nodes with an extra synchronization conditions.
    :see: :class:`hwtLib.handshaked.streamNode.StreamNode`

    It is used to stall/drop/not-require some data based on external conditions.
    
    Explicit sync flag combinations (both flags are optional)
    ---------------------------------------------|---------------------------|
    | extraCond | skipWhen | meaning for read  | meaning for write           |
    ==========================================================================
    | 0         | 0        | block             | block                       |
    | 1         | 0        | read, accept      | write, produce              |
    | 0         | 1        | skip read/peek    | skip set data but no valid  |
    | 1         | 1        | read non blocking | write non blocking          |
    --------------------------------------------------------------------------


    :ivar extraCond: an input for a flag which must be true to allow the transaction (is blocking until 1)
    :ivar skipWhen: an input for a flag which marks that this write should be skipped and transaction
                    will not be performed but the control flow will continue
    :ivar _associatedReadSync: A node which use only during optimization phase, it reads _validNB of this node.
    :ivar _orderingOut: an output used for ordering connections
    :ivar _dataVoidOut: an output which is used for data connection of a void type,
        this is used to represent the ordering after data dependency was optimized out, but previously was there.
    :ivar _ready: output with "ready" signal for writes this signalizes that the write was successful.
        Reading of this port requires write to be performed.
    :ivar _readyNB: same as "_ready" but reading this does not cause write from main interface.
    :ivar _valid: output with "valid" signal for reads which signalizes that the read was successful.
        Reading of this port requires read to be performed.
    :ivar _validNB: same as "_valid" but reading this does not cause read from main interface.
    :attention: valid/ready is not affected by any other flag (extraCond, skipWhen) and it may become 1
        even if node operation was not performed. (done to avoid comb. path inside of this node)
    :ivar _forceEnPort: A port of sync flag which tells that the function of this node should be performed even if
        the parent sync node is not activated.
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
    _PORT_ATTR_NAMES = ["_valid", "_validNB", "_ready", "_readyNB",
                         "extraCond", "skipWhen", "_forceEnPort",
                         "_orderingOut", "_dataVoidOut", ]

    def __init__(self, netlist: "HlsNetlistCtx", dtype: HdlType, name:Optional[str]=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None
        self._initCommonPortProps(None)

    def _initCommonPortProps(self, io: Optional[HwIO]):
        self._valid: Optional[HlsNetNodeOut] = None
        self._validNB: Optional[HlsNetNodeOut] = None
        self._ready: Optional[HlsNetNodeOut] = None
        self._readyNB: Optional[HlsNetNodeOut] = None

        self.extraCond: Optional[HlsNetNodeIn] = None
        self.skipWhen: Optional[HlsNetNodeIn] = None
        self._forceEnPort: Optional[HlsNetNodeOut] = None
        self._orderingOut: Optional[HlsNetNodeOut] = None
        self._dataVoidOut: Optional[HlsNetNodeOut] = None
        self._rtlUseReady = io is None or isinstance(io, (HwIORdVldSync, HwIODataRd))
        self._rtlUseValid = io is None or isinstance(io, (HwIORdVldSync, HwIODataVld))

    def setRtlUseValid(self, rtlUseValid: bool):
        if not rtlUseValid:
            for valid in (self._valid, self._validNB):
                if valid is not None:
                    self._removeOutput(valid.out_i)
        self._rtlUseValid = rtlUseValid

    def setRtlUseReady(self, rtlUseReady: bool):
        if not rtlUseReady:
            for ready in (self._ready, self._readyNB):
                if ready is not None:
                    self._removeOutput(ready.out_i)

        self._rtlUseReady = rtlUseReady

    @override
    def clone(self, memo:dict, keepTopPortsConnected: bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNodeOrderable.clone(self, memo, keepTopPortsConnected)
        if isNew:
            readSync = self._associatedReadSync
            if readSync is not None:
                y._associatedReadSync = readSync.clone(memo)
            for attrName in self._PORT_ATTR_NAMES:
                a = getattr(self, attrName)
                if a is not None:
                    setattr(y, attrName, y._inputs[a.in_i] if isinstance(a, HlsNetNodeIn) else y._outputs[a.out_i])
        return y, isNew

    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        nonOrderingInputs = (self._inputs[0], self.extraCond, self.skipWhen)
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

    def getForceEnPort(self) -> HlsNetNodeIn:
        """
        :see: doc of :class:`HlsNetNodeExplicitSync` for \\_forceEnPort flag
        """
        forceEn = self._forceEnPort
        if forceEn is None:
            netlist = self.netlist
            forceEn = self._forceEnPort = self._addInput(
                "forceEn", addDefaultScheduling=True,
                # = at the end of clock where this write is
                inputClkTickOffset=0,
                inputWireDelay=netlist.normalizedClkPeriod - self.scheduledZero - netlist.scheduler.epsilon)
        return forceEn

    def getDataVoidOutPort(self) -> HlsNetNodeOut:
        """
        Get port which used for data dependency which is of a void type.
        """
        o = self._portDataOut
        if o is not None and o._dtype == HVoidData:
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

        return HlsNetNodeOrderable._removeInput(self, index)

    @override
    def _removeOutput(self, index:int):
        oObj = self._outputs[index]
        if oObj is self._orderingOut:
            self._orderingOut = None
        elif oObj is self._dataVoidOut:
            self._dataVoidOut = None
        elif oObj is self._valid:
            self._valid = None
        elif oObj is self._validNB:
            self._validNB = None
        elif oObj is self._ready:
            self._ready = None
        elif oObj is self._readyNB:
            self._readyNB = None

        return HlsNetNodeOrderable._removeOutput(self, index)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        raise AssertionError("This is an abstract class and the child class should override this", self.__class__)

    def addControlSerialExtraCond(self, en: Union[HlsNetNodeOut, HlsNetNodeOutLazy], addDefaultScheduling:bool=False, checkCycleFree:bool=True):
        """
        Add additional extraCond flag and if there was already some flag join them as if they were in sequence.
        """
        i = self.extraCond
        if i is None:
            self.extraCond = i = self._addInput("extraCond", addDefaultScheduling=addDefaultScheduling)
            en.connectHlsIn(i, checkCycleFree=checkCycleFree)
        else:
            # create "and" of existing and new extraCond and use it instead
            cur = self.dependsOn[i.in_i]
            if cur is en:
                return  # no need to update
            en = self.getHlsNetlistBuilder().buildAnd(cur, en)
            if en is not cur:
                i.replaceDriver(en)

    def addControlSerialSkipWhen(self, skipWhen: Union[HlsNetNodeOut, HlsNetNodeOutLazy], addDefaultScheduling:bool=False, checkCycleFree:bool=True):
        """
        Add additional skipWhen flag and if there was already some flag join them as if they were in sequence.
        """
        i = self.skipWhen
        if i is None:
            self.skipWhen = i = self._addInput("skipWhen", addDefaultScheduling=addDefaultScheduling)
            skipWhen.connectHlsIn(i, checkCycleFree=checkCycleFree)
        else:
            cur = self.dependsOn[i.in_i]
            if cur is skipWhen:
                return  # no need to update
            skipWhen = self.getHlsNetlistBuilder().buildOr(cur, skipWhen)
            if cur is not skipWhen:
                i.replaceDriver(skipWhen)

    @override
    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def _stringFormatRtlUseReadyAndValid(self):
        if self._rtlUseReady and self._rtlUseValid:
            return "<r, v>"
        elif self._rtlUseReady:
            return "<r>"
        elif self._rtlUseValid:
            return "<v>"
        else:
            return "<>"

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

