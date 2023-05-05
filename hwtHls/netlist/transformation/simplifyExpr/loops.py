from typing import Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.builder import HlsNetlistBuilder


def netlistReduceLoopWithoutEnterAndExit(n: HlsNetNodeLoopStatus,
                                         worklist: UniqList[HlsNetNode],
                                         removed: Set[HlsNetNode]):
    if not n.fromEnter and not n.fromExit:
        bussyO = n.getBussyOutPort()
        if n.usedBy[bussyO.out_i]:
            b: HlsNetlistBuilder = n.netlist.builder
            for u in n.usedBy[bussyO.out_i]:
                worklist.append(u.obj)
            b.replaceOutput(bussyO, b.buildConstBit(1), True)
            return True
    return False
