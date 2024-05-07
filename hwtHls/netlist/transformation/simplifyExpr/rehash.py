from math import inf
from typing import Set, List, Optional

from hwt.hdl.operatorDefs import ALWAYS_COMMUTATIVE_OPS, \
    CMP_OP_SWAP
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifyUtils import disconnectAllInputs
from hwtHls.typingFuture import override


class HlsNetlistPassRehashDeduplicate(HlsNetlistPass):
    """
    De-duplicate all nodes in netlist.
    """

    def _normalizeOperands(self,
                           ops: List[HlsNetNodeOut],
                           worklist: Optional[UniqList[HlsNetNode]],
                           b: HlsNetlistBuilder,
                           seen: Set[HlsNetNode],
                           removed: Set[HlsNetNode]):
        """
        order by (o.obj._id, o.out_i) for non constant values and for constant use value for sorting and add them at the end
        """
        _ops = []
        for o in ops:
            o = self._rehashExpr(b, o, worklist, seen, removed)
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

    def _rehashExpr(self,
                    b: HlsNetlistBuilder,
                    o: HlsNetNodeOut,
                    worklist: Optional[UniqList[HlsNetNode]],
                    seen: Set[HlsNetNode],
                    removed: Set[HlsNetNode]):
        """
        drill down to def in def->use chain and start rehashing process there
        
        * remove duplicated equivalent nodes
        * normalized order of operands for associative nodes
        """
        n = o.obj

        assert n not in removed, n
        if n in seen:
            return o

        elif isinstance(n, HlsNetNodeOperator):  # (HlsNetNodeMux is also operator)
            n: HlsNetNodeOperator
            # if n.operator in ALWAYS_ASSOCIATIVE_COMMUTATIVE_OPS:
            #    raise NotImplementedError("collect whole tree")
            _ops = self._normalizeOperands(n.dependsOn, worklist, b, seen, removed)
            oppositeCmpOp = CMP_OP_SWAP.get(n.operator, None)
            if n.operator in ALWAYS_COMMUTATIVE_OPS or (oppositeCmpOp is not None and isinstance(_ops[0][2], HValue)):
                _ops = sorted(_ops, key=lambda x: (int(not isinstance(x[2], HValue)), x[0]))

            # ops = [o[1] for o in _ops]
            cacheKey = (n.operator, tuple(o[2] for o in _ops))
            cur = b.operatorCache.get(cacheKey)
            if cur is None or cur.obj in removed:
                # use this as a value
                # n.dependsOn = ops  # to normalize order of operands
                # if worklist is not None and ops != n.dependsOn:
                #    worklist.append(n)
                b.operatorCache[cacheKey] = o
                assert o.obj not in removed
                seen.add(o.obj)
                return o

            elif cur is o:
                # was discovered while this rehash
                return o

            else:
                # remove this and replace it with an existing value
                if worklist is not None:
                    worklist.extend(dep.obj for dep in n.dependsOn)
                    worklist.append(cur.obj)
                b.replaceOutput(o, cur, False)
                disconnectAllInputs(n, [])
                removed.add(n)
                return cur
        else:
            # a node which is not subject of a rehash
            seen.add(n)
            return o

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx,
              worklist: Optional[UniqList[HlsNetNode]]=None,
              removed: Optional[Set[HlsNetNode]]=None):
        """
        :note: worklist and removed set can be used to track which nodes were changed and removed
        """
        b: HlsNetlistBuilder = netlist.builder
        b.operatorCache.clear()

        seen: Set[HlsNetNode] = set()

        filterNodes = False
        if removed is None:
            filterNodes = True
            removed = set()

        for n in netlist.iterAllNodes():
            # for each node walk all unseen predecessor nodes and substitute nodes with previously known equivalent node
            n: HlsNetNode
            if n in seen or n in removed:
                continue
            for o in n._outputs:
                self._rehashExpr(b, o, worklist, seen, removed)

        if filterNodes and removed:
            netlist.nodes[:] = (n for n in netlist.nodes if n not in removed)

