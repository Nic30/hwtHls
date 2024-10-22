from typing import Union, Optional, Generator, Tuple

from hwt.constants import NOT_SPECIFIED
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn
from hwtHls.netlist.nodes.readIndexed import HlsNetNodeReadIndexed
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.ssa.value import SsaValue


class HlsNetNodeWriteIndexed(HlsNetNodeWrite):
    """
    Same as :class:`~.HlsNetNodeWrite` but for memory mapped interfaces with address or index.
    """

    def __init__(self, netlist:"HlsNetlistCtx", dst:Union[RtlSignal, HwIO, SsaValue],
                 mayBecomeFlushable=False,
                 name:Optional[str]=None,
                 addSrcPort=True):
        HlsNetNodeWrite.__init__(self, netlist, dst,
                                 mayBecomeFlushable=mayBecomeFlushable,
                                 name=name,
                                 addSrcPort=addSrcPort)
        self.indexes = [self._addInput("index0"), ]

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNodeWrite.clone(self, memo, keepTopPortsConnected)
        if isNew:
            y.indexes = [y._inputs[i.in_i] for i in self.indexes]

        return y, isNew

    @override
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        allNonOrdering = (self._inputs[0], self.extraCond, self.skipWhen, *self.indexes)
        for i in self._inputs:
            if i not in allNonOrdering:
                yield i

    def __repr__(self, minify=False):
        src = self.src
        if src is NOT_SPECIFIED:
            src = self.dependsOn[0]
        dstName = self._getInterfaceName(self.dst)
        if minify:
            return (f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}{' ' + self.name if self.name else ''}"
                f" {self._stringFormatRtlUseReadyAndValid():s} {dstName}>")
        else:
            return (
                f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}{' ' + self.name if self.name else ''}"
                f" {self._stringFormatRtlUseReadyAndValid():s} {dstName}{HlsNetNodeReadIndexed._strFormatIndexes(self.indexes)} <- {src} >"
            )
