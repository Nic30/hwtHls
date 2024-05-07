from hwtHls.netlist.analysis.betweenSyncIslands import BetweenSyncIsland, \
    HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync


def isDrivenFromSyncIsland(node: HlsNetNodeExplicitSync,
                           syncIsland: BetweenSyncIsland,
                           syncIslands: HlsNetlistAnalysisPassBetweenSyncIslands) -> bool:
    for dep in node.dependsOn:
        if HdlType_isNonData(dep._dtype):
            continue
        else:
            isl = syncIslands.syncIslandOfNode[dep.obj]
            if isl is syncIsland or (isinstance(isl, tuple) and (isl[0] is syncIsland or isl[1] is syncIsland)):
                return True
    return False
