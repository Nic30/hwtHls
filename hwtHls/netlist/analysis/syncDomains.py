from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
from typing import List, Dict, Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HOrderingVoidT, HExternalDataDepT
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync


class HlsNetlistAnalysisPassDiscoverIoSyncSccs(HlsNetlistAnalysisPass):
    """
    Discover Strongly Connected Components of IO operations in netlist.

    :note: Found subgraphs do have special scheduling requirements. By default all nodes with such a component
        must be scheduled in a single clock cycle in order to assert that the read is not performed speculatively
        when it is optional. A speculative read of data in circuits which explicitly specify that the read should
        not be performed may lead to a deadlock.
    :note: The IO SCC is not related to data but to synchronization of IO channel functionality.
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.ioSccs: List[UniqList[HlsNetNode]] = []
        self.syncUses: Dict[HlsNetNodeRead, UniqList[HlsNetNodeExplicitSync]] = {}

    def run(self):
        assert not self.ioSccs and not self.syncUses, "Must be run only once."
        # The naive discovery algorithm for the sync associated to IO operation mapping has O(|nodes|*|edges|) time complexity.
        # Commonly the |nodes| > 10k and |edges| > 30K, that said the time complexity is prohibitively large.
        # The |HlsNetNodeExplicitSync| << |HlsNetNode| from this reason we start search at HlsNetNodeExplicitSync
        # and walk only in the direction to a read (defs). 
        
        # :note: If the value for read is not in the dict it means that there is no extra sync for this read.
        syncUses = self.syncUses
        usersOfSync: Dict[HlsNetNodeReadSync, UniqList[HlsNetNodeReadSync]] = {}
        g = DiGraph()
        for n in self.netlist.iterAllNodes():
            n: HlsNetNode
            g.add_node(n)
            for dep in n.dependsOn:
                if dep._dtype is not HOrderingVoidT and dep._dtype is not HExternalDataDepT:
                    g.add_edge(dep.obj, n)

            if n.__class__ is HlsNetNodeExplicitSync or isinstance(n, HlsNetNodeReadSync):
                toSearch = [dep.obj for dep in n.dependsOn if dep._dtype is not HOrderingVoidT and dep._dtype is not HExternalDataDepT]
                # anyDepFound = False
                seen = set()
                while toSearch:
                    depObj: HlsNetNode = toSearch.pop()
                    if depObj in seen:
                        continue
                    seen.add(depObj)
                    if isinstance(depObj, (HlsNetNodeRead, HlsNetNodeWrite)):
                        depSyncUses = syncUses.get(depObj, None)
                        if depSyncUses is None:
                            depSyncUses = syncUses[depObj] = UniqList()
                        depSyncUses.append(n)
                        users = usersOfSync.get(n, None)
                        if users is None:
                            users = usersOfSync[n] = UniqList()
                        users.append(depObj)
                        # anyDepFound = True
                    else:
                        toSearch.extend(dep.obj for dep in depObj.dependsOn
                                        if dep._dtype is not HOrderingVoidT and dep._dtype is not HExternalDataDepT and dep.obj not in seen)
                # assert anyDepFound, (n, "Must be associated with some IO otherwise it should already be removed")

        # add edge from sync back to read/write to mark they are in same SCC
        for op, extraSyncList in syncUses.items():
            for extraSync in extraSyncList:
                g.add_edge(extraSync, op)
            if op._associatedReadSync is not None:
                g.add_edge(op._associatedReadSync, op)

        # build a cycle on all IO which is using same sync
        for users in usersOfSync.values():
            if len(users) > 1:
                userIt = iter(users)
                firstUser = next(userIt)
                lastUser = firstUser
                for u in users:
                    g.add_edge(lastUser, u)
                    lastUser = u

                g.add_edge(lastUser, firstUser)
            
        ioSccs = self.ioSccs
        for ioScc in strongly_connected_components(g):
            ioScc: Set[HlsNetNode]
            if len(ioScc) > 1:
                ioSccs.append(UniqList(sorted(ioScc, key=lambda n: n._id)))
