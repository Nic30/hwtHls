from typing import Union, Optional, Tuple, Generator, List

from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOutAny, \
    HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead


class HlsNetNodeReadIndexed(HlsNetNodeRead):
    """
    Same as :class:`~.HlsNetNodeRead` but for memory mapped interfaces with address or index.
    """

    def __init__(self, netlist:"HlsNetlistCtx", src:Union[RtlSignal, HwIO], name:Optional[str]=None):
        HlsNetNodeRead.__init__(self, netlist, src, name=name)
        self.indexes = [self._addInput("index0"), ]

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNodeRead.clone(self, memo, keepTopPortsConnected)
        if isNew:
            y.indexes = [y._inputs[i.in_i] for i in self.indexes]

        return y, isNew

    @override
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        nonOrderingInputs = (self.extraCond, self.skipWhen, *self.indexes)
        for i in self._inputs:
            if i not in nonOrderingInputs:
                yield i

    @staticmethod
    def _strFormatIndexes(indexes: List[HlsNetNodeIn]):
        if indexes:
            indexesStrs = []
            for i in indexes:
                i: HlsNetNodeIn
                dep: Optional[HlsNetNodeOutAny] = i.obj.dependsOn[i.in_i]
                if isinstance(dep, HlsNetNodeOut):
                    indexesStrs.append(f"<{dep.obj._id:d}>.{dep.out_i:d}")
                else:
                    indexesStrs.append(repr(dep))

            return f"[{','.join(indexesStrs)}]"
        else:
            return ""

    def __repr__(self):
        return (f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}{' ' + self.name if self.name else ''}"
               f" {self._stringFormatRtlUseReadyAndValid():s} {self.src}{self._strFormatIndexes(self.indexes)}>")
