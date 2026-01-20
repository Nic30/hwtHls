import sys
from typing import Optional

epsilon = sys.float_info.epsilon

SchedTime = int


def clkWindowIndex(time: SchedTime, clkPeriod: SchedTime):
    """
    Get index of clock window where the time lies
    :param clkPeriod: width of the clock time window
    """
    assert -49 // 1001 == -1
    # if time < 0:
    #    return (time // clkPeriod) - 1
    # else:
    return time // clkPeriod


def clkWindowOffsetFromWindowBegin(time: SchedTime, clkPeriod: SchedTime):
    clkI = time // clkPeriod
    # the clock window begins on left (lower) side
    if clkI >= 0:
        return time - (clkI * clkPeriod)
    else:
        return -((clkI * clkPeriod) - time)

    # return time - (time // clkPeriod) * clkPeriod


def clkWindowOffsetFromWindowEnd(time: SchedTime, clkPeriod: SchedTime):
    return clkWindowBeginOfNext(time, clkPeriod) - time


def clkWindowBeginForTime(time: SchedTime, clkPeriod: SchedTime):
    """
    Get begin time of clk window for a time somewhere inside of the window.
    """
    return clkWindowIndex(time, clkPeriod) * clkPeriod


def clkWindowBegin(clkIndex:int, clkPeriod: SchedTime):
    return clkIndex * clkPeriod


def clkWindowEnd(clkIndex: int, clkPeriod: SchedTime):
    return clkWindowBegin(clkIndex + 1, clkPeriod) - 1


def clkWindowBeginOfNext(time: SchedTime, clkPeriod: SchedTime):
    clkI = clkWindowIndex(time, clkPeriod)
    return (clkI + 1) * clkPeriod


def SchedTime_format(time: Optional[SchedTime], clkPeriod: SchedTime) -> str:
    if time is None:
        return ""

    clkI = clkWindowIndex(time, clkPeriod)
    inClkPos = clkWindowOffsetFromWindowBegin(time, clkPeriod)
    return f" {clkI}clk+{inClkPos}"
