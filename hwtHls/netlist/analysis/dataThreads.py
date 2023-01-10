from typing import Dict, Set, Tuple, Optional

from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HOrderingVoidT
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.read import HlsNetNodeRead


class HlsNetlistAnalysisPassDataThreads(HlsNetlistAnalysisPass):
    """
    Walk nodes and find the independent dataflow threads.
    Dataflow thread is a subset of netlist nodes, a DAG where nodes are connected using data dependency.
    (Non-data connections are ignored.)

    :ivar threadPerNode: a thread for each node
    """

    def __init__(self, netlist: HlsNetlistCtx):
        super(HlsNetlistAnalysisPassDataThreads, self).__init__(netlist)
        self.threadPerNode: Dict[HlsNetNode, Set[HlsNetNode]] = {}

    def mergeThreads(self, t0: Set[HlsNetNode], t1: Set[HlsNetNode]):
        "Merge t0 into t1 and replace t1 with t0 in self.threadPerNode"
        threads = self.threadPerNode
        for n in t1:
            threads[n] = t0
        t0.update(t1)

    def searchForThreads(self, obj: HlsNetNode) -> Tuple[Set[HlsNetNode], bool]:
        """
        :return: the data-flow thread for this object, flag which tells if this is newly discovered thread
        """
        # collect all nodes which are tied through data dependency
        threads = self.threadPerNode
        allMembersOfThread = threads.get(obj, None)
        if allMembersOfThread is None:
            allMembersOfThread = threads[obj] = set()
        allMembersOfThread: Set[HlsNetNode]

        allMembersOfThread.add(obj)
        threads[obj] = allMembersOfThread
        # :note: do not skip HExternalDataDepT ports because they are data dependency even though they are of void type
        
        if isinstance(obj, HlsNetNodeExplicitSync):
            ec = getattr(obj, "extraCond", None)
            sw = getattr(obj, "skipWhen", None)
        else:
            ec = None
            sw = None    
        
        for i, dep in zip(obj._inputs, obj.dependsOn):
            depObj = dep.obj
            if i is ec or\
               i is sw or\
               dep._dtype == HOrderingVoidT or\
               (isinstance(depObj, HlsNetNodeRead) and dep is getattr(depObj, "_valid", None)):
                continue
            allMembersOfThread.add(depObj)
            otherThread = threads.get(depObj, None)
            
            if otherThread is None:
                # assign current thread for depObj
                allMembersOfThread.add(depObj)
                threads[depObj] = allMembersOfThread

            elif otherThread is allMembersOfThread:
                # already discovered to be in the same thread possibly by some parallel path
                pass

            else:
                self.mergeThreads(allMembersOfThread, otherThread)

    def run(self, removed: Optional[Set[HlsNetNode]]=None):
        if removed:
            for n in self.netlist.iterAllNodes():
                if n in removed:
                    continue
                self.searchForThreads(n)
        else:
            for n in self.netlist.iterAllNodes():
                self.searchForThreads(n)
            
