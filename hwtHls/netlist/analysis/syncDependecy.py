from copy import copy
from typing import Set, Dict, Optional, Tuple, Union, Literal

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.transformation.simplifyUtils import addAllUsersToWorklist
from hwtHls.netlist.observableList import ObservableList, ObservableListRm


def iterUserObjs(n: HlsNetNode):
    for uses in n.usedBy:
        for u in uses:
            yield u.obj


def iterDepObjs(n: HlsNetNode):
    for dep in n.dependsOn:
        if dep is not None:
            yield dep.obj


class HlsNetlistAnalysisPassSyncDependency(HlsNetlistAnalysisPass):
    """
    Collect dictionaries for IO dependency analysis.
    There are 2 main reasons why this is required.
    
    1. When doing IO analysis all first sync nodes which are accessible in any direction must be taken in account.
    2. When reconnecting something in to some node in DAG we have to be sure that we keep graph DAG and do not create a cycle.
       For this we need to know the dominance relation for every node.
    
    
    :ivar dataPredecessors: HlsNetNodeExplicitSync transitive predecessor set for each node which are dependent through data outputs.
    :ivar dataSuccessors: HlsNetNodeExplicitSync transitive successor set for each node which are dependent on node data outputs.
    :ivar controlPredecessors: HlsNetNodeExplicitSync predecessor set for each node which are dependent through control outputs.
    :ivar controlSuccessors: HlsNetNodeExplicitSync transitive successor set for each node which are dependent on node control outputs.

    :note: directDataPredecessors, directDataSuccessors, directControlPredecessors, directControlSuccessors are similar to previous
        dictionaries but the set contains only first sync nodes on the path.
    :note: ordering is treated as a data and should be optimized in advance
    :note: Ideally we would like to all predecessor and successors transitively for each node for data and control parts of the circuit.
        However this is computationally infeasible and we have to aggregate nodes as much as possible before doing any deep analysis.
    :note: "direct" sets do not need to be subsets of non-direct sets
        this is because direct sets take ordering edges in account while non-direct do not
    """

    def __init__(self, netlist:"HlsNetlistCtx", removed: Optional[Set[HlsNetNode]]=None):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        d = {n:set() for n in netlist.iterAllNodes() if removed is None or n not in removed}

        def initSets():
            return {k: set() for k in d.keys()}

        self._dataPredecessors: Dict[HlsNetNode, Set[HlsNetNodeExplicitSync]] = d
        self._dataSuccessors: Dict[HlsNetNode, Set[HlsNetNodeExplicitSync]] = initSets()
        self._controlPredecessors: Dict[HlsNetNode, Set[HlsNetNodeExplicitSync]] = initSets()
        self._controlSuccessors: Dict[HlsNetNode, Set[HlsNetNodeExplicitSync]] = initSets()

        self._directDataPredecessors: Dict[HlsNetNode, Set[HlsNetNodeExplicitSync]] = initSets()
        self._directDataSuccessors: Dict[HlsNetNode, Set[HlsNetNodeExplicitSync]] = initSets()
        
        # self._directControlPredecessors: Dict[HlsNetNode, Set[HlsNetNodeExplicitSync]] = initSets()
        self._directControlSuccessors: Dict[HlsNetNode, Set[HlsNetNodeExplicitSync]] = initSets()
    
        self.changedOutUse: UniqList[HlsNetNode] = UniqList()
        self.changedInDep: UniqList[HlsNetNode] = UniqList()
        self.removed = removed
        self._pendingRemoved = UniqList()

    def doesReachToControl(self, src:HlsNetNodeExplicitSync, dst:HlsNetNode):
        return src in self._controlPredecessors[dst] 
    
    def doesReachToData(self, src:HlsNetNodeExplicitSync, dst:HlsNetNode):
        return src in self._dataPredecessors[dst]
    
    def doesUseControlOf(self, n: HlsNetNodeExplicitSync, user: HlsNetNode):
        return user in self._controlSuccessors[n]
    
    def getDirectlyConnectedSyncForControlOut(self, n: HlsNetNodeExplicitSync):
        return self._directControlSuccessors[n]

    def getDirectlyConnectedSyncForDataOut(self, n: HlsNetNodeExplicitSync):
        return self._directDataSuccessors[n]

    def getDirectDataSuccessors(self, n: HlsNetNode):
        return self._directDataSuccessors[n]

    def getDirectDataPredecessors(self, n: HlsNetNode):
        return self._directDataPredecessors[n]
    
    def hasControlPredecessor(self, n: HlsNetNode):
        return bool(self._controlPredecessors[n])
    
    # def addOutUseChange(self, n: HlsNetNode):
    #    self.changedOutUse.append(n)
    #
    # def addInDepChange(self, n: HlsNetNode):
    #    self.changedInDep.append(n)
    #
    # def addAllUsersToInDepChange(self, n: HlsNetNode):
    #    addAllUsersToWorklist(self.changedInDep, n)
    #
    # def addAllDepsToOutUseChange(self, n: HlsNetNode):
    #    for dep in n.dependsOn:
    #        dep: HlsNetNodeIn
    #        self.changedOutUse.append(dep.obj)
    #
    # def onNodeRemove(self, n: HlsNetNode):
    #    self._controlPredecessors.pop(n)
    #    self._controlSuccessors.pop(n)
    #    # self._directControlPredecessors.pop(n)
    #    self._directControlSuccessors.pop(n)
    #
    #    self._dataPredecessors.pop(n)
    #    self._dataSuccessors.pop(n)
    #    self._directDataPredecessors.pop(n)
    #    self._directDataSuccessors.pop(n)
        
    # def commitChanges(self):
    #    if not self.changedInDep and not self.changedOutUse:
    #        return
    #
    #    print("commitChanges changedInDep")
    #    removed = self.removed
    #    if self._filterUniqList(self.changedInDep, removed):
    #        for n in self.changedInDep:
    #            print("    ", n)
    #        self.recomputeSyncPredecessorsRecursively(self.changedInDep)
    #        self.changedInDep.clear()
    #
    #    print("commitChanges changedOutUse")
    #    if self._filterUniqList(self.changedOutUse, removed):
    #        for n in self.changedOutUse:
    #            print("    ", n)
    #        self.recomputeSyncSuccessorsRecursively(self.changedOutUse)
    #        self.changedOutUse.clear()
    #
    #    self.checkConsystency()
        
    def _beforeNodeAddedListener(self, _, parentList: ObservableList[HlsNetNode], index: Union[slice, int], val: Union[HlsNetNode, Literal[ObservableListRm]]):
        pass
        # raise NotImplementedError()
    
    def _beforeInputDriveUpdate(self, n: HlsNetNode,
                                parentList: ObservableList[HlsNetNodeOut],
                                index: Union[slice, int],
                                val: Union[HlsNetNodeOut, Literal[ObservableListRm]]):
        inp = n._inputs[index]
        try:
            cur = n.dependsOn[index]
        except IndexError:
            cur = None

        if val is ObservableListRm or val is None:
            if isinstance(index, int):
                if cur is not None:
                    _len = len(n.dependsOn)
                    if index < _len:
                        list.__setitem__(n.dependsOn, index, None)
                    else:
                        if index == _len:
                            list.append(n.dependsOn, None)
                        else:
                            raise IndexError(index)
                        
                    self.recomputeSyncSuccessorsRecursively([cur.obj, ])
    
                    if index == _len:
                        list.pop(n.dependsOn)  # rm temporarily added item 
                
                    #print("deleted", cur, "->", inp)
            else:
                raise NotImplementedError(n, index, val)
        else:
            if isinstance(index, int):
                if cur is val:
                    return

                _len = len(n.dependsOn)
                if index < _len:
                    list.__setitem__(n.dependsOn, index, val)
                else:
                    if index == _len:
                        list.append(n.dependsOn, val)
                    else:
                        raise IndexError(index)
                
                if cur is not None:
                    assert inp not in cur.obj.usedBy[cur.out_i], (cur, "->", inp, "usedBy should be updated before dependsOn")
                    self.recomputeSyncSuccessorsRecursively([n, ])

                val.obj.usedBy[val.out_i].append(inp)
                self.recomputeSyncSuccessorsRecursively([val.obj, ])
                self.recomputeSyncPredecessorsRecursively([n, ])
                tmp = val.obj.usedBy[val.out_i].pop()
                assert tmp is inp, (tmp, inp)
                if index == _len:
                    list.pop(n.dependsOn)  # remove temporal added item
                #print("added", val, "->", inp, "was", cur)
            
            else:
                raise NotImplementedError(n, index, val)

    def _checkDoesNotContainRemoved(self, d: Dict[HlsNetNode, UniqList[HlsNetNode]], removed: Set[HlsNetNode]):
        for k, v in d.items():
            assert k not in removed, k
            for _v in v:
                assert _v not in removed, (k, _v)
    
    def checkConsystency(self):
        removed = self.removed
        check = self._checkDoesNotContainRemoved
        check(self._dataPredecessors, removed)
        check(self._dataSuccessors, removed)
        
        check(self._controlPredecessors, removed)
        check(self._controlSuccessors, removed)

        check(self._directDataPredecessors, removed)
        check(self._directDataSuccessors, removed)
        
        # check(self._directControlPredecessors, removed)
        # check(self._directControlSuccessors, removed)
        # for n, dp in self._dataPredecessors.items():
        #    dp: Set[HlsNetNode]
        #    ddp: Set[HlsNetNode] = self._directDataPredecessors[n]
        #    assert ddp.issubset(dp), (n, ddp.difference(dp)) 
        #
        # for n, ds in self._dataSuccessors.items():
        #    ds: Set[HlsNetNode]
        #    dds: Set[HlsNetNode] = self._directDataSuccessors[n]
        #    assert dds.issubset(ds), (n, dds.difference(ds)) 

    # @staticmethod
    # def _filterUniqList(ul: UniqList, toRemove: Set):
    #    offset = 0
    #    for i, n in enumerate(tuple(ul)):
    #        if n in toRemove:
    #            ul.pop(i - offset)
    #            offset += 1
    #    return ul

    def recomputeSyncPredecessorsRecursively(self, toUpdate: UniqList[HlsNetNode]):
        directDataPredecessors = self._directDataPredecessors
        # directControlPredecessors = self._directControlPredecessors
        # cancel current
        for n in toUpdate:
            directDataPredecessors.pop(n, None)
            # directControlPredecessors.pop(n, None)
 
        for n in toUpdate:
            self.recomputePredecessor(n, directDataPredecessors, True, True)
            # self.recomputePredecessor(n, directControlPredecessors, False, True)
        
        _toUpdate = copy(toUpdate)
        while _toUpdate:
            # start from predecessor and move to successor
            n = _toUpdate.pop()
            if self.recomputePredecessor(n, self._dataPredecessors, True, False):
                _toUpdate.extend(iterUserObjs(n))
    
        while toUpdate:
            n = toUpdate.pop()
            if self.recomputePredecessor(n, self._controlPredecessors, True, False):
                toUpdate.extend(iterUserObjs(n))

    @classmethod
    def recomputeSuccessors(cls, n: HlsNetNode,
                            dictToUpdate: Dict[HlsNetNode, Set[HlsNetNodeExplicitSync]],
                            ommitControl: bool,
                            stopPropagationOnSync: bool,
                            ):
        """
        Recompute successors from successors set of of every successor.
        """
        res = set()
        vldToOmmit = n._valid if ommitControl and isinstance(n, HlsNetNodeRead) else None
    
        for o, users in zip(n._outputs, n.usedBy):
            if o is vldToOmmit:
                continue
            for u in users:
                uObj = u.obj
                sucSet = dictToUpdate.get(uObj, None)
                if sucSet is None:
                    # there is some new node which does not have set initialized yet
                    cls.recomputeSuccessors(uObj, dictToUpdate, ommitControl, stopPropagationOnSync)
                    sucSet = dictToUpdate[uObj]
                userIsSync = isinstance(uObj, HlsNetNodeExplicitSync)
                
                res.add(uObj)
                if not (userIsSync and stopPropagationOnSync):
                    res.update(sucSet)
        
        # :note: new nodes which were just generated do not have record in nodeSyncSuccessors yet
        cur = dictToUpdate.get(n, None)
        if cur != res:
            dictToUpdate[n] = res
            return True
        
        return False
    
    @classmethod
    def recomputePredecessor(cls, n: HlsNetNode,
                             dictToUpdate: Dict[HlsNetNode, Set[HlsNetNodeExplicitSync]],
                             ommitControl: bool,
                             stopPropagationOnSync: bool,
                             ) -> bool:
        """
        Recompute predecessor set from predecessors set of every directly connected predecessor.
        """
        res = set()
        for dep in n.dependsOn:
            if dep is None:
                continue
            depObj = dep.obj
            curDepSet = dictToUpdate.get(depObj, None)
            if curDepSet is None:
                # there is some unresolved dependency
                cls.recomputePredecessor(depObj, dictToUpdate, ommitControl, stopPropagationOnSync)
                curDepSet = dictToUpdate[depObj]

            depIsSync = isinstance(depObj, HlsNetNodeExplicitSync)
            if stopPropagationOnSync and depIsSync:
                res.add(depObj)
            else:
                res.update(curDepSet)

            if depIsSync:
                if ommitControl and isinstance(depObj, HlsNetNodeRead) and dep is depObj._valid:
                    # avoid adding depObj._valid to set
                    continue
    
                res.add(depObj)

        # :note: new nodes which were just generated do not have record in dictToUpdate yet
        cur = dictToUpdate.get(n, None)
        if cur != res:
            dictToUpdate[n] = res
            return True
    
        return False

    def recomputeSyncSuccessorsRecursively(self, toUpdate: UniqList[HlsNetNode]):
        directDataSuccessors = self._directDataSuccessors
        directControlSuccessors = self._directControlSuccessors
        dataSuccessors = self._dataSuccessors
        controlSuccessors = self._controlSuccessors
        # cancel current
        for n in toUpdate:
            directDataSuccessors.pop(n, None)
            directControlSuccessors.pop(n, None)

        for n in toUpdate:
            self.recomputeSuccessors(n, directDataSuccessors, True, True)
            self.recomputeSuccessors(n, directControlSuccessors, False, True)
        
        # propagate on data paths
        _toUpdate = copy(toUpdate)
        while _toUpdate:
            # start from successor and move to predecessor
            n = _toUpdate.pop()
            if self.recomputeSuccessors(n, dataSuccessors, True, False):
                if isinstance(n, HlsNetNodeRead):
                    for o, dep in zip(n._outputs, n.dependsOn):
                        if o is not n._valid:
                            _toUpdate.append(dep.obj)
                else:
                    _toUpdate.extend(iterDepObjs(n))
    
        # propagate on control paths
        while toUpdate:
            # start from successor and move to predecessor
            n = toUpdate.pop()
            if self.recomputeSuccessors(n, controlSuccessors, True, False):
                toUpdate.extend(iterDepObjs(n))

    # def popNode(self, n: HlsNetNode):
    #    for d in (self._dataPredecessors, self._dataSuccessors, self._controlPredecessors,
    #              self._controlSuccessors, self._directDataPredecessors, self._directDataSuccessors,
    #              self._directControlPredecessors, self._directControlSuccessors):
    #        d.pop(n)

    def _discoverSyncPredecessors(self, mainNode: HlsNetNode):
        dataPredecessors = self._dataPredecessors
        controlPredecessors = self._controlPredecessors
        directDataPredecessors = self._directDataPredecessors
        # directControlPredecessors = self._directControlPredecessors

        isSync = isinstance(mainNode, HlsNetNodeExplicitSync)
        seen: Set[HlsNetNode] = set()            
        toSearch: UniqList[Tuple[HlsNetNode, bool, bool, bool]] = UniqList(((mainNode, True, True, False),))
        while toSearch:
            n, isDirect, isData, isControl = toSearch.pop()
            n: HlsNetNode
            if n in seen:
                continue
            else:
                seen.add(n)
                # isSync = isinstance(n, HlsNetNodeExplicitSync)
                if n is not mainNode:
                    if isData:
                        curDataSync = dataPredecessors[n]
                        if isSync in curDataSync:
                            # because this node and all its uses already have this sync
                            continue
                        curDataSync.add(mainNode)
                        if isDirect and isSync:
                            directDataPredecessors[n].add(mainNode)
    
                    if isControl:
                        curControlSync = controlPredecessors[n]
                        if isSync in curControlSync:
                            # because this node and all its uses already have this sync
                            continue
    
                        curControlSync.add(mainNode)
                        # if isDirect and isSync:
                        #    directControlPredecessors[n].add(mainNode)
                        
            # follow the connection to uses
            isIo = isinstance(n, HlsNetNodeRead)
            if isDirect and n is not mainNode and isinstance(n, HlsNetNodeExplicitSync):
                # connection stops being direct after first sync node found on path
                isDirect = False

            for o, uses in zip(n._outputs, n.usedBy):
                if isIo and o is n._valid:
                    _isControl = True
                    _isData = False
                else:
                    _isControl = isControl
                    _isData = isData
                for u in uses:
                    u: HlsNetNodeIn
                    toSearch.append((u.obj, isDirect, _isData, _isControl))

    def _discoverSyncSuccessors(self, mainNode: HlsNetNode):
        dataSuccessors = self._dataSuccessors
        controlSuccessors = self._controlSuccessors
        directDataSuccessors = self._directDataSuccessors
        directControlSuccessors = self._directControlSuccessors

        isSync = isinstance(mainNode, HlsNetNodeExplicitSync)
        toSearch: UniqList[Tuple[HlsNetNode, bool, bool, bool]] = UniqList(((mainNode, True, True, False),))
        
        syncNodeWasSeen = False
        while toSearch:
            n, isDirect, isData, isControl = toSearch.pop()
            n: HlsNetNode
            # isSync = isinstance(n, HlsNetNodeExplicitSync)
            if n is not mainNode:
                didUpdate = False
                if isData:
                    curDataSync = dataSuccessors[n]
                    if isSync not in curDataSync:
                        # because this node and all its uses already have this sync
                        curDataSync.add(mainNode)
                        if isDirect and isSync:
                            directDataSuccessors[n].add(mainNode)
                        didUpdate = True
    
                if isControl:
                    curControlSync = controlSuccessors[n]
                    if isSync not in curControlSync:
                        # because this node and all its uses already have this sync
                        curControlSync.add(mainNode)
                        if isDirect and isSync:
                            directControlSuccessors[n].add(mainNode)
                        didUpdate = True
 
                if not didUpdate:
                    continue

            else:
                if syncNodeWasSeen:
                    continue
                syncNodeWasSeen = True
    
            # follow the connection to uses
            nIsSync = isinstance(n, HlsNetNodeExplicitSync)
            if isDirect and n is not mainNode and nIsSync:
                # connection stops being direct after first sync node found on path
                isDirect = False

            for i, dep in zip(n._inputs, n.dependsOn):
                if dep is None:
                    continue
                if nIsSync and (i is n.extraCond or i is n.skipWhen):
                    _isControl = True
                    _isData = False
                else:
                    _isControl = isControl
                    _isData = isData
                toSearch.append((dep.obj, isDirect, _isData, _isControl))

    def run(self):
        removed = self.removed
        for n in self.netlist.iterAllNodes():
            if removed is not None and n in removed:
                continue

            self._discoverSyncPredecessors(n)
            self._discoverSyncSuccessors(n)

