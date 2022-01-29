from itertools import chain
from typing import Set

from hwtHls.netlist.nodes.io import HlsNetNodeWrite, HlsNetNodeRead, HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.ssa.translation.toHwtHlsNetlist.nodes.loopHeader import HlsLoopGate


class HlsNetlistPassDCE(HlsNetlistPass):
    """
    Dead Code Elimination for hls netlist
    :note: IO operations are never removed
    """

    def _walkDependencies(self, n: HlsNetNode, seen: Set[HlsNetNode]):
        seen.add(n)
        for dep in n.dependsOn:
            if dep.obj not in seen:
                self._walkDependencies(dep.obj, seen)

    def apply(self, hls:"HlsStreamProc", to_hw:"SsaSegmentToHwPipeline"):
        used: Set[HlsNetNode] = set()
        hlsPip = to_hw.hls
        # assert len(set(hlsPip.nodes)) == len(hlsPip.nodes)
        for io in chain(hlsPip.inputs, hlsPip.outputs, (n for n in hlsPip.nodes if isinstance(n, (HlsNetNodeRead, HlsNetNodeWrite, HlsLoopGate, HlsNetNodeExplicitSync)))):
            self._walkDependencies(io, used)
        
        if len(used) != len(hlsPip.nodes) + len(hlsPip.inputs) + len(hlsPip.outputs):
            hlsPip.nodes = [n for n in hlsPip.nodes if n in used]
            for n in hlsPip.nodes:
                n: HlsNetNode
                for i, uses in enumerate(n.usedBy):
                    n.usedBy[i] = [u for u in uses if u.obj in used] 
                n.dependsOn = [d for d in n.dependsOn if d.obj in used] 
