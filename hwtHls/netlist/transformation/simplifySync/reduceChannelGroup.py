from typing import List, Tuple

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.loopChannelGroup import LoopChanelGroup, LOOP_CHANEL_GROUP_ROLE
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


def netlistTryRemoveChannelGroup(dbgTracer: DebugTracer, chGroup: LoopChanelGroup,
                                 worklist: SetList[HlsNetNode]):
    
    
    assert chGroup.members, ("If it has no members it should already be removed", chGroup)
    return False # control group can not probably be removed on its own. It probably must be always removed
    # together all of its users
    #if len(chGroup.members) != 1:
    #    return False # can not remove because this group has multiple channels synchronized between other
    #
    #w: HlsNetNodeWrite = chGroup.members[0]
    #if not HdlType_isVoid(w.dependsOn[w._portSrc.in_i]._dtype):
    #    return False # can not remove because this group transfers data
    #if w.associatedRead.channelInitValues:
    #    return False # can not remove because it holds intial state
    #
    #builder = chGroup.members[0].getHlsNetlistBuilder()
    #chGroup: LoopChanelGroup
    #connectedLoopsAndBlocksToRm: List[Tuple[LoopChanelGroup, LOOP_CHANEL_GROUP_ROLE]] = []
    ## check if it is necessary for loops to work
    #for loopAndRole in chGroup.connectedLoopsAndBlocks:
    #    loop, role = loopAndRole
    #    loop: HlsNetNodeLoopStatus
    #    role: LOOP_CHANEL_GROUP_ROLE
    #    toRm = []
    #    assert loop._bbNumberToPorts, (loop, "Loop must always have some channels to implement its functionality")
    #    srcDst, loopEnOutPort = loop._findLoopChannelIn_bbNumberToPorts(chGroup)
    #    with dbgTracer.scoped(netlistTryRemoveChannelGroup, loop):
    #        if role in (LOOP_CHANEL_GROUP_ROLE.ENTER,
    #                    LOOP_CHANEL_GROUP_ROLE.REENTER):
    #            # ENTER/REENTER channels can be removed if it can be proven that they are
    #            # complementary to some other channel
    #            assert loopEnOutPort is not None
    #            uses = loop.usedBy[loopEnOutPort.out_i]
    #            if uses:
    #                # if it is only enter, and there are no data, we can execute loop automatically directly after loop ended
    #                exits = loop.fromExitToHeaderNotify
    #                if len(loop.fromEnter) == 1 and len(exits) <= 1 and chGroup in loop.fromEnter:
    #                    # 1 enter, 0 or 1 exit
    #                    if exits:
    #                        # implicit enter = enter on any exit
    #                        enterReplacement = builder.buildConstBit(1)  # exits[0].getChannelUsedAsControl().associatedRead.getValidNB()
    #                        e0: HlsNetNodeWriteBackedge = exits[0].getChannelUsedAsControl()
    #                        assert HdlType_isVoid(e0.associatedRead._portDataOut._dtype), (e0, "This must be of void type because it only triggers the loop exit")
    #                        assert not e0.associatedRead.channelInitValues, (e0, e0.associatedRead.channelInitValues)
    #                        assert e0.allocationType == CHANNEL_ALLOCATION_TYPE.IMMEDIATE
    #                        # e0.allocationType = CHANNEL_ALLOCATION_TYPE.BUFFER
    #                        # e0.associatedRead.channelInitValues = ((),)
    #                        loop._isEnteredOnExit = True
    #                        dbgTracer.log(("rm enter, isEnteredOnExit=True", chGroup))
    #
    #                    else:
    #                        # build enter = not any(reenter)
    #                        # or  enter = 1 if len(reenter) == 0
    #                        reenters = []
    #                        for e in loop.fromReenter:
    #                            found = False
    #                            for (pn, op) in loop._bbNumberToPorts.values():  # [todo] maybe non deterministic
    #                                if pn is e:
    #                                    reenters.append(op)
    #                                    found = True
    #                                    break
    #                            assert found
    #                        if reenters:
    #                            enterReplacement = builder.buildNot(builder.buildOrVariadic(reenters))
    #                            dbgTracer.log(("rm enter, enter=not any(reenter)", chGroup))
    #                        else:
    #                            enterReplacement = builder.buildConstBit(1)
    #                            dbgTracer.log(("rm enter, enter=1", chGroup))
    #
    #                    builder.replaceOutput(loopEnOutPort, enterReplacement, True)
    #
    #                    busyO = loop.getBusyOutPort()
    #                    if loop.usedBy[busyO.out_i]:
    #                        # this loop is always busy and this node will probably be removed in next step of optimization
    #                        builder.replaceOutput(busyO, builder.buildConstBit(1), True)
    #                    loop.fromEnter.clear()
    #                else:
    #                    raise NotImplementedError(loop, srcDst, chGroup)
    #            else:
    #                dbgTracer.log(("rm enter, loop en out unused", chGroup))
    #
    #            assert not loop.usedBy[loopEnOutPort.out_i], (
    #                "If port should be removed it should be disconnected first", loopEnOutPort)
    #            loop._removeOutput(loopEnOutPort.out_i)
    #
    #        elif role == LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER:
    #            raise NotImplementedError()
    #
    #        toRm.append(srcDst)
    #        connectedLoopsAndBlocksToRm.append(loopAndRole)
    #
    #        for srcDst in toRm:
    #            loop._bbNumberToPorts.pop(srcDst)
    #
    #        worklist.append(loop)
    #
    #for loopAndRole in connectedLoopsAndBlocksToRm:
    #    chGroup.connectedLoopsAndBlocks.remove(loopAndRole)
    #
    #return bool(connectedLoopsAndBlocksToRm)

