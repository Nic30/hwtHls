from copy import copy
from typing import Set, Dict, Tuple, Union, Literal, List

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.observableList import ObservableList, ObservableListRm
from hwtHls.netlist.scheduler.clk_math import beginOfNextClk, beginOfClk


def iterUserObjs(n: HlsNetNode):
    for uses in n.usedBy:
        for u in uses:
            yield u.obj


def iterDepObjs(n: HlsNetNode):
    for dep in n.dependsOn:
        if dep is not None:
            yield dep.obj


NodeOrPort = Union[HlsNetNode, HlsNetNodeIn, HlsNetNodeOut]
ReachDict = Dict[NodeOrPort, Set[NodeOrPort]]


class HlsNetlistAnalysisPassReachability(HlsNetlistAnalysisPass):
    """
    This analysis is used to query reachability in netlist.
    It is typically used to query if some nodes are transitively connected or to reconstruct pseudo order of nodes. 
    
    :note: This analysis mostly ignores netlist hierarchy and uses only leaf nodes and ports.
    """

    def __init__(self):
        super(HlsNetlistAnalysisPassReachability, self).__init__()
        self._successors: ReachDict = {}
        self.ommitNonData = False
        self.singleClockOnly = False

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
    def _initSetDict(cls, netlist:"HlsNetlistCtx") -> ReachDict:
        d: ReachDict = {}
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if n._isMarkedRemoved:
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
        sucs = self._successors[src]
        return dst in sucs

    def _beforeNodeAddedListener(self, _, parentList: ObservableList[HlsNetNode], index: Union[slice, int], val: Union[HlsNetNode, Literal[ObservableListRm]]):
        if isinstance(val, HlsNetNode):
            val.dependsOn._setObserver(self._beforeInputDriveUpdate, val)
            self._registerNodeInSetDict(val, self._successors)

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
                    self._successors[inp] = set()

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
                    self._successors.pop(inp)
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
                    self._successors[inp] = set()

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
            sucs = self._successors.pop(outp)
            assert not sucs, (outp, "Port must not be connected before removing", sucs)
        else:
            _len = len(n._outputs)
            isAppend = index == _len
            if isAppend:
                outp = val
                self._successors[outp] = set()
                if not self.ommitNonData or not HdlType_isNonData(outp._dtype):
                    self._propagateSuccessor(outp, n, self._successors, self.ommitNonData, self.singleClockOnly)
            else:
                raise NotImplementedError(n, index, val)

    def _updateAfterLinkAdd(self, o: HlsNetNodeOut, i: HlsNetNodeIn):
        assert not self.ommitNonData
        o = self._flattenNodeOrPort(o)
        self._propagateSuccessorAddMany(o, self._successors, False, self.singleClockOnly)

    def _linkDiscard(self, o: HlsNetNodeOut, i:HlsNetNodeIn):
        assert not self.ommitNonData
        self._propagateSuccessorRemove(o, i, self._successors, False, self.singleClockOnly)

    @classmethod
    def _propagateSuccessorAddMany(cls, updatedO: HlsNetNodeOut,
                           dictToUpdate: Dict[NodeOrPort, Set[Tuple[NodeOrPort, bool]]],
                           singleClockOnly:bool):
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
            cls._propagateSuccessor(newSuc, updatedO, dictToUpdate, singleClockOnly)

    @classmethod
    def _propagateSuccessor(cls, newSuc: NodeOrPort,
                            beginOfPropagation: NodeOrPort,
                            dictToUpdate: Dict[NodeOrPort, Set[Tuple[NodeOrPort, bool]]],
                            ommitNonData: bool,
                            singleClockOnly:bool):
        """
        :attention: newSuc, beginOfPropagation must be flattened (not a port of HlsNetNodeAggregate)
        :param ommitNonData: if true connections of HdlTypeVoid type are ignored
        :param singleClockOnly: if true connections crossing clock window boundary are ignored
        """
        if singleClockOnly:
            if isinstance(newSuc, HlsNetNode):
                t = newSuc.scheduledZero
                clkPeriod = newSuc.netlist.normalizedClkPeriod
            elif isinstance(newSuc, HlsNetNodeOut):
                t = newSuc.obj.scheduledOut[newSuc.out_i]
                clkPeriod = newSuc.obj.netlist.normalizedClkPeriod
            else:
                assert isinstance(newSuc, HlsNetNodeIn)
                t = newSuc.obj.scheduledIn[newSuc.in_i]
                clkPeriod = newSuc.obj.netlist.normalizedClkPeriod

            timeLimitBegin = beginOfClk(t, clkPeriod)
            timeLimitEnd = beginOfNextClk(t, clkPeriod)
        else:
            timeLimitBegin = None
            timeLimitEnd = None

        # startingNode = sucO.obj
        toSearch: SetList[NodeOrPort] = SetList((beginOfPropagation,))
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
                if timeLimitBegin is not None and dep.obj.scheduledOut[dep.out_i] < timeLimitBegin:
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
                if timeLimitBegin is None:
                    toSearch.extend(nodeOrPort._inputs)
                else:
                    for in_, time in zip(nodeOrPort._inputs, nodeOrPort.scheduledIn):
                        if time < timeLimitBegin or time >= timeLimitEnd:
                            continue
                        toSearch.append(in_)

    @staticmethod
    def _propagateSuccessorRemove(o: HlsNetNodeOut,
                                  removedI: HlsNetNodeIn,
                                  dictToUpdate: Dict[NodeOrPort, Set[Tuple[NodeOrPort, bool]]],
                                  ommitNonData: bool):
        """
        :attention: o, removedI must be flattened (not a port of HlsNetNodeAggregate)
        """
        toSearch: SetList[NodeOrPort] = SetList((o,))
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

    def _installNetlistListeners(self, netlist: "HlsNetlistCtx"):
        netlist.setupNetlistListeners(
            self._beforeNodeAddedListener,
            self._beforeInputDriveUpdate,
            self._beforeOutputUpdate)

    @override
    def runOnHlsNetlistImpl(self, netlist: "HlsNetlistCtx"):
        assert not  self._successors
        successors = self._successors = self._initSetDict(netlist)
        ommitNonData = self.ommitNonData
        singleClockOnly = self.singleClockOnly
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if n._isMarkedRemoved:
                continue

            for i, dep in zip(n._inputs, n.dependsOn):
                i: HlsNetNodeIn
                if dep is None:
                    continue
                dep: HlsNetNodeOut
                dep = self._flattenNodeOrPort(dep)

                # make all output of this node a successor of driver of this input
                for o in n._outputs:
                    o: HlsNetNodeOut
                    self._propagateSuccessor(o, dep, successors, ommitNonData, singleClockOnly)

                # make this input node itself a successor of driver of this node
                for port in (i, n):
                    self._propagateSuccessor(port, dep, successors, ommitNonData, singleClockOnly)


class HlsNetlistAnalysisPassReachabilityDataOnly(HlsNetlistAnalysisPassReachability):

    def __init__(self) -> None:
        HlsNetlistAnalysisPassReachability.__init__(self)
        self.ommitNonData = True

    def _updateAfterLinkAdd(self, o: HlsNetNodeOut, i: HlsNetNodeIn):
        o = self._flattenNodeOrPort(o)
        if not HdlType_isNonData(o._dtype):
            self._propagateSuccessorAddMany(o, self._successors, True)

    def _linkDiscard(self, o: HlsNetNodeOut, i:HlsNetNodeIn):
        if not HdlType_isNonData(o._dtype):
            self._propagateSuccessorRemove(o, i, self._successors, True)


class HlsNetlistAnalysisPassReachabilityDataOnlySingleClock(HlsNetlistAnalysisPassReachability):

    def __init__(self):
        HlsNetlistAnalysisPassReachability.__init__(self)
        self.singleClockOnly = True

