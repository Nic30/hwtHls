from math import inf
from typing import Set, List, Optional, Sequence

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import ALWAYS_COMMUTATIVE_OPS, \
    CMP_OP_SWAP
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.builder import HlsNetlistBuilder, \
    HlsNetlistBuilderOperatorCache_t, HlsNetlistBuilderOperatorCacheKey_t
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import disconnectAllInputs, iterAllHierachies
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class _ExprRehasher():

    def __init__(self, worklist: Optional[SetList[HlsNetNode]],
                       b: HlsNetlistBuilder,
                       seen: Set[HlsNetNode],
                       operatorCache:Optional[HlsNetlistBuilderOperatorCache_t]=None):
        self.worklist = worklist
        self.b = b
        if operatorCache is None:
            operatorCache = b.operatorCache
        self.operatorCache = operatorCache
        self.seen = seen

    def _normalizeOperands(self, ops: List[HlsNetNodeOut]):
        """
        order by (o.obj._id, o.out_i) for non constant values and for constant use value for sorting and add them at the end
        """
        _ops = []
        for o in ops:
            o = self._rehashExpr(o)
            if isinstance(o.obj, HlsNetNodeConst):
                v = o.obj.val
                if isinstance(v.val, slice):
                    _v = v.to_py()
                    _v = (int(_v.start), int(_v.stop), int(_v.step))
                else:
                    _v = v
                key = (inf, _v)
            else:
                v = o
                key = (o.obj._id, o.out_i)
            # key for sorting, output object, value to store in cache
            _ops.append((key, o, v))

        return _ops

    def _handleDuplicatedNodes(self,
                               curentInCache: HlsNetNodeOut,
                               newFound: HlsNetNodeOut,
                               cacheKey: HlsNetlistBuilderOperatorCacheKey_t) -> HlsNetNodeOut:
        # remove newFound and replace it with a curentInCache
        worklist = self.worklist
        n = newFound.obj
        if worklist is not None:
            worklist.extend(dep.obj for dep in n.dependsOn)
            worklist.append(curentInCache.obj)

        self.b.replaceOutput(newFound, curentInCache, False)
        disconnectAllInputs(n, [])
        n.markAsRemoved()
        return curentInCache

    def _rehashExpr(self, o: HlsNetNodeOut) -> HlsNetNodeOut:
        """
        drill down to def in def->use chain and start rehashing process there
        
        * remove duplicated equivalent nodes
        * normalized order of operands for associative nodes
        """
        n = o.obj

        assert not n._isMarkedRemoved, n
        if n in self.seen:
            return o

        elif isinstance(n, HlsNetNodeOperator):  # (HlsNetNodeMux is also operator)
            n: HlsNetNodeOperator
            # if n.operator in ALWAYS_ASSOCIATIVE_COMMUTATIVE_OPS:
            #    raise NotImplementedError("collect whole tree")
            _ops = self._normalizeOperands(n.dependsOn)
            oppositeCmpOp = CMP_OP_SWAP.get(n.operator, None)
            if n.operator in ALWAYS_COMMUTATIVE_OPS or (oppositeCmpOp is not None and isinstance(_ops[0][2], HConst)):
                _ops = sorted(_ops, key=lambda x: (int(not isinstance(x[2], HConst)), x[0]))

            # ops = [o[1] for o in _ops]
            cacheKey = (n.operator, tuple(o[2] for o in _ops))
            cur = self.operatorCache.get(cacheKey)
            if cur is None or cur.obj._isMarkedRemoved:
                # there is no equivalent known node yet, use this as a value
                # n.dependsOn = ops  # to normalize order of operands
                # if worklist is not None and ops != n.dependsOn:
                #    worklist.append(n)
                self.operatorCache[cacheKey] = o
                assert not o.obj._isMarkedRemoved, o
                self.seen.add(o.obj)
                return o

            elif cur is o:
                # o was previously discovered while this rehash
                return o

            else:
                # remove this o and replace it with an existing value
                return self._handleDuplicatedNodes(cur, o, cacheKey)
        else:
            # a node which is not subject of a rehash
            self.seen.add(n)
            return o

    def rehashNodes(self, nodes: Sequence[HlsNetNode]):
        for n in nodes:
            # for each node walk all unseen predecessor nodes and substitute nodes with previously known equivalent node
            n: HlsNetNode
            if n._isMarkedRemoved:
                continue
            for o in n._outputs:
                self._rehashExpr(o)


class HlsNetlistPassRehashDeduplicate(HlsNetlistPass):
    """
    De-duplicate all nodes in netlist using structural hashing.
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx,
              worklist: Optional[SetList[HlsNetNode]]=None) -> PreservedAnalysisSet:
        """
        :note: worklist and removed set can be used to track which nodes were changed and removed
        """

        seen: Set[HlsNetNode] = set()

        filterNodes = False
        changed = False
        if worklist is None:
            filterNodes = True

        for parent in iterAllHierachies(netlist):
            b: HlsNetlistBuilder = parent.builder
            b.operatorCache.clear()
            rehasher = _ExprRehasher(worklist, b, seen)
            rehasher.rehashNodes(parent.subNodes)
            if b._removedNodes:
                changed = True

            if filterNodes:
                parent.filterNodesUsingRemovedSet(recursive=False)

        if changed:
            return PreservedAnalysisSet.preserveReachablity()
        else:
            return PreservedAnalysisSet.preserveAll()
