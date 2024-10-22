from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith, \
    disconnectAllInputs


def netlistReduceReadReadSyncWithReadOfValidNB(n: HlsNetNodeRead,
                                               worklist: SetList[HlsNetNode]):
    rs = n._associatedReadSync
    if rs:
        if rs.usedBy[0]:
            # replace _associatedReadSync with _validNB
            vld = n.getValidNB()
            replaceOperatorNodeWith(rs, vld, worklist)
        else:
            # remove _associatedReadSync
            disconnectAllInputs(rs, worklist)
        
        n._associatedReadSync = None
        rs.markAsRemoved()
        return True

    else:
        return False
