from typing import Set

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge, BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.loopChannelGroup import LoopChanelGroup, \
    LOOP_CHANEL_GROUP_ROLE, HlsNetNodeReadAnyChannel
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, unlink_hls_nodes
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain


def _replaceOutPortWith1(o: HlsNetNodeOut, worklist: SetList[HlsNetNode]):
    n = o.obj
    b: HlsNetlistBuilder = n.netlist.builder
    uses = n.usedBy[o.out_i]
    if uses:
        for u in uses:
            worklist.append(u.obj)
        b.replaceOutput(o, b.buildConstBit(1), True)
        return True
    return False


def _replaceOutPortWith(o: HlsNetNodeOut, replacementO: HlsNetNodeOut, worklist: SetList[HlsNetNode]):
    n = o.obj
    b: HlsNetlistBuilder = n.netlist.builder
    uses = n.usedBy[o.out_i]
    if uses:
        for u in uses:
            worklist.append(u.obj)
        b.replaceOutput(o, replacementO, True)
        return True
    return False


def netlistReduceLoopWithoutEnterAndExit(dbgTracer: DebugTracer, n: HlsNetNodeLoopStatus,
                                         worklist: SetList[HlsNetNode],
                                         removed: Set[HlsNetNode]):
    modified = False

    if not n.fromReenter:
        raise AssertionError("This loop has no reenter, this means this is not a loop and it should not be constructed"
                             " or it should have been removed when reenter was removed.")

    elif not n.fromEnter and not n.fromExitToHeaderNotify:
        # this loop is running forever, no busy flag is required
        busyO = n.getBusyOutPort()
        modified |= _replaceOutPortWith1(busyO, worklist)

        if len(n.fromReenter) == 1:
            # there is only 1 place for reenterthe reenter en port on loop is useless
            reG: LoopChanelGroup = n.fromReenter[0]
            reG.connectedLoops.remove((n, LOOP_CHANEL_GROUP_ROLE.REENTER))
            if not reG.connectedLoops:
                reG.destroy()

            srcDst, outPort = n._findLoopChannelIn_bbNumberToPorts(reG)
            n._bbNumberToPorts.pop(srcDst)
            reGControlR = reG.getChannelWhichIsUsedToImplementControl().associatedRead
            modified |= _replaceOutPortWith(outPort, reGControlR.getValidNB(), worklist)
            n._removeOutput(outPort.out_i)
            n.fromReenter.clear()
            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, worklist)
            assert not n._bbNumberToPorts, (n, n._bbNumberToPorts)
            removed.add(n)
            modified = True

    elif not n.fromEnter and len(n.fromReenter) == 1 and (not n.fromExitToHeaderNotify or n._isEnteredOnExit):
        # the loop control is useless because this loop is always running and is constantly re-executing itself
        # and there is no arbitration of inputs nor blocking until current body finishes
        builder: HlsNetlistBuilder = n.netlist.builder

        reenterG: LoopChanelGroup = n.fromReenter[0]
        srcDst, fromStatusOut = n._findLoopChannelIn_bbNumberToPorts(reenterG)
        reenterControl: HlsNetNodeReadAnyChannel = reenterG.getChannelWhichIsUsedToImplementControl().associatedRead
        _replaceOutPortWith(fromStatusOut, reenterControl.getValidNB(), worklist)
        if not reenterControl._isBlocking:
            reenterControl._isBlocking = True
        reenterG.connectedLoops.remove((n, LOOP_CHANEL_GROUP_ROLE.REENTER))
        if not reenterG.connectedLoops:
            reenterG.destroy()

        if n.fromExitToHeaderNotify:
            # unregister loop from channel
            assert len(n.fromExitToHeaderNotify) == 1, n
            exitG: LoopChanelGroup = n.fromExitToHeaderNotify[0]
            exitG.connectedLoops.remove((n, LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER))
            # avoid wait on reenter when exit
            exitW: HlsNetNodeWriteBackedge = exitG.getChannelWhichIsUsedToImplementControl()
            # promote to a regular channel with an init
            exitW.allocationType = BACKEDGE_ALLOCATION_TYPE.BUFFER 
            assert not exitW.channelInitValues, ("EXIT_NOTIFY_TO_HEADER should never have init value", exitW, exitW.channelInitValues)
            assert HdlType_isVoid(exitW._outputs[0]._dtype), exitW
            exitW.channelInitValues = (tuple(),) # add one token to start the loop 
            exitR: HlsNetNodeReadBackedge = exitW.associatedRead
            assert not exitR._isBlocking, exitR
            exitR._isBlocking = True

            reenterControl.addControlSerialSkipWhen(builder.buildNot(exitR.getValidNB()))

            # disconnect loop status port for exit input
            srcDst, exitInOnStatus = n._findLoopChannelIn_bbNumberToPorts(exitG)
            unlink_hls_nodes(exitR.getValidNB(), exitInOnStatus)

            if not exitG.connectedLoops:
                exitG.destroy()

            for exitToSucG in n.fromExitToSuccessor:
                exitToSucG: LoopChanelGroup
                exitToSucG.connectedLoops.remove((n, LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR))
                if not exitToSucG.connectedLoops:
                    exitToSucG.destroy()

        netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, worklist)
        removed.add(n)
        modified = True

    elif not n.fromEnter and len(n.fromReenter) == 1 and len(n.fromExitToHeaderNotify) == 1 and n._isEnteredOnExit:
        # has 2 real channels which can execute lopp 1 reenter, 1 enter from exit
        # 2 execute channels are beneficial to realize without the loop as the flags for enable from reenter/enter predecessors
        # are just 1 flag and its negation
        raise NotImplementedError(n)

    return modified
