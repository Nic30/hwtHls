from typing import Sequence, Optional, Set, List, Union, Dict, Tuple

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.types.defs import BIT
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.transformation.hlsAndRtlNetlistPass import HlsAndRtlNetlistPass
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUnscheduledControlLogic
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.loopChannelGroup import LoopChanelGroup, \
    HlsNetNodeReadOrWriteToAnyChannel
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import link_hls_nodes, \
    unlink_hls_nodes, HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.scheduler.clk_math import beginOfClk, endOfClk, \
    indexOfClkPeriod
from hwtHls.netlist.transformation.simplifyExpr.loops import _replaceOutPortWith


class HlsAndRtlNetlistPassDisolveHlsNetNodeLoopStatus(HlsAndRtlNetlistPass):

    @classmethod
    def _lowerHlsNetNodeLoopStatus(cls, builder: HlsNetlistBuilder, parent: ArchElement, loopStatus: HlsNetNodeLoopStatus):
        if loopStatus.scheduledZero is None:
            raise NotImplementedError()

        name = loopStatus.name
        if not name:
            name = f"loop{loopStatus._id:d}"

        netlist = loopStatus.netlist
        clkPeriod = netlist.normalizedClkPeriod
        scheduledZero = loopStatus.scheduledZero
        clkIndex = indexOfClkPeriod(scheduledZero, clkPeriod)
        syncNode = (parent, clkIndex)
        isAlwaysBusy = loopStatus._isEnteredOnExit and not loopStatus.fromEnter
        if isAlwaysBusy:
            # raise AssertionError("This node should be optimized out if state of the loop can't change", loopStatus)
            c1 = HlsNetNodeConst(netlist, BIT.from_py(1))
            c1._setScheduleZeroTimeSingleClock(scheduledZero)
            parent._addNodeIntoScheduled(clkIndex, c1)
            statusBusyRegValOut = None  # c1._outputs[0]
            _replaceOutPortWith(loopStatus.getBusyOutPort(), c1, [])

        else:
            # prepare backedge to store busyReg
            statusBusyName = f"{name:s}_busyReg" if loopStatus.fromEnter else f"{name:s}_busy"
            statusBusyRegR = HlsNetNodeReadBackedge(netlist, BIT, name=statusBusyName + "_dst")
            # busy if is executed at 0 time
            channelInitValues = ((0 if loopStatus.fromEnter else 1),)
            statusBusyRegW = HlsNetNodeWriteBackedge(netlist, name=statusBusyName + "_src", channelInitValues=channelInitValues)
            for c, time in [(statusBusyRegR, beginOfClk(loopStatus.scheduledZero, clkPeriod)),
                      (statusBusyRegW, endOfClk(loopStatus.scheduledZero, clkPeriod))]:
                c: HlsNetNodeReadOrWriteToAnyChannel
                c._rtlUseReady = c._rtlUseValid = False
                c.resolveRealization()
                c._setScheduleZeroTimeSingleClock(time)
                parent._addNodeIntoScheduled(clkIndex, c)

            statusBusyRegValIn = statusBusyRegW._inputs[0]
            statusBusyRegValOut = statusBusyRegR._portDataOut
            statusBusyRegW.associateRead(statusBusyRegR)
            link_hls_nodes(statusBusyRegR.getOrderingOutPort(), statusBusyRegW._addInput("orderingIn", addDefaultScheduling=True))
            _replaceOutPortWith(loopStatus.getBusyOutPort(), statusBusyRegValOut, [])

        groupToEdgeAndPort: Dict[LoopChanelGroup, Tuple[Tuple[int, int], Union[HlsNetNodeOut, HlsNetNodeIn]]] = {
            lcg: (edge, port) for edge, (lcg, port) in loopStatus._bbNumberToPorts.items()}

        # has the priority and does not require sync token (because it already owns it)
        assert loopStatus.fromReenter, (loopStatus, "Must have some reenters otherwise this is not the loop")

        builder.operatorCache.clear()

        newExit = NOT_SPECIFIED
        if loopStatus.fromExitToHeaderNotify:
            # returns the control token
            _newExit = []
            for channelGroup in loopStatus.fromExitToHeaderNotify:
                channelGroup: LoopChanelGroup
                edge, port = groupToEdgeAndPort[channelGroup]
                # port of loopStatus should be connected to a validNB of exit channel read
                d = loopStatus.dependsOn[port.in_i]
                unlink_hls_nodes(d, port)  # unlink from loopStatus because we will remove it later
                _newExit.append(d)

            newExit = builder.buildOrVariadic(_newExit, f"{name:s}_newExit")

        newEnter = NOT_SPECIFIED
        if loopStatus.fromEnter:
            # takes the control token
            en = builder.buildNot(statusBusyRegValOut)  # :note: the statusBusyReg is 0 in the first clock of the loop execution
            _newEnter = []
            for channelGroup in loopStatus.fromEnter:
                channelGroup: LoopChanelGroup
                channelRead = channelGroup.getChannelUsedAsControl().associatedRead
                _newEnter.append(channelRead.getValidNB())

            newEnter = builder.buildAnd(en, builder.buildOrVariadic(_newEnter, f"{name:s}_newEnter"))  # en & Or(*_newEnter)

        # new exe or reenter should be executed only if stage with this node has ack
        # exit should be executed only if stage with exit write has ack
        if isAlwaysBusy:
            # raise AssertionError("This node should be optimized out if state of the loop can't change", loopStatus)
            assert statusBusyRegValOut is None

        elif not loopStatus.fromEnter and not loopStatus.fromExitToHeaderNotify:
            # this is infinite loop without predecessor, it will run infinitely but in just one instance
            # raise AssertionError("This node should be optimized out if state of the loop can't change", loopStatus)
            assert newEnter is NOT_SPECIFIED, (newEnter, loopStatus)
            assert newExit is NOT_SPECIFIED, (newExit, loopStatus)
            c1 = builder.buildConstBit(1)
            c1._setScheduleZeroTimeSingleClock(beginOfClk(scheduledZero, clkPeriod))
            parent._addNodeIntoScheduled(clkIndex, c1)
            link_hls_nodes(c1, statusBusyRegValIn)

        elif loopStatus.fromEnter and not loopStatus.fromExitToHeaderNotify:
            # this is an infinite loop which has a predecessor, once started it will be closed for new starts
            # :attention: we pick the data from any time because this is kind of back edge
            assert newEnter, (newEnter, loopStatus)
            assert newExit is NOT_SPECIFIED, (newExit, loopStatus)
            # if newEnter:
            #     statusBusyReg = 1
            busyNext = builder.buildOr(statusBusyRegValOut, newEnter)
            scheduleUnscheduledControlLogic(syncNode, busyNext)
            link_hls_nodes(busyNext, statusBusyRegValIn, checkCycleFree=False)

        elif loopStatus.fromEnter and loopStatus.fromExitToHeaderNotify:
            # loop with a predecessor and successor
            assert newEnter is not NOT_SPECIFIED, (newEnter, loopStatus)
            assert newExit is not NOT_SPECIFIED, (newExit, loopStatus)
            becomesBusy = builder.buildAnd(newEnter, builder.buildNot(newExit))  # newEnter & ~newExit
            becomesFree = builder.buildAnd(builder.buildNot(newEnter), newExit)  # ~newEnter & newExit
            # if becomesBusy:
            #    statusBusyReg = 1
            # elif becomesFree:
            #    statusBusyReg = 0
            busyNext = builder.buildAnd(
                builder.buildOr(becomesBusy, statusBusyRegValOut),
                builder.buildNot(becomesFree))
            scheduleUnscheduledControlLogic(syncNode, busyNext)
            link_hls_nodes(busyNext,
                statusBusyRegValIn, checkCycleFree=False)
            # allow for update of busy on exit if this node does not have ack at the moment
            link_hls_nodes(becomesFree, statusBusyRegW.getForceWritePort(), checkCycleFree=False)

        elif not loopStatus.fromEnter and loopStatus.fromExitToHeaderNotify:
            # loop with no predecessor and successor
            assert newEnter is NOT_SPECIFIED, (newEnter, loopStatus)
            assert newExit is not NOT_SPECIFIED, (newExit, loopStatus)
            c0 = builder.buildConstBit(0)
            c0.obj.resolveRealization()
            c0.obj._setScheduleZeroTimeSingleClock(beginOfClk(scheduledZero, clkPeriod))
            parent._addNodeIntoScheduled(clkIndex, c0.obj)
            link_hls_nodes(c0, statusBusyRegValIn)
            # if newExit:
            #    statusBusyReg = 0
            link_hls_nodes(newExit, statusBusyRegW.getForceWritePort(), checkCycleFree=False)

        else:
            raise AssertionError("All cases should already be covered in this if", loopStatus)

    @classmethod
    def _lowerHlsNetNodeLoopStatusInNodes(cls,
                                          rootBuilder: HlsNetlistBuilder,
                                          builder: HlsNetlistBuilder,
                                          parent: Optional[HlsNetNodeAggregate],
                                          nodes: Sequence[HlsNetNode],
                                          removed: Set[HlsNetNodeLoopStatus]):
        for n in nodes:
            if isinstance(n, HlsNetNodeAggregate):
                _removed = set()
                cls._lowerHlsNetNodeLoopStatusInNodes(rootBuilder, rootBuilder.scoped(n), n, n._subNodes, _removed)
                if _removed:
                    n.filterNodesUsingSet(_removed)

            elif isinstance(n, HlsNetNodeLoopStatus):
                cls._lowerHlsNetNodeLoopStatus(builder, parent, n)
                removed.add(n)

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        rootBuilder: HlsNetlistBuilder = netlist.builder
        removed = set()
        self._lowerHlsNetNodeLoopStatusInNodes(rootBuilder, rootBuilder, None, netlist.nodes, removed)
        if removed:
            netlist.filterNodesUsingSet(removed)

