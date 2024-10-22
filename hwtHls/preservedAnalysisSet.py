from typing import Set, Type, Union, Iterable

from hwt.constants import NOT_SPECIFIED
from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler

AnalysisKey = Union[Type[HlsArchAnalysisPass],
                    Type[HlsNetlistAnalysisPass]]


class PreservedAnalysisSet(Set[AnalysisKey]):

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
        return cls(((HlsNetlistAnalysisPassReachability, HlsNetlistAnalysisPassRunScheduler)))

    @classmethod
    def preserveSchedulingOnly(cls):
        return cls(((HlsNetlistAnalysisPassRunScheduler, )))

    @classmethod
    def preserveReachablity(cls):
        return cls(((HlsNetlistAnalysisPassReachability,)))
