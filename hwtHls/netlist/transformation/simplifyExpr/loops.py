from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder, _replaceOutPortWith1
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.loopChannelGroup import LoopChanelGroup, \
    LOOP_CHANEL_GROUP_ROLE, HlsNetNodeReadAnyChannel
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain


def netlistReduceLoopWithoutEnterAndExit(dbgTracer: DebugTracer, n: HlsNetNodeLoopStatus,
                                         worklist: SetList[HlsNetNode]):
    modified = False

    with dbgTracer.scoped(netlistReduceLoopWithoutEnterAndExit, n):
        if not n.fromReenter:
            raise AssertionError("This loop has no reenter, this means this is not a loop and it should not be constructed"
                                 " or it should have been removed when reenter was removed.")
    
        elif not n.fromEnter and not n.fromExitToHeaderNotify:
            # this loop is running forever => no busy flag is required
            busyO = n.getBusyOutPort()
            dbgTracer.log("no enter & noeixtToHeaderNotify -> replace busy with 1")
            modified |= _replaceOutPortWith1(busyO, worklist)
    
            #if len(n.fromReenter) == 1:
            #   # there is only 1 place for reenter the reenter en port on loop is useless
            #   reG: LoopChanelGroup = n.fromReenter[0]
            for reG in n.fromReenter:
                reG.connectedLoopsAndBlocks.remove((n, LOOP_CHANEL_GROUP_ROLE.REENTER))
                if not reG.connectedLoopsAndBlocks:
                    reG.destroy()
    
                srcDst, _ = n._findLoopChannelIn_bbNumberToPorts(reG)
                n._bbNumberToPorts.pop(srcDst)

            #reGControlR = reG.getChannelUsedAsControl().associatedRead
            #modified |= _replaceOutPortWith(outPort, reGControlR.getValidNB(), worklist)
            #n._removeOutput(outPort.out_i)
            n.fromReenter.clear()
            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, worklist)
            assert not n._bbNumberToPorts, (n, n._bbNumberToPorts)
            n.markAsRemoved()
            modified = True
            dbgTracer.log("remove because it has just 1 reenter")

        elif not n.fromEnter and len(n.fromReenter) == 1 and (not n.fromExitToHeaderNotify or
                                                              n._isEnteredOnExit):
            dbgTracer.log("try to remove control because always running")
            # the loop control is useless because this loop is always running and is constantly re-executing itself
            # and there is no arbitration of inputs nor blocking until current body finishes
            builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
    
            reenterG: LoopChanelGroup = n.fromReenter[0]
            srcDst, _ = n._findLoopChannelIn_bbNumberToPorts(reenterG)
            reenterControl: HlsNetNodeReadAnyChannel = reenterG.getChannelUsedAsControl().associatedRead
            #_replaceOutPortWith(fromStatusOut, reenterControl.getValidNB(), worklist)
            if not reenterControl._isBlocking:
                reenterControl._isBlocking = True
            reenterG.connectedLoopsAndBlocks.remove((n, LOOP_CHANEL_GROUP_ROLE.REENTER))
            if not reenterG.connectedLoopsAndBlocks:
                reenterG.destroy()
    
            if n.fromExitToHeaderNotify:
                dbgTracer.log("rm because no exitToHeaderNotify")
                # unregister loop from channel
                assert len(n.fromExitToHeaderNotify) == 1, n
                exitG: LoopChanelGroup = n.fromExitToHeaderNotify[0]
                exitG.connectedLoopsAndBlocks.remove((n, LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER))
                # avoid wait on reenter when exit
                exitW: HlsNetNodeWriteBackedge = exitG.getChannelUsedAsControl()
                # promote to a regular channel with an init
                exitW.allocationType = CHANNEL_ALLOCATION_TYPE.BUFFER 
                exitR: HlsNetNodeReadBackedge = exitW.associatedRead
                assert not exitR.channelInitValues, ("EXIT_NOTIFY_TO_HEADER should never have init value", exitW, exitR.channelInitValues)
                assert HdlType_isVoid(exitW._portDataOut._dtype), exitW
                exitR.channelInitValues = (tuple(),) # add one token to start the loop 
                assert not exitR._isBlocking, exitR
                exitR._isBlocking = True
    
                reenterControl.addControlSerialSkipWhen(builder.buildNot(exitR.getValidNB()))
    
                # disconnect loop status port for exit input
                srcDst, exitInOnStatus = n._findLoopChannelIn_bbNumberToPorts(exitG)
                exitInOnStatus.disconnectFromHlsOut(exitR.getValidNB())
    
                if not exitG.connectedLoopsAndBlocks:
                    exitG.destroy()
    
                for exitToSucG in n.fromExitToSuccessor:
                    exitToSucG: LoopChanelGroup
                    exitToSucG.connectedLoopsAndBlocks.remove((n, LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR))
                    if not exitToSucG.connectedLoopsAndBlocks:
                        exitToSucG.destroy()
    
            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, worklist)
            n.markAsRemoved()
            modified = True
    
        elif not n.fromEnter and len(n.fromReenter) == 1 and len(n.fromExitToHeaderNotify) == 1 and n._isEnteredOnExit:
            # has 2 real channels which can execute lopp 1 reenter, 1 enter from exit
            # 2 execute channels are beneficial to realize without the loop as the flags for enable from reenter/enter predecessors
            # are just 1 flag and its negation
            raise NotImplementedError(n)

    return modified
