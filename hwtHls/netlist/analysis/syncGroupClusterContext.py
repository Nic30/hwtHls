from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
from typing import List, Dict, Set, Tuple, Generator, Union

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from itertools import chain

HlsNetNodeAnySync = Union[HlsNetNodeExplicitSync, HlsNetNodeLoopStatus]
SyncGroupLabel = Tuple[HlsNetNodeAnySync, ...]


class SyncGroupClusterContext():

    def __init__(self, syncOfNode: Dict[HlsNetNode, Set[HlsNetNodeAnySync]]):
        self.syncOfNode = syncOfNode

    def resolveSyncGroups(self):
        # :note: every input/output should have some sync group because it must be connected
        # to some IO (transitively)

        syncGroups: Dict[SyncGroupLabel, UniqList[HlsNetNode]] = {}
        syncGroupOfNode: Dict[HlsNetNode, SyncGroupLabel] = {}
        for n, syncGroupSet in self.syncOfNode.items():
            if not syncGroupSet:
                continue

            assert syncGroupSet, (n, syncGroupSet,)
            syncGroupLabel = tuple(sorted(syncGroupSet, key=lambda n: n._id))
            groupNodes = syncGroups.get(syncGroupLabel, None)
            if groupNodes is None:
                groupNodes = syncGroups[syncGroupLabel] = UniqList()
            groupNodes.append(n)
            syncGroupOfNode[n] = syncGroupLabel
        return syncGroups, syncGroupOfNode

    def _copySyncGroupToDiGraph(self, g:DiGraph, nodes: UniqList[HlsNetNode]) -> Generator[HlsNetNode, None, None]:
        g.add_nodes_from(nodes)
        allNodes = g.nodes
        for n0 in nodes:
            for dep in n0.dependsOn:
                n1 = dep.obj
                if n1 in allNodes:
                    g.add_edge(n1, n0)
                else:
                    yield n1

            for uses0 in n0.usedBy:
                for u in uses0:
                    u: HlsNetNodeIn
                    n1 = u.obj
                    if n1 not in allNodes:
                        # found something out of this cluster, yield for external decision if copy should continue there
                        yield n1
                    else:
                        g.add_edge(n0, n1)

    def _copySyncGroupToDiGraphFlodding(self,
                                        syncGroupLabel: SyncGroupLabel,
                                        syncGroupNodes: UniqList[HlsNetNode],
                                        syncGroups: Dict[SyncGroupLabel, UniqList[HlsNetNode]],
                                        syncGroupOfNode: Dict[HlsNetNode, SyncGroupLabel],
                                        resolvedGroups: Set[SyncGroupLabel]):
        """
        :param resolvedGroups: groups which were discovered previously and are definitely not tied to current cluster
            because if this was the case this group would already have been in seen as well
        """
        g = DiGraph()
        tiedGroups: List[SyncGroupLabel] = []

        groupsToCollect = [(syncGroupLabel, syncGroupNodes)]
        while groupsToCollect:
            label, nodes = groupsToCollect.pop()
            resolvedGroups.add(label)
            labelAsSet = set(label)
            seenGroups: Set[SyncGroupLabel] = set()
            tiedGroups.append(label)
            # syncGroup may be tied with its neighbors
            # search only in def->use direction
            for externNode in self._copySyncGroupToDiGraph(g, nodes):
                conectedGroupLabel = syncGroupOfNode.get(externNode, None)
                if conectedGroupLabel is None or conectedGroupLabel in seenGroups or conectedGroupLabel in resolvedGroups:
                    continue
                seenGroups.add(conectedGroupLabel)
                # if group intersect in at least a single item it means that this group is tied trough the sync
                if labelAsSet.isdisjoint(set(conectedGroupLabel)):
                    continue
                groupsToCollect.append((conectedGroupLabel, syncGroups[conectedGroupLabel]))
        return g, tiedGroups

    def mergeSyncGroupsToClusters(self,
                                  syncGroups: Dict[SyncGroupLabel, UniqList[HlsNetNode]],
                                  syncGroupsSorted: List[Tuple[SyncGroupLabel, UniqList[HlsNetNode]]],
                                  syncGroupOfNode: Dict[HlsNetNode, SyncGroupLabel]):
        # sync groups are scope of unique reach of sync nodes, some of them may be tied in the IO SCC
        # this dictionary is used to keep track of this association, key is the label of the group and value (if present)
        # is some tied group label which was picked as a representator of this cluster because it was found first
        resolvedSyncGroups: Set[SyncGroupLabel] = set()
        for syncGroupLabel, syncGroupNodes in syncGroupsSorted:
            syncGroupLabel: SyncGroupLabel
            syncGroupNodes: UniqList[HlsNetNode]
            if syncGroupLabel in resolvedSyncGroups:
                continue
            g, tiedGroups = self._copySyncGroupToDiGraphFlodding(syncGroupLabel, syncGroupNodes, syncGroups, syncGroupOfNode, resolvedSyncGroups)
            resolvedSyncGroups.update(tiedGroups)
            # once all sync group clusters are resolved we connect all explicit sync with all reachable
            # reads so we create a cycle in the graph  whenever there is a read connected to sync transitively

            # add edge from sync back to read/write to mark they are in same SCC
            for op in tuple(g.nodes):
                if isinstance(op, HlsNetNodeExplicitSync):
                    op: HlsNetNodeExplicitSync

                    for extraSync in syncGroupOfNode[op]:
                        if extraSync is op:
                            # skip because this edge is not necessary because 1 node is SCC by def.
                            continue

                        g.add_edge(extraSync, op)

                    if op._associatedReadSync is not None:
                        g.add_edge(op._associatedReadSync, op)

                elif isinstance(op, HlsNetNodeLoopStatus):
                    op: HlsNetNodeLoopStatus
                    for extraSync in syncGroupOfNode[op]:
                        if extraSync is op:
                            # skip because this edge is not necessary because 1 node is SCC by def.
                            continue

                        g.add_edge(extraSync, op)
                    for e in chain(op.fromEnter, op.fromReenter, op.fromExitToHeaderNotify):
                        # add edge to enter reads so they are in same SCC
                        g.add_edge(e.getChannelWhichIsUsedToImplementControl().associatedRead, op)

            # build a cycle on all IO which is using same sync
            # for users in usersOfSync.values():
            #    if len(users) > 1:
            #        userIt = iter(users)
            #        firstUser = next(userIt)
            #        lastUser = firstUser
            #        for u in users:
            #            g.add_edge(lastUser, u)
            #            lastUser = u
            #
            #        g.add_edge(lastUser, firstUser)

            for ioScc in strongly_connected_components(g):
                ioScc: Set[HlsNetNode]
                # if it is worth extracting
                if len(ioScc) > 1:
                    _ioScc = UniqList(sorted(ioScc, key=lambda n: n._id))
                    # privatize constants to reduce number of ports
                    usedConstants = []
                    for n in _ioScc:
                        for dep in n.dependsOn:
                            if isinstance(dep.obj, HlsNetNodeConst) and len(dep.obj.usedBy[0]) == 1:
                                # assert len(dep.obj.usedBy[0]) == 1, dep.obj.usedBy
                                usedConstants.append(dep.obj)

                    _ioScc.extend(usedConstants)
                    yield _ioScc

