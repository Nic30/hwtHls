from typing import Set, Dict, Optional, Tuple, Union, Literal, List

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.observableList import ObservableList, ObservableListRm
from hwtHls.netlist.nodes.orderable import HdlType_isNonData
from copy import copy


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


# [todo] rename to HlsNetlistAnalysisPassReach
class HlsNetlistAnalysisPassSyncDependency(HlsNetlistAnalysisPass):

    def __init__(self, netlist:"HlsNetlistCtx", removed: Optional[Set[HlsNetNode]]=None):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self._dataSuccessors: ReachDict = {}
        self._anySuccessors: ReachDict = {}
        self.removed = removed

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
        for n in netlist.iterAllNodes():
            if removed is not None and n in removed:
                continue
            cls._registerNodeInSetDict(n, d)

        return d
    
    def doesReachToPorts(self, src: NodeOrPort, ports: List[HlsNetNodeOut]):
        for p in ports:
            if self.doesReachTo(src, p):
                return True
        return False
        
    def doesReachTo(self, src:NodeOrPort, dst:NodeOrPort):
        sucs = self._anySuccessors[src]
        return dst in sucs 

    def doesReachToControl(self, src:HlsNetNode, dst:HlsNetNodeExplicitSync):
        sucs = self._anySuccessors[src]
        for i in (dst.extraCond, dst.skipWhen):
            if i is not None and i in sucs:
                return True

        return False
        # return src in self._controlPredecessors[dst] 
    
    def doesReachToData(self, src:HlsNetNodeExplicitSync, dst:HlsNetNode):
        raise NotImplementedError()
        return src in self._dataPredecessors[dst]
    
    def doesUseControlOf(self, n: HlsNetNodeExplicitSync, user: HlsNetNode):
        if isinstance(n, HlsNetNodeRead) and n._validNB is not None:
            sucs = self._anySuccessors[n._validNB]
            return user in sucs

        return False
        # return user in self._controlSuccessors[n]
    
    @staticmethod
    def getDirectDataSuccessors(n: HlsNetNode):
        """
        BFS search for HlsNetNodeExplicitSync successor nodes, but do not cross these instances while searching
        """
        found: UniqList[HlsNetNodeExplicitSync] = UniqList()
        toSearch: HlsNetNode = UniqList()
        seen: Set[HlsNetNode] = set()
        if isinstance(n, HlsNetNodeExplicitSync):
            if isinstance(n, HlsNetNodeRead):
                validNB = n._validNB
            else:
                validNB = None 
            for o, uses in zip(n._outputs, n.usedBy):
                if o is validNB:
                    # skipping control signals
                    continue
                #if HdlType_isNonData(o._dtype):
                #    continue
                for u in uses:
                    toSearch.append(u.obj)
        else:
            for uses in n.usedBy:
                toSearch.extend(u.obj for u in uses)

        while toSearch:
            n = toSearch.pop()
            
            if n in seen:
                continue
            seen.add(n)

            if isinstance(n, HlsNetNodeExplicitSync):
                found.append(n)
                continue
            
            for o, uses in zip(n._outputs, n.usedBy):
                #if HdlType_isNonData(o._dtype):
                #    continue
                for u in uses:
                    toSearch.append(u.obj)
        
        return found

    @staticmethod
    def getDirectDataPredecessors(n: HlsNetNode) -> UniqList[HlsNetNodeExplicitSync]:
        """
        BFS search for HlsNetNodeExplicitSync predecessor nodes, but do not cross these instances while searching
        """
        found: UniqList[HlsNetNodeExplicitSync] = UniqList()
        toSearch: HlsNetNode = UniqList()
        seen: Set[HlsNetNode] = set()
        if isinstance(n, HlsNetNodeExplicitSync):
            for i, dep in zip(n._inputs, n.dependsOn):
                if dep is None or i is n.extraCond or i is n.skipWhen:
                    continue
                #if HdlType_isNonData(dep._dtype):
                #    continue
                toSearch.append(dep.obj)
        else:
            if isinstance(n, HlsNetNode):
                toSearch.extend(dep.obj for dep in n.dependsOn if dep is not None)
            elif isinstance(n, HlsNetNodeIn):
                dep = n.obj.dependsOn[n.in_i]
                    
                if dep is not None: # and HdlType_isNonData(dep._dtype):
                    toSearch.append(dep.obj)
            else:
                assert isinstance(n, HlsNetNodeOut), n
                toSearch.append(n.obj)
            
        while toSearch:
            n = toSearch.pop()
            
            if n in seen:
                continue
            seen.add(n)

            if isinstance(n, HlsNetNodeExplicitSync):
                found.append(n)
                continue

            toSearch.extend(dep.obj for dep in n.dependsOn if dep is not None) # and not HdlType_isNonData(dep._dtype)
        
        return found
    
    def hasControlPredecessor(self, n: HlsNetNode):
        raise NotImplementedError()
        return bool(self._controlPredecessors[n])
        
    def _beforeNodeAddedListener(self, _, parentList: ObservableList[HlsNetNode], index: Union[slice, int], val: Union[HlsNetNode, Literal[ObservableListRm]]):
        if isinstance(val, HlsNetNode):
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

    def _updateAfterLinkAdd(self, o: HlsNetNodeOut, i: HlsNetNodeIn):
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
        curSucc = dictToUpdate.get(updatedO, None)
        if curSucc is None:
            # this is newly added output port
            dictToUpdate[updatedO.obj].add(updatedO)
            dictToUpdate[updatedO] = set()
            sucToUpdate = updatedO.obj.usedBy[updatedO.out_i]
        else:
            
            realSucc = set()
            for u in updatedO.obj.usedBy[updatedO.out_i]:
                realSucc.update(dictToUpdate[u])
        
            sucToUpdate = realSucc.difference(curSucc)
            
        for newSuc in sucToUpdate:
            cls._propagateSuccessor(newSuc, updatedO, dictToUpdate, ommitNonData)
         
    @classmethod
    def _propagateSuccessor(cls, newSuc: NodeOrPort,
                            beginOfPropagation: NodeOrPort,
                            dictToUpdate: Dict[NodeOrPort, Set[Tuple[NodeOrPort, bool]]],
                            ommitNonData: bool):
        # startingNode = sucO.obj
        toSearch: UniqList[NodeOrPort] = UniqList((beginOfPropagation,))
        while toSearch:
            n = toSearch.pop()
            
            if n is not newSuc:
                curSuccessors = dictToUpdate[n]
                if newSuc in curSuccessors:
                    # end of propagation because suc is already marked as a successor
                    continue 
                else:
                    curSuccessors.add(newSuc)
            
            if isinstance(n, HlsNetNodeIn):
                # walk from input to connected output of other node
                dep = n.obj.dependsOn[n.in_i]
                if dep is None or (ommitNonData and HdlType_isNonData(dep._dtype)):
                    continue
                toSearch.append(dep)

            elif isinstance(n, HlsNetNodeOut):
                # walk from output node to node itself
                toSearch.append(n.obj)

            else:
                # walk from node to its inputs
                toSearch.extend(i for i in n._inputs)

    @classmethod
    def _propagateSuccessorRemove(cls,
                                  o: HlsNetNodeOut,
                                  removedI: HlsNetNodeIn,
                                  dictToUpdate: Dict[NodeOrPort, Set[Tuple[NodeOrPort, bool]]],
                                  ommitNonData: bool):
        toSearch: UniqList[NodeOrPort] = UniqList((o,))
        while toSearch:
            n = toSearch.pop()
            curSuccessors = dictToUpdate[n]

            if isinstance(n, HlsNetNodeIn):
                # walk from input to connected output of other node
                newSuccessors = dictToUpdate[n.obj]
                if newSuccessors.symmetric_difference(curSuccessors) != {n.obj, }:
                    continue
                else:
                    d = dictToUpdate[n] = copy(newSuccessors)
                    d.add(n.obj)
 
                dep = n.obj.dependsOn[n.in_i]
                if dep is None or (ommitNonData and HdlType_isNonData(dep._dtype)):
                    continue
                    
                toSearch.append(dep)

            elif isinstance(n, HlsNetNodeOut):
                # walk from output node to node itself
                newSuccessors = set()
                for u in n.obj.usedBy[n.out_i]:
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
                    dictToUpdate[n] = newSuccessors
                
                toSearch.append(n.obj)
                
            else:
                newSuccessors = set()
                for o in n._outputs:
                    sucs = dictToUpdate.get(o, None)
                    if sucs is None:
                        uses = set()
                        for u in n.usedBy[o.out_i]:
                            uses.update(dictToUpdate[u])
                            uses.add(u)
                        sucs = dictToUpdate[o] = uses

                    newSuccessors.update(sucs)

                if newSuccessors == curSuccessors:
                    continue
                else:
                    dictToUpdate[n] = newSuccessors
                
                # walk from node to its inputs
                for i in n._inputs:
                    toSearch.append(i)
        
    def run(self):
        assert not  self._dataSuccessors
        assert not self._anySuccessors
        removed = self.removed
        dataSuccessors = self._dataSuccessors = self._initSetDict(self.netlist, removed)
        anySuccessors = self._anySuccessors = self._initSetDict(self.netlist, removed)

        for n in self.netlist.iterAllNodes():
            if removed is not None and n in removed:
                continue
            
            for i in n._inputs:
                dep = n.dependsOn[i.in_i]
                if dep is None:
                    continue
                for o in n._outputs:
                    self._propagateSuccessor(o, dep, dataSuccessors, True)
                    self._propagateSuccessor(o, dep, anySuccessors, False)
                for x in (i, n):
                    self._propagateSuccessor(x, dep, dataSuccessors, True)
                    self._propagateSuccessor(x, dep, anySuccessors, False)
