from typing import List

from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwtHls.netlist.nodes.io import HlsExplicitSyncNode, HlsRead, HlsWrite


def merge_explicit_sync(nodes: List[AbstractHlsOp]):
    to_rm = set()
    for n in nodes:
        if n not in to_rm and isinstance(n, HlsExplicitSyncNode):
            n: HlsExplicitSyncNode
            dep0 = n.dependsOn[0].obj
            # merge sync to previous object if possible
            if isinstance(dep0, HlsRead) and len(dep0.usedBy[0]) == 1:
                # check if we did not generate cycle because sync was dependent on value of previous read
                dep0: HlsRead
                dep0.add_control_extraCond(n.extraCond)
                # transfer output from this HlsExplicitSyncNode to HlsRead (to avoid modificaion of potentially unknown objects behind HlsExplicitSyncNode)
                dep0._outputs = n._outputs
                for o in dep0._outputs:
                    o.obj = dep0
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
