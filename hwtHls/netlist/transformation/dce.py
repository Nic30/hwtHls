from itertools import chain
from typing import Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregatedBitwiseOps import HlsNetNodeBitwiseOps
from hwtHls.netlist.nodes.io import HlsNetNodeWrite, HlsNetNodeRead, HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopHeader import HlsLoopGate
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutLazy
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassDCE(HlsNetlistPass):
    """
    Dead Code Elimination for hls netlist

    :note: volatile IO operations are never removed
    """
    NON_REMOVABLE_CLS = (HlsNetNodeRead, HlsNetNodeWrite, HlsLoopGate, HlsNetNodeExplicitSync)

    def _walkDependencies(self, n: HlsNetNode, seen: Set[HlsNetNode]):
        seen.add(n)
        for dep in n.dependsOn:
            if isinstance(dep, HlsNetNodeOutLazy):
                raise AssertionError(self.__class__.__name__, "does not support", dep)
            if dep.obj not in seen:
                self._walkDependencies(dep.obj, seen)

    def _reduceCompositeNodeIo(self, n: HlsNetNodeBitwiseOps):
        usedNodes: Set[HlsNetNode] = set()
        newOuterOutputs = []
        newInternOutputs = UniqList()
        for outerOut, internOut in zip(n._outputs, n._subNodes.outputs):
            if n.usedBy[outerOut.out_i] and internOut.obj in n._subNodes.nodes:
                self._walkDependencies(internOut.obj, usedNodes)
                newOuterOutputs.append(outerOut)
                newInternOutputs.append(internOut)

        if len(newOuterOutputs) != len(n._outputs):
            if len(usedNodes) != len(n._subNodes.nodes):
                # some nodes were removed because their outputwas unused
                n._subNodes.nodes = UniqList(n for n in n._subNodes.nodes if n in usedNodes)
            # some output was removed because it was unused
            n._outputs = newOuterOutputs
            n._subNodes.outputs = newOuterOutputs
            # reindex outputs after modification
            for i, o in enumerate(n._outputs):
                o.out_i = i

            iDict = n._subNodes.inputDict
            for i in n._subNodes.inputs:
                internalUses = iDict[i]
                newUses = UniqList(u for u in internalUses if u.obj in usedNodes)
                if newUses:
                    iDict[i] = newUses
                else:
                    iDict.pop(i)

            anyInputRemoved = len(iDict) != len(n._subNodes.inputs)
            if anyInputRemoved:
                newOuterInputs = []
                newNodeInputs = []
                for (outerI, nodeI) in zip(n._subNodes.inputs, n._inputs):
                    if outerI in iDict:
                        outerI.obj.usedBy[outerI.out_i].remove(nodeI)
                        newOuterInputs.append(outerI)
                        newNodeInputs.append(nodeI)
                for ii, i in enumerate(newNodeInputs):
                    i.in_i = ii

                n._subNodes.inputs = newOuterInputs
                n._inputs = newNodeInputs
                allInputs = set(n._inputs)
                n.outerOutToIn = {o:i for o, i in n.outerOutToIn.items() if o in allInputs}

            n.internOutToOut = {intern:outer for intern, outer in  n.internOutToOut.items() if intern in n._subNodes.outputs}

            assert len(n._subNodes.outputs) == len(n._outputs)
            return anyInputRemoved

        return False

    def apply(self, hls:"HlsScope", netlist: HlsNetlistCtx):

        while True:
            used: Set[HlsNetNode] = set()
            # assert len(set(netlist.nodes)) == len(netlist.nodes)
            for io in chain(netlist.inputs, netlist.outputs, (
                    n for n in netlist.nodes 
                    if isinstance(n, self.NON_REMOVABLE_CLS))):
                self._walkDependencies(io, used)

            nodesWithReducedOutputs = []
            if len(used) != len(netlist.nodes) + len(netlist.inputs) + len(netlist.outputs):
                netlist.nodes = [n for n in netlist.nodes if n in used]
                for n in netlist.iterAllNodes():
                    n: HlsNetNode
                    # IO can not be reduced, but always update usedBy
                    outReduced = not isinstance(n, self.NON_REMOVABLE_CLS)
                    for i, uses in enumerate(n.usedBy):
                        newUses = [u for u in uses if u.obj in used]
                        n.usedBy[i] = newUses
                        outReduced &= not newUses
                    for dep in n.dependsOn:
                        assert dep.obj in used
                    # n.dependsOn = [d for d in n.dependsOn if d.obj in used]
                    if not outReduced:
                        nodesWithReducedOutputs.append(n)

            anyInputRemoved = False
            for n in nodesWithReducedOutputs:
                n: HlsNetNode
                if isinstance(n, HlsNetNodeBitwiseOps):
                    anyInputRemoved |= self._reduceCompositeNodeIo(n)

            if not anyInputRemoved:
                break
