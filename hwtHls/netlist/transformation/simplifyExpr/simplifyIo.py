from typing import Set

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith, \
    disconnectAllInputs


def netlistReduceReadReadSyncWithReadOfValidNB(n: HlsNetNodeRead,
                                               worklist: SetList[HlsNetNode],
                                               removed: Set[HlsNetNode]):
    rs = n._associatedReadSync
    if rs:
        if rs.usedBy[0]:
            # replace _associatedReadSync with _validNB
            vld = n.getValidNB()
            replaceOperatorNodeWith(rs, vld, worklist, removed)
        else:
            # remove _associatedReadSync
            disconnectAllInputs(rs, worklist)
        
        n._associatedReadSync = None
        removed.add(rs)
        return True

    else:
        return False
