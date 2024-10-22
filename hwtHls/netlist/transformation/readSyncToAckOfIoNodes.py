from typing import Union, Optional, List

from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.syncUtils import HwIO_getSyncTuple
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE


class HlsNetlistPassReadSyncToAckOfIoNodes(HlsNetlistPass):

    def _getAckOfIoNode(self, n: Union[HlsNetNodeRead, HlsNetNodeWrite]) -> Optional[HlsNetNodeOut]:
        if isinstance(n, HlsNetNodeRead):
            # drop this for input which does not have vld signal
            n: HlsNetNodeRead

            vld, _ = HwIO_getSyncTuple(n.src)
            if isinstance(vld, (int, HBitsConst)):
                # if IO interface does not use any sync replace this with 1
                assert vld == 1, (n, vld)
                return None
            else:
                return n.getValidNB()

        else:
            assert isinstance(n, HlsNetNodeWrite), n
            # drop this for output which does not have rd signal
            _, rd = HwIO_getSyncTuple(n.dst)
            if isinstance(rd, (int, HBitsConst)):
                # if IO interface does not use any sync replace this with 1
                assert rd == 1, (n, rd)
                return None
            elif n._ready:
                return n._ready
            else:
                n._addReady()
                return n._ready

    def _collectSyncValidFromExpr(self, o: HlsNetNodeOut) -> Optional[HlsNetNodeOut]:
        """
        :return: an output of node which is an expression which combines all validity ports of every predecessor io else None if there is not any
        """
        n = o.obj
        _collectSyncValidFromExpr = self._collectSyncValidFromExpr
        builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
        if isinstance(n, HlsNetNodeOperator):
            if isinstance(n, HlsNetNodeMux) and len(n._inputs) > 1:
                n: HlsNetNodeMux
                is1b = n._outputs[0]._dtype.bit_length() == 1
                # w = n._outputs[0]._dtype.bit_length()
                # Check only (cond & val)* | else val
                prevConditions_n: List[HlsNetNodeOut] = []
                result = []
                for v, c in n._iterValueConditionDriverPairs():
                    if c is None:
                        if prevConditions_n:
                            if not is1b:
                                v = _collectSyncValidFromExpr(v)
                            srcVld = builder.buildAndVariadic(prevConditions_n + [v, ])
                            _res = _collectSyncValidFromExpr(srcVld)
                        else:
                            _res = _collectSyncValidFromExpr(v)
                    else:
                        # all previous mux conditions 0 this condition 1 and
                        if not is1b:
                            v = _collectSyncValidFromExpr(v)
                        srcVld = builder.buildAndVariadic(prevConditions_n + [c, v])
                        _res = _collectSyncValidFromExpr(srcVld)
                        c_n = builder.buildNot(c)
                        prevConditions_n.append(c_n)
                    result.append(_res)
                assert result, "Must not be empty because MUX has to have operands"
                return builder.buildOrVariadic(result)

            else:
                result = SetList()
                for dep in n.dependsOn:
                    _res = _collectSyncValidFromExpr(dep)
                    if _res is not None:
                        result.append(_res)
                if not result:
                    return None
                elif len(result) == 1:
                    return result[0]
                else:
                    return builder.buildAndVariadic(result)

        elif isinstance(n, HlsNetNodeExplicitSync):
            if o is n._outputs[0]:
                if n.__class__ is HlsNetNodeExplicitSync:
                    return _collectSyncValidFromExpr(n.dependsOn[0])
                else:
                    # read only sync of this node
                    return self._getAckOfIoNode(n)

            elif o is n._valid or o is n._validNB:
                return o
            else:
                raise NotImplementedError(o)

        elif not n._inputs:
            return None
        elif isinstance(n, HlsNetNodeReadSync):
            return o  # return output of HlsNetNodeReadSync which will be replaced later
        else:
            raise NotImplementedError(o)

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        worklistPlaceholder = []
        removed = set()
        for elm, nodes in netlist.iterNodesFlatWithParentByType(HlsNetNodeReadSync):
            builder: HlsNetlistBuilder = elm.getHlsNetlistBuilder()
            for n in nodes:
                removed.add(n)
                # rm this if the source object does not have sync
                dep = n.dependsOn[0].obj
                if isinstance(dep, HlsNetNodeExplicitSync) and dep._associatedReadSync is n:
                    dep._associatedReadSync = None

                # replace with the expression made from
                origDepO = n.dependsOn[0]

                newDep = self._collectSyncValidFromExpr(origDepO)
                if newDep is None:
                    newDep = builder.buildConstBit(1)
                replaceOperatorNodeWith(n, newDep, worklistPlaceholder, removed)

            if removed:
                # update because nodes list may have listeners set
                elm.filterNodesUsingSet(removed)
                assert not removed

        if removed:
            return PreservedAnalysisSet.preserveReachablity()
        else:
            return PreservedAnalysisSet.preserveAll()
