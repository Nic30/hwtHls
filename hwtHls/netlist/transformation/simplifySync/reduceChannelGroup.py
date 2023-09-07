from typing import List, Tuple

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeWriteAnyChannel, \
    LoopChanelGroup, LOOP_CHANEL_GROUP_ROLE
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HdlType_isVoid


def netlistTryRemoveChannelGroup(chGroup: LoopChanelGroup,
                                 worklist: UniqList[HlsNetNode]):
    if len(chGroup.members) != 1:
        return False
    builder = chGroup.members[0].netlist.builder

    chGroup: LoopChanelGroup
    connectedLoopsToRm: List[Tuple[LoopChanelGroup, LOOP_CHANEL_GROUP_ROLE]] = []
    for loopAndRole in chGroup.connectedLoops:
        loop, role = loopAndRole
        loop: HlsNetNodeLoopStatus
        role: LOOP_CHANEL_GROUP_ROLE
        toRm = []
        assert loop._bbNumberToPorts, (loop, "Loop must always have some channels to implement its functionality")
        srcDst, outPort = loop._findLoopChannelIn_bbNumberToPorts(chGroup)

        if role in (LOOP_CHANEL_GROUP_ROLE.ENTER, LOOP_CHANEL_GROUP_ROLE.REENTER):
            assert outPort is not None
            uses = loop.usedBy[outPort.out_i]
            if uses:
                # if it is only enter, and there are no data, we can execute loop automatically directly after loop ended
                if chGroup in loop.fromEnter and len(loop.fromEnter) == 1:
                    exits = loop.fromExitToHeaderNotify
                    if exits:
                        # implicit enter = enter on any exit
                        enterReplacement = builder.buildOrVariadic(tuple(e.getChannelWhichIsUsedToImplementControl().associatedRead.getValidNB() for e in exits))
                        e0: HlsNetNodeWriteBackedge = exits[0].getChannelWhichIsUsedToImplementControl()
                        assert HdlType_isVoid(e0.associatedRead._outputs[0]._dtype), (e0, "This must be of void type because it only triggers the loop exit")
                        assert not e0.channelInitValues, (e0, e0.channelInitValues)
                        e0.channelInitValues = ((),)
                        loop._isEnteredOnExit = True

                    else:
                        # build enter = not any(reenter)
                        # or  enter = 1 if len(reenter) == 0
                        reenters = []
                        for e in loop.fromReenter:
                            found = False
                            for (pn, op) in loop._bbNumberToPorts.values():
                                if pn is e:
                                    reenters.append(op)
                                    found = True
                                    break
                            assert found
                        if reenters:
                            enterReplacement = builder.buildNot(builder.buildOrVariadic(reenters))
                        else:
                            enterReplacement = builder.buildConstBit(1)

                    builder.replaceOutput(outPort, enterReplacement, True)

                    busyO = loop.getBusyOutPort()
                    if loop.usedBy[busyO.out_i]:
                        # this loop is always busy and this node will probably be removed in next step of optimization
                        builder.replaceOutput(busyO, builder.buildConstBit(1), True)
                    loop.fromEnter.clear()
                else:
                    raise NotImplementedError(loop, srcDst, chGroup)

            assert not loop.usedBy[outPort.out_i], ("If port should be removed it should be disconnected first", outPort)
            loop._removeOutput(outPort.out_i)

        elif role == LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER:
            raise NotImplementedError()

        toRm.append(srcDst)
        connectedLoopsToRm.append(loopAndRole)

        for srcDst in toRm:
            loop._bbNumberToPorts.pop(srcDst)

        worklist.append(loop)

    for loopAndRole in connectedLoopsToRm:
        chGroup.connectedLoops.remove(loopAndRole)

    return bool(connectedLoopsToRm)

