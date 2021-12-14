from typing import Union, List

from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.clk_math import start_clk, end_clk, epsilon
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal


class TimeIndependentRtlResourceItem():
    __slots__ = ["parent", "data"]

    def __init__(self, parent:"TimeIndependentRtlResource", data:Interface):
        self.parent = parent
        self.data = data

    def is_rlt_register(self) -> bool:
        return (self.parent.valuesInTime[0] is not self or
                isinstance(self.parent.valuesInTime[0].data, RtlSyncSignal))

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.data}>"


class TimeIndependentRtlResource():
    """
    Container of resource which manages access to resource
    in different times

    (dynamically generates register chains and synchronization
     to pass values to specified clk periods)
    """
    INVARIANT_TIME = "INVARIANT_TIME"
    # time constant, which means that item is not time dependent
    # and can be accessed any time
    __slots__ = ["timeOffset", "allocator", "valuesInTime"]

    def __init__(self, data: Union[RtlSignal, Interface, HValue],
                 time: Union[int, "TimeIndependentRtlResource.INVARIANT_TIME"],
                 hlsAllocator: "HlsAllocator"):
        """
        :param data: signal with value in initial time
        :param time: number of clock form start when valid data appears on "signal"
            (constant INVARIANT_TIME is used if input signal is constant
             and does not require any registers and synchronizations)
        :param hlsAllocator: HlsAllocator instance to generate registers an synchronization logic

        :ivar valuesInTime: list (chain) of signals (register outputs) for clk periods specified by index
        """
        self.timeOffset = time
        self.allocator = hlsAllocator
        self.valuesInTime: List[TimeIndependentRtlResourceItem] = [
            TimeIndependentRtlResourceItem(self, data),
        ]

    def get(self, time: float) -> TimeIndependentRtlResourceItem:
        """
        Get value of signal in specified time (clk period)
        """

        # if time is first time in live of this value return original signal
        time += epsilon
        if self.timeOffset is self.INVARIANT_TIME or self.timeOffset == time:
            return self.valuesInTime[0]

        # else try to look up register for this signal in valuesInTime cache
        clk_period = self.allocator.parentHls.clk_period
        dst_clk_period = end_clk(time, clk_period)
        index = dst_clk_period - \
            start_clk(self.timeOffset, clk_period)

        assert index >= 0, (self.timeOffset, time, self.valuesInTime[0])
        try:
            return self.valuesInTime[index]
        except IndexError:
            pass

        # allocate registers to propagate value into next cycles
        sig = self.valuesInTime[0]
        prev = self.valuesInTime[-1]
        requestedRegCnt = index + 1
        actualTimesCnt = len(self.valuesInTime)

        # HValue instance should have never get the there
        if isinstance(sig.data, Interface):
            name = sig.data._getHdlName()
        else:
            name = sig.data.name
        # allocate specified number of registers to pass value to specified pieline stage
        regsToAdd = requestedRegCnt - actualTimesCnt
        for i in reversed(range(regsToAdd)):
            reg = self.allocator._reg(f"{name:s}_delayTo{dst_clk_period - i:d}",
                                      dtype=sig.data._dtype)
            reg(prev.data)
            cur = TimeIndependentRtlResourceItem(self, reg)
            self.valuesInTime.append(cur)
            prev = cur

        return cur

    def checkIfExistsInClockCycle(self, clkCyleI: int):
        if self.timeOffset is self.INVARIANT_TIME:
            index = 0
        else:
            clk_period = self.allocator.parentHls.clk_period
            index = clkCyleI - start_clk(self.timeOffset, clk_period)
            if index < 0 or index >= len(self.valuesInTime):
                return None

        return self.valuesInTime[index]

    def __repr__(self):
        return f"<{self.__class__.__name__:s} for {self.valuesInTime[0].data}>"
