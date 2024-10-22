from typing import Optional, Set, Sequence

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.builder import HlsNetlistBuilder, \
    HlsNetlistBuilderOperatorCacheKey_t
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyExpr.rehash import _ExprRehasher


class _ExprRehasherClockWindowOnly(_ExprRehasher):

    def __init__(self,
                 parent: ArchElement,
                 clockIndex: int,
                 worklist:Optional[SetList[HlsNetNode]],
                 b:HlsNetlistBuilder,
                 seen:Set[HlsNetNode],):
        _ExprRehasher.__init__(self, worklist, b, seen, operatorCache={})
        self.parent = parent
        self.beginTime = clockIndex * parent.netlist.normalizedClkPeriod

    @override
    def _handleDuplicatedNodes(self,
        curentInCache:HlsNetNodeOut,
        newFound:HlsNetNodeOut,
        cacheKey:HlsNetlistBuilderOperatorCacheKey_t) -> HlsNetNodeOut:
        if newFound.obj.scheduledOut[newFound.out_i] < curentInCache.obj.scheduledOut[curentInCache.out_i]:
            # if time of newFound is lower use it and replace curentInCache
            newFound, curentInCache = curentInCache, newFound
        # else replace newFound with curentInCache
        return _ExprRehasher._handleDuplicatedNodes(self, curentInCache, newFound, cacheKey)

    @override
    def _rehashExpr(self, o:HlsNetNodeOut):
        if o.obj.scheduledOut[o.out_i] < self.beginTime:
            return o  # do not cross clock window boundary
        return _ExprRehasher._rehashExpr(self, o)


    @classmethod
    def rehashNodesInElements(cls, worklist: SetList[HlsNetNode], elements: Sequence[ArchElement]):
        for elm in elements:
            if isinstance(elm, ArchElement):
                elm: ArchElement
                for clockIndex, nodes in elm.iterStages():
                    rehasher = cls(elm, clockIndex, worklist, elm.builder, set())
                    rehasher.rehashNodes(nodes)
                    elm.builder.operatorCache.update(rehasher.operatorCache)
