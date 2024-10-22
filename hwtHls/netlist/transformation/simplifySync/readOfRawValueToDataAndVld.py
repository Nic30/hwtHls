from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import _replaceOutPortWith
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith


def netlistReadOfRawValueToDataAndVld(n: HlsNetNodeRead, worklist: SetList[HlsNetNode]):
    """
    try convert uses of "rawValue" to uses of "dataOut" and "valid" outputs
    raw value is expected to be in format Concat(_validNB, _valid, dataOut) (_validNB as MSB)
    """
    rawValueO: HlsNetNodeOut = n._rawValue
    assert rawValueO is not None, n
    rawUses = n.usedBy[rawValueO.out_i]
    dataValueO = n._portDataOut
    dataWidth = dataValueO._dtype.bit_length()
    modified = False
    for u in tuple(rawUses):
        u: HlsNetNodeIn
        uObj: HlsNetNode = u.obj
        if isinstance(uObj, HlsNetNodeOperator) and uObj.operator == HwtOps.INDEX and rawValueO is uObj.dependsOn[0]:
            i = getConstDriverOf(uObj._inputs[1])
            if i is not None:
                iVal = i.val  # index of selected bit
                # reachDb.addAllUsersToInDepChange(uObj)
                if isinstance(iVal, (HBitsConst, int)):
                    iVal = int(iVal)
                    if dataWidth == iVal:
                        # is selecting _valid port
                        if n._isBlocking:
                            vld = n.getValid()
                        else:
                            vld = n.getValidNB()

                        replaceOperatorNodeWith(uObj, vld, worklist)

                    elif dataWidth + 1 == iVal:
                        # is selecting _validNB port
                        replaceOperatorNodeWith(uObj, n._validNB, worklist)

                    else:
                        # is selecting data port
                        if dataWidth == 1:
                            assert iVal == 0
                            # remove index because it is just 1b
                            replaceOperatorNodeWith(uObj, dataValueO, worklist)
                        else:
                            assert iVal < dataWidth
                            # keep index operator but reconnect to data port
                            u.disconnectFromHlsOut(rawValueO)
                            dataValueO.connectHlsIn(u)
                else:
                    assert isinstance(iVal, slice), iVal
                    assert int(iVal.step) == -1, iVal
                    highBitNo = int(iVal.start)
                    lowBitNo = int(iVal.stop)
                    if highBitNo <= dataWidth:
                        if lowBitNo == 0 and highBitNo == dataWidth:
                            # exactly selecting data port
                            replaceOperatorNodeWith(uObj, n._portDataOut, worklist)
                        else:
                            # indexing on data part
                            # keep index operator but reconnect to data port
                            u.disconnectFromHlsOut(rawValueO)
                            dataValueO.connectHlsIn(u)

                    elif lowBitNo == dataWidth and highBitNo == dataWidth + 1:
                        # exactly selecting _valid port
                        if n._isBlocking:
                            vld = n.getValid()
                        else:
                            vld = n.getValidNB()
                        replaceOperatorNodeWith(uObj, vld, worklist)

                    elif lowBitNo == dataWidth + 1 and highBitNo == dataWidth + 2:
                        # exactly selecting _validNB port
                        replaceOperatorNodeWith(uObj, n._validNB, worklist)

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
