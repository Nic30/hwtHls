from itertools import chain
from typing import List, Dict, Set, Tuple, Callable, Generator

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.syncGroupClusterContext import SyncGroupLabel, \
    SyncGroupClusterContext, HlsNetNodeAnySync
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering, HVoidExternData
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopChannelGroup import LoopChanelGroup
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeIn


class HlsNetlistAnalysisPassSyncDomains(HlsNetlistAnalysisPass):
    """
    Discover Strongly Connected Components (SCCs) of IO and sync operations in netlist.
    SCCs do represent the scheduling and architectural constraint related to not to data but to synchronization of IO channel functionality.
    
    :note: Found subgraphs do have special scheduling requirements. By default all nodes within such a component
        must be scheduled in a single clock cycle in order to assert that the read is not performed speculatively
        when it is optional. (A speculative read of data in circuits which explicitly specify that the read should
        not be performed may lead to a deadlock.)
    :note: This pass ignores hierarchy created by HlsNetNodeAggregate instances.

    The reasons why HlsNetNodeExplicitSync appears in the circuit:
    * Implementation of optional/non-blocking read.
      * Because of this individual circuit parts may run independently and do require independent control.
      * HlsNetNodeExplicitSync is never associated with a write, if this was the case the sync should be already
        merged to write.
    * Selection of inputs for loops.
      * Because of this it is likely that there are multiple sync nodes along the data path.
        Not everything needs to be scheduled in a single clock and data can potentially stall or be dropped anywhere along the path.
        This implies that if this is a case data has to have some validity flag.


    Rules for extraction of sync for pipeline
    * In every pipeline which is not fully initialized by reset there must be a set of validity flags
      for each stage in order to resolve if the the stage contains data or not.
    * HlsNetlistAnalysisPassIoDiscoverSyncSccs specifies which nodes are affect by each sync node.
    * From flags of the sync it can be resolved if the data may be dropped or read non-blocking (= has skipWhen flag).
      If there is sync node a sync of all predecessors must be in separate pipeline so it runs asynchronously
      from rest of the pipeline and this sync node must be an inter-element channel. 
      However this is only required if predecessors of the sync node can not fit in the same clock tick.
      If they can the sync node can be realized combinationally and there is no need for another asynchronous pipeline.

    Rules for extraction of sync for FSM
    * Note that if some part of FSM should run asynchronously, it means that it must be a separate FSM.
    * Rules are similar as for pipeline however FSMs are always in a single state and communication between FSMs may be in multiple states.
      This alone creates a possibility for deadlock, but there is yet another problem.
      If the FSM is cut it cancels register sharing inside FSM.
      And all IO nodes specific to some IO channels needs to stay in a single FSM.
      This further complicates architecture.


    Other notes:
    * There is no real difference between explicit sync generated for loops or IO.
    * The sync is often tied with the data and often multiple IO channels are interacting with each other sync.
    * It is highly desired to schedule all connected sync into the same clock tick as an IO to reduce control complexity.
    * Pipeline flushing is a specific case of this problematic. It is a functionality described using sync nodes.
    * What is an exact query for the sync nodes which must be scheduled in same clock cycle?
       * There is no such rule, instead sync should be aggregated as much as possible.
    * Due to optional read there may be the situation where pipeline have multiple potential starts
      or FSM may contain multiple sub-states based on which data were available.
      This is a problem because there may be a situation where it is resolved if the read should be performed or not
      after read was done. Depending on how sync is implemented this may potentially result in deadlock
      if read waits on resolution of sync or data loose if the data was read before it was resolved that data should be read.
    """

    def __init__(self):
        super(HlsNetlistAnalysisPassSyncDomains, self).__init__()
        self.ioSccs: List[UniqList[HlsNetNode]] = []
        self.syncOfNode: Dict[HlsNetNode, Set[HlsNetNodeAnySync]] = {}
        self.syncDomains: Dict[List[Tuple[SyncGroupLabel, UniqList[HlsNetNode]]]] = {}

    @staticmethod
    def _discoverSyncUsers(syncNode: HlsNetNodeAnySync, syncOfNode: Dict[HlsNetNode, Set[HlsNetNodeAnySync]]):
        """
        Discover all nodes which are directly data dependent on this sync, but are not a sync node
        This is a first step in discovering the reach of the sync node.
        """
        seen: Set[HlsNetNode] = set()
        toSearch: List[HlsNetNode] = [syncNode, ]
        if isinstance(syncNode, HlsNetNodeLoopStatus):
            for e in syncNode.iterConnectedChannelGroups():
                e: LoopChanelGroup
                toSearch.append(e.getChannelWhichIsUsedToImplementControl().associatedRead)

        while toSearch:
            n0: HlsNetNode = toSearch.pop()
            if n0 in seen:
                continue
            else:
                seen.add(n0)
                if n0 is not syncNode:
                    curSync = syncOfNode[n0]
                    if syncNode in curSync:
                        # because this node and all its uses already have this sync
                        continue
                    curSync.add(syncNode)

                if n0 is not syncNode and isinstance(n0, (HlsNetNodeExplicitSync, HlsNetNodeLoopStatus)):
                    # this is end of the search
                    # interSyncDomainConnections.add((syncNode, n0))
                    continue

                else:
                    # follow the connection to uses
                    for o, uses in zip(n0._outputs, n0.usedBy):
                        if  o._dtype is HVoidOrdering or o._dtype is HVoidExternData:
                            # skip ordering because it is not a real data dependency
                            continue

                        for u in uses:
                            u: HlsNetNodeIn
                            n1 = u.obj
                            if n1 not in seen:
                                toSearch.append(n1)

    @staticmethod
    def _discoverSyncSinkUsers(getNodeIteratorFn: Callable[[], Generator[HlsNetNode, None, None]],
                               syncOfNode: Dict[HlsNetNode, Set[HlsNetNodeAnySync]]):
        """
        For every dependency object which is not yet in any group assign it to a group of its sink
        """
        nodesWithSyncedSinkOnly: Set[HlsNetNode] = set(
            n
            for n in getNodeIteratorFn()
            if not syncOfNode[n] and not isinstance(n, (HlsNetNodeExplicitSync, HlsNetNodeLoopStatus)))
        # nodes must be detected in advance because this information is required when
        # some node is synchronized by multiple sinks
        for n in getNodeIteratorFn():
            sync = syncOfNode[n]
            if sync:
                toSearch: List[HlsNetNode] = [n, ]
                seen = set()
                while toSearch:
                    n0: HlsNetNode = toSearch.pop()
                    if n0 in seen:
                        continue

                    if n0 is n:
                        updatePropagete = True
                    else:
                        # assert n0 in nodesWithSyncedSinkOnly, "Should be trivially satisfied because we are searching only such nodes"
                        assert not isinstance(n0, (HlsNetNodeExplicitSync, HlsNetNodeLoopStatus)), (
                            n0, "This node should have been discovered previously and should not appear in nodes without sync")
                        n0sync = syncOfNode[n0]
                        prevSyncLen = len(n0sync)
                        n0sync.update(sync)
                        updatePropagete = len(n0sync) != prevSyncLen

                    seen.add(n0)
                    if updatePropagete:
                        for dep in n0.dependsOn:
                            t = dep._dtype
                            if t is HVoidOrdering or t is HVoidExternData:
                                continue
                            depObj = dep.obj
                            if depObj not in nodesWithSyncedSinkOnly or depObj in seen:
                                continue
                            toSearch.append(dep.obj)

    @staticmethod
    def _discoverSyncCutsByClkOffset(allSyncs: List[HlsNetNodeAnySync],
                                     allDelays: List[HlsNetNodeDelayClkTick],
                                     syncOfNode: Dict[HlsNetNode, Set[HlsNetNodeAnySync]]):
        """
        for every sync which takes more than 1 clock to complete cut off the group part after this node from rest of the group
        where this sync is
        """
        for syncNode in chain(allSyncs, allDelays):
            if syncNode.realization is None:
                syncNode.resolveRealization()
            if not any(syncNode.outputClkTickOffset):
                continue

            # for all successors cancel all dependencies which are shared with this node
            # because output of this node shifts successors to a next clock and thus they can not
            # be in IO SCC because they must be scheduled in a different clock cycle
            n0Deps = syncOfNode.get(syncNode, None)
            if n0Deps is not None:
                # remove syncNode, None and all predecessors of syncNode from successors of syncNode
                seen: Set[HlsNetNode] = set()
                # walk all nodes which are directly data dependent on this sync, but are a sync node
                toSearch: List[HlsNetNode] = [syncNode, ]

                while toSearch:
                    n0: HlsNetNode = toSearch.pop()
                    if n0 in seen:
                        continue
                    else:
                        seen.add(n0)
                        if n0 is not syncNode:
                            sync = syncOfNode[n0]
                            if sync:
                                for discardedDepNode in n0Deps:
                                    sync.discard(discardedDepNode)
                                sync.discard(syncNode)

                        if n0 is not syncNode and isinstance(n0, (HlsNetNodeExplicitSync, HlsNetNodeLoopStatus)):
                            # this is end of the search
                            # interSyncDomainConnections.add((syncNode, n0))
                            continue

                        else:
                            # follow the connection to uses
                            for uses0 in n0.usedBy:
                                for u in uses0:
                                    u: HlsNetNodeIn
                                    n1 = u.obj
                                    if n1 not in seen:
                                        toSearch.append(n1)
            else:
                raise NotImplementedError("Remove just self from all successors")

    @staticmethod
    def _addSelfToSyncOfSelf(allSyncs: List[HlsNetNodeAnySync], syncOfNode: Dict[HlsNetNode, Set[HlsNetNodeAnySync]]):
        """
        Add each sync node to a sync of self.
        """
        for syncNode in allSyncs:
            # add sync node to its cluster
            sync = syncOfNode.get(syncNode, None)
            if sync is None:
                sync = syncOfNode[syncNode] = set()
            sync.add(syncNode)

    def _discoverSyncAssociationsDefToUse(self, netlist:"HlsNetlistCtx"):
        """
        Collect all associations of sync nodes to all nodes.
        Start search on HlsNetNodeAnySync instances and walk circuit in def to use direction
        and stop on each HlsNetNodeAnySync instance.

        If something with delay > 1 clk is discovered it is required to move all successors from this IO SCC.
        This must be also done transitively. If node with > 1 clk delay has some predecessors the nodes
        which does have bout this node and its predecessor
        """
        getNodeIteratorFn = lambda: netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT)
        syncOfNode = self.syncOfNode = {n: set() for n in getNodeIteratorFn()}
        allSyncs: List[HlsNetNodeAnySync] = []
        allDelays: List[HlsNetNodeDelayClkTick] = []
        # from every sync walk down (def->use) and discover which nodes are affected
        for syncNode in getNodeIteratorFn():
            if not isinstance(syncNode, (HlsNetNodeExplicitSync, HlsNetNodeLoopStatus)):
                if isinstance(syncNode, HlsNetNodeDelayClkTick):
                    allDelays.append(syncNode)

                continue

            syncNode: HlsNetNodeExplicitSync
            allSyncs.append(syncNode)
            self._discoverSyncUsers(syncNode, syncOfNode)

        self._discoverSyncCutsByClkOffset(allSyncs, allDelays, syncOfNode)
        self._discoverSyncSinkUsers(getNodeIteratorFn, syncOfNode)
        self._addSelfToSyncOfSelf(allSyncs, syncOfNode)

    def _discoverSyncDomains(self):
        """
        After reach of the sync to every node resolve the SCCs in synchronization
        node to sync set map -> sync group label to node list map -> sync group cluster to node list map -> IO SCC to node list map
        """
        sgcc = SyncGroupClusterContext(self.syncOfNode)
        syncGroups, syncGroupOfNode = sgcc.resolveSyncGroups()
        syncDomains = self.syncDomains = sorted(syncGroups.items(), key=lambda x: x[0][0]._id)
        ioSccs = self.ioSccs
        for scc in sgcc.mergeSyncGroupsToClusters(syncGroups, syncDomains, syncGroupOfNode):
            ioSccs.append(scc)

    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        assert not self.ioSccs  # and not self.syncUses, "Must be run only once."
        # The naive discovery algorithm for the sync associated to IO operation mapping has O(|nodes|*|edges|) time complexity.
        # Commonly the |nodes| > 10k and |edges| > 30K, that said the time complexity is prohibitively large.
        # The |HlsNetNodeExplicitSync| << |HlsNetNode| from this reason we start search at HlsNetNodeExplicitSync
        # and walk only in the direction to a read (defs).

        # :note: If the value for read is not in the dict it means that there is no extra sync for this read.
        self._discoverSyncAssociationsDefToUse(netlist)
        self._discoverSyncDomains()

