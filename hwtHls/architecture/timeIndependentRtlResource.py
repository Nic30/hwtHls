from itertools import islice
from typing import Union, List, Tuple, Literal

from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.netlist.scheduler.clk_math import start_clk


class TimeIndependentRtlResourceItem():
    """
    for :class:`~.TimeIndependentRtlResource`
    """
    __slots__ = ["parent", "data", "isExplicitRegister"]

    def __init__(self, parent:"TimeIndependentRtlResource", data:Interface, isExplicitRegister: bool):
        self.parent = parent
        self.data = data
        self.isExplicitRegister = isExplicitRegister

    def isRltRegister(self) -> bool:
        return self.isExplicitRegister or (
                self.parent.valuesInTime[0] is not self or
                isinstance(self.parent.valuesInTime[0].data, RtlSyncSignal)
        )

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.data}>"


class INVARIANT_TIME():

    def __init__(self):
        raise AssertionError("Should not be instantiated this is used as a constant")


class TimeIndependentRtlResource():
    """
    Container of resource which manages access to resource
    in different times.

    (dynamically generates register chains and synchronization
     to pass values to specified clk periods)


    :ivar timeOffset: scheduling time when valid data appears on "signal"
        (constant INVARIANT_TIME is used if input signal is constant
        and does not require any registers and synchronizations)
    :ivar allocator: ArchElement instance to generate registers an synchronization logic
    :ivar valuesInTime: list (chain) of signals (register outputs) for clk periods specified by index
    :ivar persistenceRanges: sorted list of ranges of clock period indexes where the value may stay in previous register
        and new register is not required (and will not be allocated, the previous value will be used instead).
        (uses enclosed intervals, 0,1 means clock 0 and 1)
    :ivar isExplicitRegister: A flag which means that the beginning of life of this resource is a register
        which is instantiated at the time of the beginning and the synchronization from that time should be injected
        into register load logic.
    :ivar isForwardDeclr: The first value is forward declaration which will be replaced or driver will be added once it is resolved.
    :ivar mayChangeOutOfCfg: The first value may change from places which were not present in original CFG and thus the value
        must be copied if used in different time than the first one.
    """

    # time constant, which means that item is not time dependent
    # and can be accessed any time
    __slots__ = ["timeOffset", "allocator", "valuesInTime", "persistenceRanges", "isForwardDeclr", "mayChangeOutOfCfg"]

    def __init__(self, data: Union[RtlSignal, Interface, HValue],
                 timeOffset: Union[int, Literal[INVARIANT_TIME]],
                 allocator: "ArchElement",
                 isExplicitRegister: bool,
                 isForwardDeclr: bool,
                 mayChangeOutOfCfg: bool):
        """
        :param data: signal with value in initial time
        """
        if isinstance(data, HValue):
            assert timeOffset == INVARIANT_TIME
        self.timeOffset = timeOffset
        self.allocator = allocator
        self.valuesInTime: List[TimeIndependentRtlResourceItem] = [
            TimeIndependentRtlResourceItem(self, data, isExplicitRegister),
        ]
        if timeOffset is not INVARIANT_TIME:
            self.allocator.connections.getForTime(self.timeOffset).signals.append(self.valuesInTime[0])
        self.persistenceRanges: List[Tuple[int, int]] = []
        self.isForwardDeclr = isForwardDeclr
        self.mayChangeOutOfCfg = mayChangeOutOfCfg

    def markPersistent(self, beginClkIndex: int, endClkIndex: int):
        if self.persistenceRanges:
            raise NotImplementedError()
        else:
            self.persistenceRanges.append((beginClkIndex, endClkIndex))

    def _isInPersistenceRanges(self, clkIndex: int):
        for low, high in self.persistenceRanges:
            if clkIndex < low:
                # before cur. range
                continue
            elif high < clkIndex:
                # after cur. range
                return False
            else:
                # in cur. range
                return True

        return False

    def get(self, time: Union[int, Literal[INVARIANT_TIME]]) -> TimeIndependentRtlResourceItem:
        """
        Get value of signal in specified time (clk period)
        """

        # if time is first time in live of this value return original signal
        if self.timeOffset is INVARIANT_TIME:
            return self.valuesInTime[0]
        try:
            assert time >= self.timeOffset, ("This resource does not yet exist in requested time", time, ">=", self.timeOffset, self)
        except:
            raise
        netlist = self.allocator.netlist
        #epsilon = netlist.scheduler.epsilon
        #time += epsilon
        if self.timeOffset == time:
            return self.valuesInTime[0]

        # else try to look up register for this signal in valuesInTime cache
        clkPeriod = netlist.normalizedClkPeriod
        dstClkClkIndex = start_clk(time, clkPeriod)
        startClkIndex = start_clk(self.timeOffset, clkPeriod)
        index = dstClkClkIndex - startClkIndex
        assert index >= 0, (index, self.timeOffset, time, self.valuesInTime[0])
        try:
            return self.valuesInTime[index]
        except IndexError:
            pass

        # allocate registers to propagate value into next cycles
        sig = self.valuesInTime[0]

        # HValue instance should have never get the there
        if isinstance(sig.data, Interface):
            name = sig.data._getHdlName()
        else:
            name = sig.data.name
        # allocate specified number of registers to pass value to specified pipeline stage

        prev = self.valuesInTime[-1]
        connections = self.allocator.connections

        actualTimesCnt = len(self.valuesInTime)
        assert actualTimesCnt >= 0, (self, actualTimesCnt, "This should be initialized with at least one item.")
        firstRegClkIndex = None
        if self.persistenceRanges:
            firstAfterPersistentRangeBegin = self.persistenceRanges[0][0]
            for clkI, con in islice(enumerate(connections), firstAfterPersistentRangeBegin, None):
                if con is not None:
                    firstRegClkIndex = clkI
                    break
        for clkI in range(startClkIndex + actualTimesCnt, dstClkClkIndex + 1):
            isMarkedPersistent = self._isInPersistenceRanges(clkI + 1)
            cur = self.valuesInTime[-1]
            # :note: valuesInTime[0] was input signal
            #        valuesInTime[n] is first register (n is index of first clock window after 0 used by parent - startClkIndex)
            #        valuesInTime[n:] is reference to this register
            if not isMarkedPersistent or (firstRegClkIndex is not None and firstRegClkIndex == clkI):
                # create next register in register pipeline
                reg = self.allocator._reg(f"{name:s}_delayTo{clkI:d}",
                                          dtype=sig.data._dtype)
                # can not use prev.data directly as a reg.next because this assignment (reg.next = prev.data)
                # will be used to control
                reg.next(prev.data)
                cur = TimeIndependentRtlResourceItem(self, reg, True)

            con = connections.getForClkIndex(clkI, allowNone=True)
            if con is not None:
                # if time is managed by parent element
                sigs = con.signals
                sigs.append(cur)

            self.valuesInTime.append(cur)
            prev = cur

        return cur

    def checkIfExistsInClockCycle(self, clkCyleI: int):
        if self.timeOffset is INVARIANT_TIME:
            index = 0
        else:
            clkPeriod = self.allocator.netlist.normalizedClkPeriod
            index = clkCyleI - start_clk(self.timeOffset, clkPeriod)
            if index < 0 or index >= len(self.valuesInTime):
                return None

        return self.valuesInTime[index]

    def __repr__(self):
        return f"<{self.__class__.__name__:s} for {self.valuesInTime[0].data}>"
