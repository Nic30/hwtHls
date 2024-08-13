from collections import OrderedDict
from typing import Type, Union

from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.ssa.analysis.ssaAnalysisPass import SsaAnalysisPass


AnalysisPass = Union[SsaAnalysisPass, HlsNetlistAnalysisPass, HlsArchAnalysisPass]


class AnalysisCache():
    """
    A pass manager for analysis passes
    """

    def __init__(self,):
        self._analysis_cache = OrderedDict()

    def invalidateAnalysis(self, analysis_cls:Type[AnalysisPass]):
        a = self._analysis_cache.pop(analysis_cls, None)
        if a is not None:
            a.invalidate(self)
        else:
            toRm = []
            for k in self._analysis_cache.keys():
                if k.__class__ is analysis_cls:
                    toRm.append(k)
            for k in reversed(toRm):
                self.invalidateAnalysis(k)

    def getAnalysisIfAvailable(self, analysis_cls:Type[AnalysisPass]):
        try:
            return self._analysis_cache[analysis_cls]
        except KeyError:
            return None

    def _runAnalysisImpl(self, a):
        raise NotImplementedError()

    def getAnalysis(self, analysis_cls:Union[Type[AnalysisPass], AnalysisPass]):
        if isinstance(analysis_cls, (SsaAnalysisPass, HlsNetlistAnalysisPass)):
            a = analysis_cls
        else:
            a = None

        try:
            return self._analysis_cache[analysis_cls]
        except KeyError:
            pass

        if a is None:
            a = analysis_cls()

        self._analysis_cache[analysis_cls] = a
        self._runAnalysisImpl(a)
        return a
