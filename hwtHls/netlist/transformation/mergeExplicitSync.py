from typing import List

from hwtHls.netlist.nodes.io import HlsNetNodeExplicitSync, HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.ops import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassMergeExplicitSync(HlsNetlistPass):
    """
    Merge nodes with explicit synchronization (HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeExplicitSync) together
    if possible to reduce the number of places where we need to solve the synchronisation.
    """

    @staticmethod
    def _apply(nodes: List[HlsNetNode]):
        to_rm = set()
        for n in nodes:
            if n not in to_rm and isinstance(n, HlsNetNodeExplicitSync):
                n: HlsNetNodeExplicitSync
                dep0 = n.dependsOn[0].obj
                # merge sync to previous object if possible
                if isinstance(dep0, HlsNetNodeRead) and len(dep0.usedBy[0]) == 1:
                    # check if we did not generate cycle because sync was dependent on value of previous read
                    dep0: HlsNetNodeRead
                    if n.extraCond is not None:
                        n.extraCond.obj.usedBy[n.extraCond.out_i].remove(n._inputs[n.extraCond_inI])
                        dep0.add_control_extraCond(n.extraCond)
                        
                    if n.skipWhen is not None:
                        n.skipWhen.obj.usedBy[n.skipWhen.out_i].remove(n._inputs[n.skipWhen_inI])
                        dep0.add_control_skipWhen(n.skipWhen)
                    # transfer output from this HlsNetNodeExplicitSync to HlsNetNodeRead (to avoid modificaion of potentially unknown objects behind HlsNetNodeExplicitSync)
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
                        if isinstance(suc0, HlsNetNodeExplicitSync):
                            raise NotImplementedError()
                        elif isinstance(suc0, HlsNetNodeWrite):
                            raise NotImplementedError()

        if to_rm:
            nodes[:] = [
                n for n in nodes
                if (n not in to_rm)
            ]

    def apply(self, hls: "HlsStreamProc", to_hw: "SsaSegmentToHwPipeline"):
        self._apply(to_hw.hls.nodes)
