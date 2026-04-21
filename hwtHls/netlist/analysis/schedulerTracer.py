from io import StringIO
from typing import Optional, Sequence, Union

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.scheduler.clk_math import SchedTime_format, SchedTime

NodeTimeUpdatesTy = list[Union[
    str,  # label
    tuple[HlsNetNode, SchedTime, tuple[SchedTime, ...], tuple[SchedTime, ...]]  # node schedule update
]]


class TemproallOverrideTrackTimeOnCall():

    def __init__(self, node: HlsNetNode, name:str, nodeTimeUpdates: NodeTimeUpdatesTy):
        self.originalFn = getattr(node, name, None)
        if self.originalFn is None:
            return
        assert not isinstance(self.originalFn, TemproallOverrideTrackTimeOnCall), (node, name)
        self.node = node
        self.name = name
        self.nodeTimeUpdates = nodeTimeUpdates
        setattr(node, name, self)

    def undo(self):
        setattr(self.node, self.name, self.originalFn)

    def __call__(self, *args, **kwargs):
        try:
            self.originalFn(*args, **kwargs)
        finally:
            n = self.node
            self.nodeTimeUpdates.append((n, n.scheduledZero, n.scheduledIn, n.scheduledOut, self.name))


class HlsSchedulerTracer():
    _TRACED_METHODS = [
        "_setScheduleZeroTimeMultiClock",
        "_setScheduleZeroTimeSingleClock",
        "moveSchedulingTime",
        "setScheduling",
        "resetScheduling",
        "copySchedulingFromChildren",
    ]

    def __init__(self, scheduler: "HlsScheduler", logFile: Optional[StringIO]=None):
        self.nodeTimeUpdates: list[tuple[HlsNetNode, SchedTime, tuple[SchedTime, ...], tuple[SchedTime, ...]]] = []
        self.scheduler = scheduler
        self.logFile = logFile

    def _installListeners(self, nodes: Sequence[HlsNetNode]):
        nodeTimeUpdates = self.nodeTimeUpdates
        for n in nodes:
            for attr in self._TRACED_METHODS:
                TemproallOverrideTrackTimeOnCall(n, attr, nodeTimeUpdates)

            if isinstance(n, HlsNetNodeAggregate):
                self._installListeners(n.subNodes)

    def _uninstallListeners(self, nodes: Sequence[HlsNetNode]):
        for n in nodes:
            for attr in self._TRACED_METHODS:
                try:
                    ow: Optional[TemproallOverrideTrackTimeOnCall] = getattr(n, attr, None)
                    if ow is not None:
                        ow.undo()
                except:
                    raise AssertionError("There was some node which was not traced", n)
            if isinstance(n, HlsNetNodeAggregate):
                self._uninstallListeners(n.subNodes)

    def log(self, val, formatter=None):
        if formatter is not None:
            val = (val, formatter)
        self.nodeTimeUpdates.append(val)

    def __enter__(self):
        self._installListeners(self.scheduler.netlist.subNodes)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.logFile is not None:
            log = self.logFile.write
            clkPeriod = self.scheduler.netlist.normalizedClkPeriod
            for item in self.nodeTimeUpdates:
                if isinstance(item, str):
                    log(item)
                elif len(item) == 2:
                    n, name = item
                    if isinstance(name, str):
                        log(f"{n._id: 8}: ")
                        log(name)
                    else:
                        formatter = name
                        log(formatter(n))

                else:
                    n, schedZero, schedIn, schedOut, name = item
                    log(f"{n._id: 8}: ")
                    if schedZero is None:
                        log("-, ")
                    else:
                        log(SchedTime_format(schedZero, clkPeriod))
                        log(", ")
                    for schedInOut in (schedIn, schedOut):
                        if schedInOut is None:
                            log("-, ")
                        else:
                            log("(")
                            for isLast, t in iter_with_last(schedInOut):
                                if t is None:
                                    log("-")
                                else:
                                    log(SchedTime_format(t, clkPeriod))
                                if not isLast:
                                    log(", ")
                            log(")")
                        log(", ")
                    log(", ")
                    log(name)

                log("\n")

        self._uninstallListeners(self.scheduler.netlist.subNodes)

