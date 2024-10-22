from typing import List, Set, Callable

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.hdlTypeVoid import HVoidData, HdlType_isNonData
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.transformation.simplifyExpr.concat import _collectConcatOfVoidTreeOutputs, \
    _collectConcatOfVoidTreeInputs


class HlsNetlistAnalysisPassIoOrdering(HlsNetlistAnalysisPass):

    @staticmethod
    def getDirectDataSuccessors(n: HlsNetNodeExplicitSync) -> SetList[HlsNetNodeExplicitSync]:
        """
        Use IO cluster core to iterate HlsNetNodeExplicitSync successor nodes.

        :attention: Expects that HlsNetlistPassMoveExplicitSyncOutOfDataAndAddVoidDataLinks and HlsNetlistPassExplicitSyncDataToOrdering to be applied before
        """
        assert isinstance(n, HlsNetNodeExplicitSync), n
        found: SetList[HlsNetNodeExplicitSync] = SetList()
        voidDataOuts = []
        if n._outputs and n._outputs[0]._dtype == HVoidData and n._outputs[0] is not n._dataVoidOut:
            voidDataOuts.append(n._outputs[0])

        if n._dataVoidOut is not None:
            voidDataOuts.append(n._dataVoidOut)

        for o in voidDataOuts:
            for user in n.usedBy[o.out_i]:
                obj = user.obj
                if isinstance(obj, HlsNetNodeExplicitSync):
                    found.append(obj)
                else:
                    assert isinstance(obj, HlsNetNodeOperator) and obj.operator == HwtOps.CONCAT, obj
                    for user in _collectConcatOfVoidTreeOutputs(o):
                        assert isinstance(user.obj, HlsNetNodeExplicitSync), (n, user.obj)
                        found.append(user.obj)

        return found

    @staticmethod
    def getDirectDataPredecessors(n: HlsNetNodeExplicitSync) -> SetList[HlsNetNodeExplicitSync]:
        """
        Use IO cluster core to iterate HlsNetNodeExplicitSync successor nodes.

        :attention: Expects some passes to be applied before :see:`~.HlsNetlistAnalysisPassReachability.getDirectDataSuccessors`
        """
        assert isinstance(n, HlsNetNodeExplicitSync), n
        found: SetList[HlsNetNodeExplicitSync] = SetList()
        orderingPorts = n.iterOrderingInputs()
        assert n.__class__ is not HlsNetNodeExplicitSync, "HlsNetNodeExplicitSync is just abstract class"
        # if n.__class__ is HlsNetNodeExplicitSync and HdlType_isVoid(n._outputs[0]._dtype):
        #    orderingPorts = (n._inputs[0], *orderingPorts)

        for i in orderingPorts:
            dep = n.dependsOn[i.in_i]
            if dep._dtype == HVoidData:
                obj = dep.obj
                if isinstance(obj, HlsNetNodeExplicitSync):
                    found.append(obj)
                elif isinstance(obj, HlsNetNodeConst):
                    continue
                else:
                    assert isinstance(obj, HlsNetNodeOperator) and obj.operator == HwtOps.CONCAT, obj
                    _found = SetList()
                    _collectConcatOfVoidTreeInputs(dep, _found, set())
                    for o in _found:
                        if not isinstance(o.obj, HlsNetNodeConst):
                            found.append(o.obj)

        return found

    # @staticmethod
    # def _getDirectDataSuccessorsRawAddToSearch(n: HlsNetNode, toSearch: SetList[HlsNetNode]):
    #    if isinstance(n, HlsNetNodeExplicitSync):
    #        if isinstance(n, HlsNetNodeRead):
    #            validNB = n._validNB
    #        else:
    #            validNB = None
    #        for o, uses in zip(n._outputs, n.usedBy):
    #            if o is validNB:
    #                # skipping control signals
    #                continue
    #            # if HdlType_isNonData(o._dtype):
    #            #    continue
    #            for u in uses:
    #                toSearch.append(u.obj)
    #    else:
    #        for uses in n.usedBy:
    #            toSearch.extend(u.obj for u in uses)
    #
    @classmethod
    def _getDirectDataSuccessorsRaw(cls, toSearch: SetList[HlsNetNode], seen: Set[HlsNetNode]) -> SetList[HlsNetNodeExplicitSync]:
        """
        BFS search for HlsNetNodeExplicitSync successor nodes, but do not cross these instances while searching
        """
        while toSearch:
            n = toSearch.pop()

            if n in seen:
                continue
            seen.add(n)
            assert not isinstance(n, HlsNetNodeAggregate), n

            if isinstance(n, HlsNetNodeRead):
                validNb = n._validNB
            else:
                validNb = None

            for o, uses in zip(n._outputs, n.usedBy):
                if HdlType_isNonData(o._dtype) or o is validNb:
                    continue
                for u in uses:
                    if cls._isExtraCondOrSkipWhen(u):
                        continue
                    u = cls._flattenNodeOrPort(u)
                    uObj = u.obj
                    yield uObj
                    if not isinstance(uObj, HlsNetNodeExplicitSync):
                        toSearch.append(uObj)

    @classmethod
    def _getDirectDataSuccessorsRawAnyData(cls,
                                           toSearch: SetList[HlsNetNode],
                                           seen: Set[HlsNetNode],
                                           searchEndPredicateFn: Callable[[HlsNetNode], bool]) -> SetList[HlsNetNodeExplicitSync]:
        """
        Simplified version of :meth:`~._getDirectDataSuccessorsRaw` which uses node searchEndPredicateFn instead of check for specific ports.
        """

        while toSearch:
            n = toSearch.pop()

            if n in seen:
                continue
            seen.add(n)
            assert not isinstance(n, HlsNetNodeAggregate), n

            for o, uses in zip(n._outputs, n.usedBy):
                if HdlType_isNonData(o._dtype):
                    continue

                for u in uses:
                    u = cls._flattenNodeOrPort(u)
                    uObj = u.obj
                    if searchEndPredicateFn(uObj):
                        continue
                    yield uObj
                    toSearch.append(uObj)

    # @classmethod
    # def _getDirectDataPredecessorsRawAddToSearch(cls, n: HlsNetNode, toSearch: SetList[HlsNetNode]):
    #    if isinstance(n, HlsNetNodeExplicitSync):
    #        for i, dep in zip(n._inputs, n.dependsOn):
    #            if dep is None or i is n.extraCond or i is n.skipWhen or cls._isValidNB(dep):
    #                continue
    #            # if HdlType_isNonData(dep._dtype):
    #            #    continue
    #            toSearch.append(dep.obj)
    #    else:
    #        if isinstance(n, HlsNetNode):
    #            toSearch.extend(dep.obj
    #                            for dep in n.dependsOn
    #                            if dep is not None and not cls._isValidNB(dep))
    #
    #        elif isinstance(n, HlsNetNodeIn):
    #            dep = n.obj.dependsOn[n.in_i]
    #            if dep is not None:  # and HdlType_isNonData(dep._dtype):
    #                if cls._isValidNB(dep):
    #                    return
    #                toSearch.append(dep.obj)
    #        else:
    #            assert isinstance(n, HlsNetNodeOut), n
    #            if cls._isValidNB(n):
    #                return
    #
    #            toSearch.append(n.obj)

    @classmethod
    def _getDirectDataPredecessorsRaw(cls, toSearch: SetList[HlsNetNode], seen: Set[HlsNetNode]) -> SetList[HlsNetNodeExplicitSync]:
        """
        BFS search for HlsNetNodeExplicitSync predecessor nodes, but do not cross these instances while searching
        """
        while toSearch:
            n = toSearch.pop()
            if n in seen:
                continue
            seen.add(n)
            assert not isinstance(n, HlsNetNodeAggregate), n

            nIsSync = isinstance(n, HlsNetNodeExplicitSync)
            if nIsSync:
                ec = n.extraCond
                sw = n.skipWhen
            else:
                ec = None
                sw = None
            for i, dep in zip(n._inputs, n.dependsOn):
                if i is ec or i is sw or dep is None or HdlType_isNonData(dep._dtype) or cls._isValidNB(dep):
                    continue
                dep = cls._flattenNodeOrPort(dep)
                depObj = dep.obj
                yield depObj
                if not isinstance(depObj, HlsNetNodeExplicitSync):
                    toSearch.append(dep.obj)

    @classmethod
    def _getDirectDataPredecessorsRawAnyData(cls, toSearch: SetList[HlsNetNode],
                                             seen: Set[HlsNetNode],
                                             searchEndPredicateFn: Callable[[HlsNetNode], bool]) -> SetList[HlsNetNodeExplicitSync]:
        """
        Simplified version of :meth:`~._getDirectDataPredecessorsRaw` which uses searchEndPredicateFn instead of check for specific ports.
        """
        while toSearch:
            n = toSearch.pop()
            if n in seen:
                continue
            assert not isinstance(n, HlsNetNodeAggregate), n

            seen.add(n)
            for dep in n.dependsOn:
                if dep is None or HdlType_isNonData(dep._dtype):
                    continue
                dep = cls._flattenNodeOrPort(dep)
                depObj = dep.obj
                if searchEndPredicateFn(depObj):
                    continue
                yield depObj
                toSearch.append(dep.obj)
