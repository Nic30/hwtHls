from typing import Type, Union

from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.ssa.analysis.ssaAnalysisPass import SsaAnalysisPass

AnalysisPass = Union[SsaAnalysisPass, HlsNetlistAnalysisPass]


class AnalysisCache():

    def __init__(self):
        self._analysis_cache = {}

    def invalidateAnalysis(self, analysis_cls:Type[AnalysisPass]):
        a = self._analysis_cache.pop(analysis_cls, None)
        if a is not None:
            a.invalidate()

    def getAnalysisIfAvailable(self, analysis_cls:Type[AnalysisPass]):
        try:
            return self._analysis_cache[analysis_cls]
        except KeyError:
            return None

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
            a = analysis_cls(self)

        self._analysis_cache[analysis_cls] = a
        a.run()
        return a
