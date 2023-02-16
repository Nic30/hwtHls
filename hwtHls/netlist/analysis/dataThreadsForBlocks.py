from typing import Dict, Set, List, Union, Optional

from hwt.pyUtils.arrayQuery import flatten
from hwt.pyUtils.uniqList import UniqList
from hwtHls.llvm.llvmIr import MachineBasicBlock
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HVoidOrdering
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOutLazy, \
    HlsNetNodeOutAny


class HlsNetlistAnalysisPassDataThreadsForBlocks(HlsNetlistAnalysisPass):
    """
    Walk nodes and find the independent dataflow threads.
    Dataflow thread is a subset of netlist nodes where each node is reachable from any node (= a single graph component).
    The original netlist contains also non-data dependencies and nodes which must be excluded.

    :ivar threadPerNode: a thread for each node
    :ivar threadsPerBlock: for each block threads which do have some node from this block
    """

    def __init__(self, netlist: HlsNetlistCtx):
        super(HlsNetlistAnalysisPassDataThreadsForBlocks, self).__init__(netlist)
        self.threadPerNode: Dict[HlsNetNode, Set[Union[HlsNetNode, HlsNetNodeOutLazy]]] = {}
        self.threadsPerBlock: Dict[MachineBasicBlock, List[Set[HlsNetNode]]] = {}

    def mergeThreads(self, t0: Set[HlsNetNode], t1: Set[HlsNetNode]):
        "Merge t0 into t1 and replace t1 with t0 in self.threadPerNode"
        threads = self.threadPerNode
        for n in t1:
            threads[n] = t0
        t0.update(t1)

    def searchForThreads(self, obj: HlsNetNode):
        """
        :return: the data-flow thread for this object, flag which tells if this is newly discovered thread
        """
        try:
            return self.threadPerNode[obj], False
        except KeyError:
            pass

        # collect all nodes which are tied through data dependency
        allMembersOfThread: Set[HlsNetNode] = set()
        toSearch = [obj, ]
        while toSearch:
            obj = toSearch.pop()
            if obj in allMembersOfThread:
                continue
            allMembersOfThread.add(obj)
            self.threadPerNode[obj] = allMembersOfThread
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
                    allMembersOfThread.add(dep)
                    self.threadPerNode[dep] = allMembersOfThread
                    continue

                depObj = dep.obj
                if dep._dtype == HVoidOrdering:
                    continue
                if depObj not in allMembersOfThread:
                    toSearch.append(depObj)

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
            
        return threads

    def run(self):
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
                liveIns = UniqList(flatten(liveInGroups, 1))
                liveIns = [originalMir.valCache._toHlsCache[(mb, li)] for li in liveIns
                           if li not in originalMir.regToIo and not MRI.def_empty(li)]
                self.threadsPerBlock[mb] = self.searchEnForDrivenThreads(en, liveIns)

