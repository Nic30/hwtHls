from itertools import chain
from typing import List

from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassMergeExplicitSync(HlsNetlistPass):
    """
    Merge nodes with explicit synchronization (HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeExplicitSync) together
    if possible to reduce the number of places where we need to solve the synchronization.
    """
    
    @staticmethod
    def _trasferHlsNetNodeExplicitSyncFlags(src: HlsNetNodeExplicitSync, dst: HlsNetNodeExplicitSync):
        if src.extraCond is not None:
            ec = src.dependsOn[src.extraCond.in_i]
            ec.obj.usedBy[ec.out_i].remove(src.extraCond)
            dst.add_control_extraCond(ec)
            
        if src.skipWhen is not None:
            sw = src.dependsOn[src.skipWhen.in_i]
            sw.obj.usedBy[sw.out_i].remove(src.skipWhen)
            dst.add_control_skipWhen(sw)
        
        for orderIn in src.iterOrderingInputs():
            orderDep = src.dependsOn[orderIn.in_i]
            if orderDep.obj is not dst and not any(depOfDep is orderDep
                                                   for depOfDep in orderDep.obj.dependsOn):
                orderIn.obj = dst
                orderIn.in_i = len(dst._inputs)
                dst._inputs.append(orderIn)
                dst.dependsOn.append(orderDep)

    @classmethod
    def _apply(cls, nodes: List[HlsNetNode]):
        to_rm = set()
        for n in nodes:
            if n not in to_rm and n.__class__ is HlsNetNodeExplicitSync:
                n: HlsNetNodeExplicitSync
                dep0 = n.dependsOn[0].obj
                # merge sync to previous object if possible
                if isinstance(dep0, HlsNetNodeRead) and len(dep0.usedBy[0]) == 1:
                    # check if we did not generate cycle because sync was dependent on value of previous read
                    dep0: HlsNetNodeRead
                    cls._trasferHlsNetNodeExplicitSyncFlags(n, dep0)

                    # transfer output from this HlsNetNodeExplicitSync to HlsNetNodeRead (to avoid modificaion of potentially unknown objects behind HlsNetNodeExplicitSync)
                    dep0._outputs = n._outputs
                    for o in dep0._outputs:
                        o.obj = dep0
                    assert len(n.usedBy) == 2, (n, n.usedBy)
                    assert len(dep0.usedBy) == 2, (n, dep0.usedBy)
                    dep0.usedBy[0] = n.usedBy[0]
                    dep0.usedBy[1] = list(use for use in chain(dep0.usedBy[1], n.usedBy[1]) if use.obj is not n or dep0)

                    to_rm.add(n)
                else:
                    # merge this node into successor if possible
                    sucs = n.usedBy[0]
                    if len(sucs) == 1:
                        suc0: HlsNetNodeExplicitSync = sucs[0].obj
                        if isinstance(suc0, (HlsNetNodeExplicitSync, HlsNetNodeWrite)):
                            cls._trasferHlsNetNodeExplicitSyncFlags(n, suc0)
                            o = n.dependsOn[0]
                            prevI = n._inputs[0]
                            newI = suc0._inputs[0]
                            newI.replaceDriver(o)
                            o.obj.usedBy[0].remove(prevI)
                            to_rm.add(n)

        if to_rm:
            nodes[:] = [
                n for n in nodes
                if (n not in to_rm)
            ]

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        self._apply(netlist.nodes)
