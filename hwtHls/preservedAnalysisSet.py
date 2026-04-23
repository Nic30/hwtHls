from typing import Set, Type, Union, Iterable

from hwt.constants import NOT_SPECIFIED
from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass

AnalysisKey = Union[Type[HlsArchAnalysisPass],
                    Type[HlsNetlistAnalysisPass]]


class PreservedAnalysisSet(Set[AnalysisKey]):
    HlsNetlistAnalysisPassRunScheduler = None
    HlsNetlistAnalysisPassReachability = None

    def __init__(self, iterable:Iterable[AnalysisKey]=NOT_SPECIFIED, isAll=False):
        if iterable is NOT_SPECIFIED:
            iterable = ()
        set.__init__(self, iterable)
        self.isAll = isAll

    @classmethod
    def preserveAll(cls):
        return cls(isAll=True)

    @classmethod
    def preserveScheduling(cls):
        if cls.HlsNetlistAnalysisPassReachability is None:
            from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
            cls.HlsNetlistAnalysisPassReachability = HlsNetlistAnalysisPassReachability
        if cls.HlsNetlistAnalysisPassRunScheduler is None:
            from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
            cls.HlsNetlistAnalysisPassRunScheduler = HlsNetlistAnalysisPassRunScheduler

        return cls(((cls.HlsNetlistAnalysisPassReachability, cls.HlsNetlistAnalysisPassRunScheduler)))

    @classmethod
    def preserveSchedulingOnly(cls):
        if cls.HlsNetlistAnalysisPassRunScheduler is None:
            from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
            cls.HlsNetlistAnalysisPassRunScheduler = HlsNetlistAnalysisPassRunScheduler
        return cls(((cls.HlsNetlistAnalysisPassRunScheduler,)))

    @classmethod
    def preserveReachablity(cls):
        if cls.HlsNetlistAnalysisPassReachability is None:
            from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
            cls.HlsNetlistAnalysisPassReachability = HlsNetlistAnalysisPassReachability
        return cls(((cls.HlsNetlistAnalysisPassReachability,)))

