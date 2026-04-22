from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import _replaceOutPortWith, HlsNetlistBuilder
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator, OP_INDEX_CONST
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
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
    if dataWidth == 0:
        assert rawValueO._dtype.bit_length() == 1, rawValueO
        if n._isBlocking:
            vld = n.getValid()
        else:
            vld = n.getValidNB()
        _replaceOutPortWith(rawValueO, vld, worklist)
        return

    for u in tuple(rawUses):
        u: HlsNetNodeIn
        uObj: HlsNetNode = u.obj
        if isinstance(uObj, HlsNetNodeOperator) and uObj.operator == OP_INDEX_CONST and rawValueO is uObj.dependsOn[0]:
            i = uObj.operatorSpecialization  # index of selected bit
            # reachDb.addAllUsersToInDepChange(uObj)
            if isinstance(i, int):
                if dataWidth == i:
                    # is selecting _valid port
                    if n._isBlocking:
                        vld = n.getValid()
                    else:
                        vld = n.getValidNB()

                    replaceOperatorNodeWith(uObj, vld, worklist)

                elif dataWidth + 1 == i:
                    # is selecting _validNB port
                    replaceOperatorNodeWith(uObj, n._validNB, worklist)

                else:
                    # is selecting data port
                    if dataWidth == 1:
                        assert i == 0
                        # remove index because it is just 1b
                        replaceOperatorNodeWith(uObj, dataValueO, worklist)
                    else:
                        assert i < dataWidth
                        # keep index operator but reconnect to data port
                        u.disconnectFromHlsOut(rawValueO)
                        dataValueO.connectHlsIn(u)
            else:
                assert isinstance(i, slice), uObj
                assert i.step == -1, uObj
                highBitNo = i.start
                lowBitNo = i.stop
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
                    replaceOperatorNodeWith(uObj, n.getValidNB(), worklist)

                else:
                    # Index overlaps data, _valid, _validNB port boundary in rawValue, split to index + concat
                    builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
                    replacement: list[HlsNetNodeOut] = []  # lsb first
                    if lowBitNo == 0:
                        replacement.append(dataValueO)
                    else:
                        _data = builder.buildIndexConstSlice(HBits(dataWidth - lowBitNo), dataValueO,
                                                             dataWidth, lowBitNo)

                        replacement.append(_data)
                    assert highBitNo > dataWidth

                    if n._isBlocking:
                        vld = n.getValid()
                    else:
                        vld = n.getValidNB()
                    replacement.append(vld)

                    if highBitNo == dataWidth + 2:
                        vld = n.getValidNB()
                        replacement.append(vld)
                    else:
                        assert highBitNo == dataWidth + 1, (n, dataWidth, lowBitNo, highBitNo)

                    replacement = builder.buildConcat(*replacement)
                    replaceOperatorNodeWith(uObj, replacement, worklist)

            modified = True
            # reachDb.addOutUseChange(uObj)
            # reachDb.addOutUseChange(n)
    if not rawUses:
        n._removeOutput(n._rawValue.out_i)
    # if modified:
    #    reachDb.commitChanges(removed)
    return modified
