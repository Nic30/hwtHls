from typing import List

from hwtHls.netlist.nodes.io import HlsExplicitSyncNode, HlsRead, HlsWrite
from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwtHls.netlist.transformations.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassMergeExplicitSync(HlsNetlistPass):
    """
    Merge nodes with explicit synchronization (HlsRead, HlsWrite, HlsExplicitSyncNode) together
    if possible to reduce the number of places where we need to solve the synchronisation.
    """

    @staticmethod
    def _apply(nodes: List[AbstractHlsOp]):
        to_rm = set()
        for n in nodes:
            if n not in to_rm and isinstance(n, HlsExplicitSyncNode):
                n: HlsExplicitSyncNode
                dep0 = n.dependsOn[0].obj
                # merge sync to previous object if possible
                if isinstance(dep0, HlsRead) and len(dep0.usedBy[0]) == 1:
                    # check if we did not generate cycle because sync was dependent on value of previous read
                    dep0: HlsRead
                    if n.extraCond is not None:
                        n.extraCond.obj.usedBy[n.extraCond.out_i].remove(n._inputs[n.extraCond_inI])
                        dep0.add_control_extraCond(n.extraCond)
                        
                    if n.skipWhen is not None:
                        n.skipWhen.obj.usedBy[n.skipWhen.out_i].remove(n._inputs[n.skipWhen_inI])
                        dep0.add_control_skipWhen(n.skipWhen)
                    # transfer output from this HlsExplicitSyncNode to HlsRead (to avoid modificaion of potentially unknown objects behind HlsExplicitSyncNode)
                    dep0._outputs = n._outputs
                    for o in dep0._outputs:
                        o.obj = dep0
                    assert len(n.usedBy) == 1, (n, n.usedBy)
                    dep0.usedBy[0] = n.usedBy[0]

                    to_rm.add(n)
                else:
                    # merge into successor if possible
                    sucs = n.usedBy[0]
                    if len(sucs) == 1:
                        suc0 = sucs[0].obj
                        if isinstance(suc0, HlsExplicitSyncNode):
                            raise NotImplementedError()
                        elif isinstance(suc0, HlsWrite):
                            raise NotImplementedError()

        if to_rm:
            nodes[:] = [
                n for n in nodes
                if (n not in to_rm)
            ]

    def apply(self, hls: "HlsStreamProc", to_hw: "SsaSegmentToHwPipeline"):
        self._apply(to_hw.hls.nodes)
