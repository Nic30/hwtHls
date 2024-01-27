from copy import copy
from typing import Set, Dict, Optional, Tuple, Union, Literal, List

from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData, HVoidData, \
    HdlType_isVoid
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.observableList import ObservableList, ObservableListRm
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate


def iterUserObjs(n: HlsNetNode):
    for uses in n.usedBy:
        for u in uses:
            yield u.obj


def iterDepObjs(n: HlsNetNode):
    for dep in n.dependsOn:
        if dep is not None:
            yield dep.obj


def _collectConcatOfVoidTreeInputs(o: HlsNetNodeOut, inputs: List[HlsNetNodeOut], seen:Set[HlsNetNodeOut]):
    if o in seen:
        return True

    seen.add(o)

    duplicitySeen = False
    obj: HlsNetNode = o.obj
    if isinstance(obj, HlsNetNodeOperator) and obj.operator == AllOps.CONCAT:
        t = obj.dependsOn[0]._dtype
        assert HdlType_isVoid(t), obj
        for i in obj.dependsOn:
            duplicitySeen |= _collectConcatOfVoidTreeInputs(i, inputs, seen)
    else:
        inputs.append(o)

    return duplicitySeen


def _collectConcatOfVoidTreeOutputs(o: HlsNetNodeOut):
    for use in o.obj.usedBy[o.out_i]:
        useO = use.obj
        if isinstance(useO, HlsNetNodeOperator) and useO.operator == AllOps.CONCAT:
            yield from _collectConcatOfVoidTreeOutputs(useO._outputs[0])
        else:
            yield use


NodeOrPort = Union[HlsNetNode, HlsNetNodeIn, HlsNetNodeOut]
ReachDict = Dict[NodeOrPort, Set[NodeOrPort]]


class HlsNetlistAnalysisPassReachability(HlsNetlistAnalysisPass):
    """
    This analysis is used to query reachability in netlist.
    It is typically used to query if some nodes are transitively connected or to reconstruct pseudo order of nodes. 
    
    :note: This analysis mostly ignores netlist hierarchy and uses only leaf nodes and ports.
    """

    def __init__(self, netlist:"HlsNetlistCtx", removed: Optional[Set[HlsNetNode]]=None):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self._dataSuccessors: ReachDict = {}
        self._anySuccessors: ReachDict = {}
        self.removed = removed

    def __hash__(self):
        return hash(self.__class__)

    def __eq__(self, other) -> bool:
        return self.__class__ is other.__class__

    @staticmethod
    def _registerNodeInSetDict(n: HlsNetNode, d: ReachDict):
        assert n not in d, n
        for i in n._inputs:
            suc = d[i] = {n, }
            suc.update(o for o in n._outputs)

        d[n] = {o for o in n._outputs}
        for o in n._outputs:
            d[o] = set()

    @classmethod
    def _initSetDict(cls, netlist:"HlsNetlistCtx", removed: Optional[Set[HlsNetNode]]) -> ReachDict:
        d: ReachDict = {}
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if removed is not None and n in removed:
                continue
            cls._registerNodeInSetDict(n, d)

        return d

    @staticmethod
    def _flattenNodeOrPort(p: NodeOrPort) -> NodeOrPort:
        while True:
            if isinstance(p, HlsNetNodeIn):
                if isinstance(p.obj, HlsNetNodeAggregate):
                    p = p.obj._inputsInside[p.in_i]._outputs[0]
                else:
                    return p
            elif isinstance(p, HlsNetNodeOut):
                if isinstance(p.obj, HlsNetNodeAggregate):
                    p = p.obj._outputsInside[p.out_i]._inputs[0]
                else:
                    return p
            else:
                assert isinstance(p, HlsNetNode) and not isinstance(p, HlsNetNodeAggregate), p
                return p

    def doesReachToPorts(self, src: NodeOrPort, ports: List[HlsNetNodeOut]):
        for p in ports:
            if self.doesReachTo(src, p):
                return True
        return False

    def doesReachTo(self, src:NodeOrPort, dst:NodeOrPort):
        src = self._flattenNodeOrPort(src)
        dst = self._flattenNodeOrPort(dst)
        sucs = self._anySuccessors[src]
        return dst in sucs

    def doesReachToControl(self, src:HlsNetNode, dst:HlsNetNodeExplicitSync):
        src = self._flattenNodeOrPort(src)
        dst = self._flattenNodeOrPort(dst)
        sucs = self._anySuccessors[src]
        for i in (dst.extraCond, dst.skipWhen):
            if i is not None and i in sucs:
                return True

        return False
        # return src in self._controlPredecessors[dst]

    def doesReachToData(self, src:HlsNetNode, dst:HlsNetNode):
        src = self._flattenNodeOrPort(src)
        dst = self._flattenNodeOrPort(dst)
        return dst in self._dataSuccessors[src]

    def doesUseControlOf(self, n: HlsNetNodeExplicitSync, user: HlsNetNode):
        if isinstance(n, HlsNetNodeRead) and n._validNB is not None:
            sucs = self._anySuccessors[n._validNB]
            return user in sucs

        return False
        # return user in self._controlSuccessors[n]

    def getDirectDataSuccessors(self, n: HlsNetNodeExplicitSync) -> UniqList[HlsNetNodeExplicitSync]:
        """
        Use IO cluster core to iterate HlsNetNodeExplicitSync successor nodes.

        :attention: Expects that HlsNetlistPassMoveExplicitSyncOutOfDataAndAddVoidDataLinks and HlsNetlistPassExplicitSyncDataToOrdering to be applied before
        """
        assert isinstance(n, HlsNetNodeExplicitSync), n
        found: UniqList[HlsNetNodeExplicitSync] = UniqList()
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
                    assert isinstance(obj, HlsNetNodeOperator) and obj.operator == AllOps.CONCAT, obj
                    for user in _collectConcatOfVoidTreeOutputs(o):
                        assert isinstance(user.obj, HlsNetNodeExplicitSync), (n, user.obj)
                        found.append(user.obj)

        return found

    def getDirectDataPredecessors(self, n: HlsNetNodeExplicitSync) -> UniqList[HlsNetNodeExplicitSync]:
        """
        Use IO cluster core to iterate HlsNetNodeExplicitSync successor nodes.

        :attention: Expects some passes to be applied before :see:`~.HlsNetlistAnalysisPassReachability.getDirectDataSuccessors`
        """
        assert isinstance(n, HlsNetNodeExplicitSync), n
        found: UniqList[HlsNetNodeExplicitSync] = UniqList()
        orderingPorts = n.iterOrderingInputs()
        if n.__class__ is HlsNetNodeExplicitSync and HdlType_isVoid(n._outputs[0]._dtype):
            orderingPorts = (n._inputs[0], *orderingPorts)

        for i in orderingPorts:
            dep = n.dependsOn[i.in_i]
            if dep._dtype == HVoidData:
                obj = dep.obj
                if isinstance(obj, HlsNetNodeExplicitSync):
                    found.append(obj)
                elif isinstance(obj, HlsNetNodeConst):
                    continue
                else:
                    assert isinstance(obj, HlsNetNodeOperator) and obj.operator == AllOps.CONCAT, obj
                    _found = UniqList()
                    _collectConcatOfVoidTreeInputs(dep, _found, set())
                    for o in _found:
                        if not isinstance(o.obj, HlsNetNodeConst):
                            found.append(o.obj)

        return found

    def hasControlPredecessor(self, n: HlsNetNode):
        raise NotImplementedError()
        return bool(self._controlPredecessors[n])

    def _beforeNodeAddedListener(self, _, parentList: ObservableList[HlsNetNode], index: Union[slice, int], val: Union[HlsNetNode, Literal[ObservableListRm]]):
        if isinstance(val, HlsNetNode):
            val.dependsOn._setObserver(self._beforeInputDriveUpdate, val)
            for d in (self._dataSuccessors, self._anySuccessors):
                self._registerNodeInSetDict(val, d)

    def _beforeInputDriveUpdate(self, n: HlsNetNode,
                                parentList: ObservableList[HlsNetNodeOut],
                                index: Union[slice, int],
                                val: Union[HlsNetNodeOut, Literal[ObservableListRm]]):
        inp = n._inputs[index]
        try:
            curDep = n.dependsOn[index]
        except IndexError:
            curDep = None

        if val is ObservableListRm or val is None:
            if isinstance(index, int):
                _len = len(n.dependsOn)
                isAppend = index == _len
                if isAppend:
                    assert val is None, val
                    self._anySuccessors[inp] = set()
                    self._dataSuccessors[inp] = set()

                if curDep is not None:
                    if index < _len:
                        list.__setitem__(n.dependsOn, index, None)
                    elif isAppend:
                        list.append(n.dependsOn, None)
                    else:
                        raise IndexError(index)

                    # update curDep successors sets after we removed the use in inp port
                    self._linkDiscard(curDep, inp)

                    if isAppend:
                        list.pop(n.dependsOn)  # rm temporarily added item

                if val is ObservableListRm:
                    # remove input from internal dictionaries
                    for d in (self._dataSuccessors, self._anySuccessors):
                        d.pop(inp)
            else:
                raise NotImplementedError(n, index, val)
        else:
            if isinstance(index, int):
                if curDep is val:
                    return

                _len = len(n.dependsOn)
                isAppend = index == _len
                if index < _len:
                    list.__setitem__(n.dependsOn, index, val)
                elif isAppend:
                    list.append(n.dependsOn, val)
                else:
                    raise IndexError(index)

                if curDep is not None:
                    assert inp not in curDep.obj.usedBy[curDep.out_i], (curDep, "->", inp, "usedBy should be updated before dependsOn")
                    self._linkDiscard(curDep, inp)
                val.obj.usedBy[val.out_i].append(inp)

                if isAppend:
                    self._anySuccessors[inp] = set()
                    self._dataSuccessors[inp] = set()

                self._updateAfterLinkAdd(val, inp)
                tmp = val.obj.usedBy[val.out_i].pop()
                assert tmp is inp, (tmp, inp)
                if isAppend:
                    list.pop(n.dependsOn)  # remove temporal added item

            else:
                raise NotImplementedError(n, index, val)

    def _beforeOutputUpdate(self, n: HlsNetNode,
                            parentList: ObservableList[HlsNetNodeOut],
                            index: Union[slice, int],
                            val: Union[HlsNetNodeOut, Literal[ObservableListRm]]):
        if val is ObservableListRm:
            outp = n._outputs[index]
            for d in (self._dataSuccessors, self._anySuccessors):
                sucs = d.pop(outp)
                assert not sucs, (outp, "Port must not be connected before removing", sucs)
        else:
            _len = len(n._outputs)
            isAppend = index == _len
            if isAppend:
                outp = val
                self._anySuccessors[outp] = set()
                self._dataSuccessors[outp] = set()
                self._propagateSuccessor(outp, n, self._anySuccessors, False)
                if not HdlType_isNonData(outp._dtype):
                    self._propagateSuccessor(outp, n, self._dataSuccessors, True)
            else:
                raise NotImplementedError(n, index, val)

    def _updateAfterLinkAdd(self, o: HlsNetNodeOut, i: HlsNetNodeIn):
        o = self._flattenNodeOrPort(o)
        self._propagateSuccessorAddMany(o, self._anySuccessors, False)
        if not HdlType_isNonData(o._dtype):
            self._propagateSuccessorAddMany(o, self._dataSuccessors, True)

    def _linkDiscard(self, o: HlsNetNodeOut, i:HlsNetNodeIn):
        self._propagateSuccessorRemove(o, i, self._anySuccessors, False)
        if not HdlType_isNonData(o._dtype):
            self._propagateSuccessorRemove(o, i, self._dataSuccessors, True)

    @classmethod
    def _propagateSuccessorAddMany(cls, updatedO: HlsNetNodeOut,
                           dictToUpdate: Dict[NodeOrPort, Set[Tuple[NodeOrPort, bool]]],
                           ommitNonData: bool):
        """
        :attention: updatedO must be flattened (not a port of HlsNetNodeAggregate)
        """
        curSucc = dictToUpdate.get(updatedO, None)
        if curSucc is None:
            # this is newly added output port
            dictToUpdate[updatedO.obj].add(updatedO)
            dictToUpdate[updatedO] = set()
            sucToUpdate = updatedO.obj.usedBy[updatedO.out_i]
        else:

            realSucc = set()
            for u in updatedO.obj.usedBy[updatedO.out_i]:
                u = cls._flattenNodeOrPort(u)
                realSucc.update(dictToUpdate[u])  # KeyError means that the node is not registered in this analysis

            sucToUpdate = realSucc.difference(curSucc)

        for newSuc in sucToUpdate:
            cls._propagateSuccessor(newSuc, updatedO, dictToUpdate, ommitNonData)

    @classmethod
    def _propagateSuccessor(cls, newSuc: NodeOrPort,
                            beginOfPropagation: NodeOrPort,
                            dictToUpdate: Dict[NodeOrPort, Set[Tuple[NodeOrPort, bool]]],
                            ommitNonData: bool):
        """
        :attention: newSuc, beginOfPropagation must be flattened (not a port of HlsNetNodeAggregate)
        """
        # startingNode = sucO.obj
        toSearch: UniqList[NodeOrPort] = UniqList((beginOfPropagation,))
        while toSearch:
            nodeOrPort = toSearch.pop()

            if nodeOrPort is not newSuc:
                curSuccessors = dictToUpdate[nodeOrPort]

                if newSuc in curSuccessors:
                    # end of propagation because suc is already marked as a successor
                    continue
                else:
                    curSuccessors.add(newSuc)

            if isinstance(nodeOrPort, HlsNetNodeIn):
                # walk from input to connected output of other node
                dep = nodeOrPort.obj.dependsOn[nodeOrPort.in_i]
                if dep is None:
                    continue
                if ommitNonData and HdlType_isNonData(dep._dtype):
                    continue
                dep = cls._flattenNodeOrPort(dep)
                toSearch.append(dep)

            elif isinstance(nodeOrPort, HlsNetNodeOut):
                # walk from output node to node itself
                if isinstance(nodeOrPort.obj, HlsNetNodeAggregate):
                    aggregatePort = nodeOrPort.obj._outputsInside[nodeOrPort.out_i]
                    toSearch.append(aggregatePort)

                else:
                    toSearch.append(nodeOrPort.obj)

            else:
                # walk from node to its inputs
                toSearch.extend(i for i in nodeOrPort._inputs)

    @classmethod
    def _propagateSuccessorRemove(cls,
                                  o: HlsNetNodeOut,
                                  removedI: HlsNetNodeIn,
                                  dictToUpdate: Dict[NodeOrPort, Set[Tuple[NodeOrPort, bool]]],
                                  ommitNonData: bool):
        """
        :attention: o, removedI must be flattened (not a port of HlsNetNodeAggregate)
        """
        toSearch: UniqList[NodeOrPort] = UniqList((o,))
        while toSearch:
            nodeOrPort = toSearch.pop()
            curSuccessors = dictToUpdate[nodeOrPort]

            if isinstance(nodeOrPort, HlsNetNodeIn):
                # walk from input to connected output of other node
                newSuccessors = dictToUpdate[nodeOrPort.obj]
                if newSuccessors.symmetric_difference(curSuccessors) != {nodeOrPort.obj, }:
                    continue
                else:
                    d = dictToUpdate[nodeOrPort] = copy(newSuccessors)
                    d.add(nodeOrPort.obj)

                dep = nodeOrPort.obj.dependsOn[nodeOrPort.in_i]
                if dep is None or (ommitNonData and HdlType_isNonData(dep._dtype)):
                    continue

                toSearch.append(dep)

            elif isinstance(nodeOrPort, HlsNetNodeOut):
                # walk from output node to node itself
                newSuccessors = set()
                for u in nodeOrPort.obj.usedBy[nodeOrPort.out_i]:
                    newSuccessors.add(u)
                    sucs = dictToUpdate.get(u, None)
                    if sucs is None:
                        uses = set()
                        uses.update(dictToUpdate[u.obj])
                        uses.add(u)
                        sucs = dictToUpdate[u] = uses
                    newSuccessors.update(sucs)

                if newSuccessors == curSuccessors:
                    continue
                else:
                    dictToUpdate[nodeOrPort] = newSuccessors

                toSearch.append(nodeOrPort.obj)

            else:
                newSuccessors = set()
                for o in nodeOrPort._outputs:
                    sucs = dictToUpdate.get(o, None)
                    if sucs is None:
                        uses = set()
                        for u in nodeOrPort.usedBy[o.out_i]:
                            uses.update(dictToUpdate[u])
                            uses.add(u)
                        sucs = dictToUpdate[o] = uses

                    newSuccessors.update(sucs)

                if newSuccessors == curSuccessors:
                    continue
                else:
                    dictToUpdate[nodeOrPort] = newSuccessors

                # walk from node to its inputs
                for i in nodeOrPort._inputs:
                    toSearch.append(i)

    @staticmethod
    def _isValidNB(o: HlsNetNodeOut):
        return isinstance(o.obj, HlsNetNodeRead) and o is o.obj._validNB

    @staticmethod
    def _isExtraCondOrSkipWhen(i: HlsNetNodeIn):
        n = i.obj
        return isinstance(n, HlsNetNodeExplicitSync) and (i is n.extraCond or i is n.skipWhen)

    # @classmethod
    # def _getDirectDataPredecessorsRawAddToSearch(cls, n: HlsNetNode, toSearch: UniqList[HlsNetNode]):
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
    def _getDirectDataPredecessorsRaw(cls, toSearch: UniqList[HlsNetNode], seen: Set[HlsNetNode]) -> UniqList[HlsNetNodeExplicitSync]:
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
    def _getDirectDataPredecessorsRawAnyData(cls, toSearch: UniqList[HlsNetNode],
                                             seen: Set[HlsNetNode],
                                             blacklist: Set[HlsNetNode]) -> UniqList[HlsNetNodeExplicitSync]:
        """
        Simplified version of :meth:`~._getDirectDataPredecessorsRaw` which uses node blacklist instead of check for specific ports.
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
                if depObj in blacklist:
                    continue
                yield depObj
                toSearch.append(dep.obj)

    # @staticmethod
    # def _getDirectDataSuccessorsRawAddToSearch(n: HlsNetNode, toSearch: UniqList[HlsNetNode]):
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
    def _getDirectDataSuccessorsRaw(cls, toSearch: UniqList[HlsNetNode], seen: Set[HlsNetNode]) -> UniqList[HlsNetNodeExplicitSync]:
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
                                           toSearch: UniqList[HlsNetNode],
                                           seen: Set[HlsNetNode],
                                           blacklist: Set[HlsNetNode]) -> UniqList[HlsNetNodeExplicitSync]:
        """
        Simplified version of :meth:`~._getDirectDataSuccessorsRaw` which uses node blacklist instead of check for specific ports.
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
                    if uObj in blacklist:
                        continue
                    yield uObj
                    toSearch.append(uObj)

    def run(self):
        assert not  self._dataSuccessors
        assert not self._anySuccessors
        removed = self.removed
        dataSuccessors = self._dataSuccessors = self._initSetDict(self.netlist, removed)
        anySuccessors = self._anySuccessors = self._initSetDict(self.netlist, removed)

        for n in self.netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if removed is not None and n in removed:
                continue

            for i in n._inputs:
                i: HlsNetNodeIn
                dep = n.dependsOn[i.in_i]
                if dep is None:
                    continue

                for o in n._outputs:
                    o: HlsNetNodeOut
                    self._propagateSuccessor(o, dep, dataSuccessors, True)
                    self._propagateSuccessor(o, dep, anySuccessors, False)

                for port in (i, n):
                    self._propagateSuccessor(port, dep, dataSuccessors, True)
                    self._propagateSuccessor(port, dep, anySuccessors, False)
