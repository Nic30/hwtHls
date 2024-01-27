from typing import Dict, Set, List, Union, Optional, Tuple

from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.llvm.llvmIr import MachineBasicBlock
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge, \
    HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOutLazy, \
    HlsNetNodeOutAny
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite

DataFlowThread = Union[HlsNetNode, HlsNetNodeOutLazy]


class HlsNetlistAnalysisPassDataThreadsForBlocks(HlsNetlistAnalysisPass):
    """
    Walk nodes and find the independent dataflow threads.
    Dataflow thread is a subset of netlist nodes where each node is reachable from any node (= a single graph component).
    The original netlist may contain also non-data dependencies and nodes which must be excluded.

    :attention: This type of analysis can not be performed on MIR, because MIR instructions can be lowered to multiple
        HlsNetNode instances and which may not be in the same thread.
    :attention: This analysis must be done before we connect control, because once we do that
        everything will blend together.
    :ivar threadPerNode: a thread for each node
    :ivar threadsPerBlock: for each block threads which do have some node from this block
    """

    def __init__(self, netlist: HlsNetlistCtx):
        super(HlsNetlistAnalysisPassDataThreadsForBlocks, self).__init__(netlist)
        self.threadPerNode: Dict[HlsNetNode, Set[Union[HlsNetNode, HlsNetNodeOutLazy]]] = {}
        self.threadsPerBlock: Dict[MachineBasicBlock, List[DataFlowThread]] = {}
        self.threadIdToBlock: Dict[int, List[MachineBasicBlock]] = {}

    def mergeThreads(self, t0: DataFlowThread, t1: DataFlowThread):
        "Merge t0 into t1 and replace t1 with t0 in self.threadPerNode"
        assert t0 is not t1
        assert t0 is not None
        assert t1 is not None

        threads = self.threadPerNode
        for n in t1:
            threads[n] = t0
        t0.update(t1)

        # replace thread in block theads
        t0Id = id(t0)
        t1Id = id(t1)
        threadIdToBlock = self.threadIdToBlock
        threadsPerBlock = self.threadsPerBlock
        # replace t1 in blocks
        for b in threadIdToBlock[t1Id]:  # for each block where t1 is used
            threadInBlock = threadsPerBlock[b]
            t0i = None
            t1i = None
            for i, t in enumerate(threadInBlock):
                # search for index of t0, t1 in list of threads for block b
                tId = id(t)
                if t0Id == tId:
                    assert t0i  is None
                    t0i = i
                elif t1Id == tId:
                    assert t1i  is None
                    t1i = i
            assert t1i is not None, "Must not be None because we are searching in block which should have t1"
            threadInBlock.pop(t1i)
            if t0i is None:
                threadInBlock.append(t0)
        threadIdToBlock.pop(t1Id)

    def searchForThreads(self, obj: Union[HlsNetNode, HlsNetNodeOutLazy]) -> Tuple[DataFlowThread, bool]:
        """
        :return: the data-flow thread for this object, flag which tells if this is newly discovered thread
        """
        try:
            return self.threadPerNode[obj], False
        except KeyError:
            pass

        if isinstance(obj, HlsNetNodeOutLazy):
            if obj._dtype == HVoidOrdering:
                return None, False

        # collect all nodes which are tied through data dependency
        allMembersOfThread: Set[HlsNetNode] = set()
        toSearch = [obj, ]
        while toSearch:
            obj = toSearch.pop()
            if obj in allMembersOfThread:
                continue

            assert obj not in self.threadPerNode, obj
            allMembersOfThread.add(obj)
            self.threadPerNode[obj] = allMembersOfThread

            if isinstance(obj, HlsNetNodeOutLazy):
                assert obj._dtype != HVoidOrdering, obj
                for use in obj.dependent_inputs:
                    use: HlsNetNodeIn
                    useObj = use.obj
                    if useObj not in allMembersOfThread:
                        toSearch.append(useObj)
            else:
                # :note: do not skip HVoidExternData ports because they are data dependency even though they are of void type
                for o, uses in zip(obj._outputs, obj.usedBy):
                    if o._dtype == HVoidOrdering:
                        continue
                    for use in uses:
                        use: HlsNetNodeIn
                        useObj = use.obj
                        if useObj not in allMembersOfThread:
                            toSearch.append(useObj)

                for dep in obj.dependsOn:
                    if dep._dtype == HVoidOrdering:
                        continue
                    if isinstance(dep, HlsNetNodeOutLazy):
                        dep: HlsNetNodeOutLazy
                        allMembersOfThread.add(dep)
                        self.threadPerNode[dep] = allMembersOfThread
                        toSearch.extend(u.obj for u in dep.dependent_inputs)
                        continue

                    depObj = dep.obj
                    if dep._dtype == HVoidOrdering:
                        continue
                    if depObj not in allMembersOfThread:
                        toSearch.append(depObj)

                if isinstance(obj, HlsNetNodeWriteForwardedge):
                    toSearch.append(obj.associatedRead)
                elif isinstance(obj, HlsNetNodeReadForwardedge):
                    toSearch.append(obj.associatedWrite)

        return allMembersOfThread, True

    def searchEnForDrivenThreads(self, en: Optional[HlsNetNodeOutLazy], liveIns: List[HlsNetNodeOutAny]):
        """
        Walk all nodes affected by this en signal and aggregate them into dataflow threads.
        """
        threads = []
        if en is not None:
            for use in en.dependent_inputs:
                use: HlsNetNodeIn
                thread, isNew = self.searchForThreads(use.obj)
                if isNew or not any(t is thread for t in threads):
                    threads.append(thread)

        for liveIn in liveIns:
            if isinstance(liveIn, HlsNetNodeOutLazy):
                if en is not None:
                    for use in en.dependent_inputs:
                        use: HlsNetNodeIn
                        thread, isNew = self.searchForThreads(use.obj)
                        if isNew or not any(t is thread for t in threads):
                            threads.append(thread)
            else:
                thread, isNew = self.searchForThreads(liveIn.obj)
                if isNew or not any(t is thread for t in threads):
                    threads.append(thread)
                self.consystencyCheck()
        return threads

    @staticmethod
    def threadContainsNonConcurrentIo(thread: DataFlowThread):
        """
        :returns: True if there are multiple nodes which are using the same interface.
        """
        seenIos: Set[Union[InterfaceBase, RtlSignalBase]] = set()
        for n in thread:
            if isinstance(n, (HlsNetNodeReadBackedge, HlsNetNodeWriteBackedge, HlsNetNodeReadForwardedge, HlsNetNodeWriteForwardedge)):
                # there is always only 1 instance of write/read to such a channel
                continue
            elif isinstance(n, HlsNetNodeWrite):
                i = n.dst
            elif isinstance(n, HlsNetNodeRead):
                i = n.src
            else:
                continue

            assert i is not None, n
            if i in seenIos:
                return True
            else:
                seenIos.add(i)

        return False

    def consystencyCheck(self):
        allSets = []
        seenSetIds: Set[int] = set()
        for t in self.threadPerNode.values():
            if id(t) in seenSetIds:
                continue
            else:
                seenSetIds.add(id(t))
                allSets.append(t)

        seen = set()
        for t in allSets:
            if not seen.isdisjoint(t):
                raise AssertionError("Nodes were already in a different thread", sorted(n._id for n in seen.intersection(t)))
            seen.update(t)

    def run(self):
        assert not self.threadPerNode
        assert not self.threadsPerBlock
        from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
        originalMir: HlsNetlistAnalysisPassMirToNetlist = self.netlist.getAnalysisIfAvailable(HlsNetlistAnalysisPassMirToNetlist)
        if originalMir is None:
            # we do not have MIR because this netlist was not generated from it, we have to search everything and we can not distinguish between control and data path
            liveIns = []
            for i in self.netlist.inputs:
                liveIns.extend(i._outputs)
            self.threadsPerBlock[None] = self.searchEnForDrivenThreads(None, liveIns)

        else:
            MRI = originalMir.mf.getRegInfo()
            for mb in originalMir.mf:
                mb: MachineBasicBlock
                en: HlsNetNodeOutLazy = originalMir.blockSync[mb].blockEn
                assert isinstance(en, HlsNetNodeOutLazy), ("This analysis works only if control is not instantiated yet", en)
                liveInGroups = list(originalMir.liveness[pred][mb] for pred in mb.predecessors())
                seen = set()

                liveIns = []
                for liveInGroup in liveInGroups:
                    for liveIn in liveInGroup:
                        if liveIn in seen:
                            continue
                        seen.add(liveIn)
                        if originalMir._regIsValidLiveIn(MRI, liveIn):
                            li = originalMir.valCache._toHlsCache[(mb, liveIn)]
                            liveIns.append(li)

                threads = self.searchEnForDrivenThreads(en, liveIns)
                self.threadsPerBlock[mb] = threads
                for t in threads:
                    blockOfThread = self.threadIdToBlock.get(id(t), None)
                    if blockOfThread is None:
                        self.threadIdToBlock[id(t)] = [mb, ]
                    else:
                        blockOfThread.append(mb)
