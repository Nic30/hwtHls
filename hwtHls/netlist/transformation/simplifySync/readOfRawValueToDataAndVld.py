from typing import Set

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bitsVal import BitsVal
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn, \
    unlink_hls_nodes, link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf, \
    replaceOperatorNodeWith


def netlistReadOfRawValueToDataAndVld(n: HlsNetNodeRead, worklist: UniqList[HlsNetNode],
                                            removed: Set[HlsNetNode]):
    """
    try convert uses of "rawValue" to uses of "dataOut" and "valid" outputs
    raw value is expected to be in format Concat(_validNB, _valid, dataOut) (_validNB as MSB)
    """
    rawValueO: HlsNetNodeOut = n._rawValue
    assert rawValueO is not None, n
    rawUses = n.usedBy[rawValueO.out_i]
    dataValueO = n._outputs[0]
    dataWidth = n._outputs[0]._dtype.bit_length()
    modified = False
    for u in tuple(rawUses):
        u: HlsNetNodeIn
        uObj: HlsNetNode = u.obj
        if isinstance(uObj, HlsNetNodeOperator) and uObj.operator == AllOps.INDEX and rawValueO is uObj.dependsOn[0]:
            i = getConstDriverOf(uObj._inputs[1])
            if i is not None:
                iVal = i.val  # index of selected bit
                # reachDb.addAllUsersToInDepChange(uObj)
                if isinstance(iVal, (BitsVal, int)):
                    iVal = int(iVal)
                    if dataWidth == iVal:
                        # is selecting _valid port
                        if n._isBlocking:
                            vld = n.getValid()
                        else:
                            vld = n.getValidNB()

                        replaceOperatorNodeWith(uObj, vld, worklist, removed)
                    
                    elif dataWidth + 1 == iVal:
                        # is selecting _validNB port
                        replaceOperatorNodeWith(uObj, n._validNB, worklist, removed)

                    else:
                        # is selecting data port
                        if dataWidth == 1:
                            assert iVal == 0
                            # remove index because it is just 1b
                            replaceOperatorNodeWith(uObj, dataValueO, worklist, removed)
                        else:
                            assert iVal < dataWidth
                            # keep index operator but reconnect to data port
                            unlink_hls_nodes(rawValueO, u)
                            link_hls_nodes(dataValueO, u)
                else:
                    assert isinstance(iVal, slice), iVal
                    assert int(iVal.step) == -1, iVal
                    highBitNo = int(iVal.start)
                    lowBitNo = int(iVal.stop)
                    if highBitNo <= dataWidth:
                        if lowBitNo == 0 and highBitNo == dataWidth:
                            # exactly selecting data port
                            replaceOperatorNodeWith(uObj, n._outputs[0], worklist, removed)
                        else:
                            # indexing on data part
                            # keep index operator but reconnect to data port
                            unlink_hls_nodes(rawValueO, u)
                            link_hls_nodes(dataValueO, u)

                    elif lowBitNo == dataWidth and highBitNo == dataWidth + 1:
                        # exactly selecting _valid port
                        if n._isBlocking:
                            vld = n.getValid()
                        else:
                            vld = n.getValidNB()
                        replaceOperatorNodeWith(uObj, vld, worklist, removed)
                
                    elif lowBitNo == dataWidth + 1 and highBitNo == dataWidth + 2:
                        # exactly selecting _validNB port
                        replaceOperatorNodeWith(uObj, n._validNB, worklist, removed)

                    else:
                        raise NotImplementedError("Index overlaps data, _valid, _validNB port boundary in rawValue, split to 2x index + concat")    

                modified = True
                # reachDb.addOutUseChange(uObj)
                # reachDb.addOutUseChange(n)
    if not rawUses:
        n._removeOutput(n._rawValue.out_i)
    # if modified:
    #    reachDb.commitChanges(removed)
    return modified
