from collections import OrderedDict
from typing import Type, Union, TypeVar, Generic, Self, Callable, Optional

from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.ssa.analysis.ssaAnalysisPass import SsaAnalysisPass

AnalysisPass = Union[SsaAnalysisPass, HlsNetlistAnalysisPass, HlsArchAnalysisPass]

AnalysisT = TypeVar("AnalysisT")
PassT = TypeVar("PassT")


class AnalysisCache(Generic[AnalysisT, PassT]):
    """
    A pass manager for analysis passes
    """

    def __init__(self):
        self._analysis_cache = OrderedDict()
        self.callbacksBeforeAnalysis: list[Callable[[Type, AnalysisT, Self], None]] = []
        self.callbacksAfterAnalysis: list[Callable[[Type, AnalysisT, Self], None]] = []
        self.callbacksInvalidateAnalysis: list[Callable[[Type, AnalysisT, Self], None]] = []
        self.callbacksBeforePass: list[Callable[[Type, PassT, Self], None]] = []
        self.callbacksAfterPass: list[Callable[[Type, PassT, Self], None]] = []
        self.instrumentations: Optional["HwtHlsInstrumentations"] = None

    def invalidateAnalysis(self, analysis_cls:Type[AnalysisT]):
        a = self._analysis_cache.pop(analysis_cls, None)
        if a is not None:
            for cb in self.callbacksInvalidateAnalysis:
                cb(analysis_cls, a, self)
            a.invalidate(self)
        else:
            toRm = []
            for k in self._analysis_cache.keys():
                if k.__class__ is analysis_cls:
                    toRm.append(k)
            for k in reversed(toRm):
                self.invalidateAnalysis(k)

    def invalidateAnalysisUsingPreservedAnalysisSet(self, pa: "PreservedAnalysisSet"):
        if not pa.isAll:
            if not pa:
                for k, v in self._analysis_cache.items():
                    for cb in self.callbacksInvalidateAnalysis:
                        cb(k, v, self)
                    v.invalidate(self)
            else:
                toRm = []
                for k, v in self._analysis_cache.items():
                    if k in pa or k.__class__ in pa:
                        continue
                    else:
                        toRm.append(k)
                for k in toRm:
                    self.invalidateAnalysis(k)

    def getAnalysisIfAvailable(self, analysis_cls:Type[AnalysisT]):
        try:
            return self._analysis_cache[analysis_cls]
        except KeyError:
            return None

    def _runAnalysisImpl(self, a):
        raise NotImplementedError()

    def getAnalysis(self, analysis_cls:Union[Type[AnalysisT], AnalysisT]):
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
