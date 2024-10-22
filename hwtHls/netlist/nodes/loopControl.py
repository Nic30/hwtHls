from itertools import chain
from typing import List, Generator, Tuple, Dict, Optional

from hwt.hdl.types.defs import BIT
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.hdlTypeVoid import HVoidData, HVoidOrdering
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitSync import IO_COMB_REALIZATION
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import \
    LoopChanelGroup, LOOP_CHANEL_GROUP_ROLE, HlsNetNodeReadOrWriteToAnyChannel
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HlsNetNodeOrderable
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.portsUtils import HlsNetNodeOut_connectHlsIn_crossingHierarchy
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class HlsNetNodeLoopStatus(HlsNetNodeOrderable):
    """
    This status node holds the state of execution of all loops for some loop header block.
    It locks enter ports while the loop body is running to assert that loop exits before it takes new data.

    Not all hardware loops necessary need this:
    * Top loops with a single predecessor may have this predecessor liveIn variables values inlined to an initialization
      of backedges of this loop if all values coming from this predecessor are constant.
      (This removes enter to loop which is important for next items in this list.)
    * Loops with no enter and exit do not need this as they are always running.
    * Loops with no enter and no live variables on reenter edges do not need this
     as there are no inter iteration dependencies.

    :attention: Loop ports may be shared between loops. E.g. one exit may be also enter to other loop and also exit from parent loop.
    :attention: Loop ports may hold data if some data channel is reused as a control.
    :attention: For correct functionality the loop body must be separated from rest of the circuit.
        This is required because various blocking operations which are not inside of the loop must be separated.
    :attention: There should be ordering connected from last IO in the loop to achieve better results in
        :meth:`~.HlsNetNodeLoopStatus.scheduleAlapCompaction` because without it this does not have any outputs
        and will stay at the end of current cycle which is sub-optimal if the whole loop shifts in time.
    :attention: The status register (busy) is 0 in the first clock and becomes 1 after first clock when loop is executed.
        The busy port value controls only if data is accepted from loop predecessors or reenters.
    :note: This node does not contain any multiplexers or explicit synchronization it is just a state-full control logic
        which provides "enable signals".
    :note: Enable output flags are telling which patch to loop was enabled.
        Busy select between enter/reenter and the input group from fromEnter/fromReenter
        is arbitrated. At most a single flags is 1 at the time.

    :note: For nested loops the parent loop is always guaranteed to be busy if child is.

    :ivar fromEnter: for each direct predecessor which is not in cycle body a tuple input for control and variable values.
        Signalizes that the loop has data to be executed.
    :ivar fromReenter: For each direct predecessor which is a part of a cycle body a tuple control input and associated variables.
        Note that the channels are usually connected to out of pipeline interface because the HlsNetlistCtx does not support cycles.
    :ivar fromExitToHeaderNotify: Group which lead from exit point to a place where this loop status is and it notifies
        the status about the exit from the loop so loop can be reentered again.
        It is always IMMEDIATE channel and it always sets the next state of loop busy register to 0.
        (busy is 0 during first clock of fist iteration) 
    :ivar fromExitToSuccessor: Groups which lead from exit point to section behind the loop to enable it.
    :ivar _isEnteredOnExit: flag, If True it means that the loop is automatically entered if not busy.
        (Every exit causes busy=0 for first iteration.)
    """

    def __init__(self, netlist:"HlsNetlistCtx", name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        # :note: other outputs are added for each predecessor for the block where loop is
        #    ports are used to separate loop body from circuit outside of loop
        self._addOutput(HVoidOrdering, "orderingOut")
        self._addOutput(BIT, f"busy")

        self.debugUseNamedSignalsForControl = False
        # a dictionary port node -> RtlSignal
        self._rtlPortGroupSigs: Dict[LoopChanelGroup, RtlSignal] = {}
        self._rtlAllocated = False

        self.fromEnter: List[LoopChanelGroup] = []
        self.fromReenter: List[LoopChanelGroup] = []
        self.fromExitToHeaderNotify: List[LoopChanelGroup] = []

        self.fromExitToSuccessor: List[LoopChanelGroup] = []

        self._bbNumberToPorts: Dict[tuple(int, int), Tuple[LoopChanelGroup, Optional[HlsNetNodeIn]]] = {}
        self._isEnteredOnExit: bool = False

    @override
    def clone(self, memo:dict) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNodeOrderable.clone(self, memo)
        if isNew:
            y.fromEnter = [c.clone(memo)[0] for c in self.fromEnter]
            y.fromReenter = [c.clone(memo)[0] for c in self.fromReenter]
            y.fromExitToHeaderNotify = [c.clone(memo)[0] for c in self.fromExitToHeaderNotify]
            y.fromExitToSuccessor = [c.clone(memo)[0] for c in self.fromExitToSuccessor]
            y._bbNumberToPorts = {k: (memo[id(lcg)], None if i is None else y._inputs[i.in_i])
                                  for k, (lcg, i) in self._bbNumberToPorts.items()}
        return y, isNew

    @override
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        nonOrderingInputs = set(v[1] for v in self._bbNumberToPorts.values())
        for i in self._inputs:
            if i not in nonOrderingInputs:
                yield i

    def iterConnectedInputChannelGroups(self) -> Generator[LoopChanelGroup, None, None]:
        return chain(self.fromEnter, self.fromReenter, self.fromExitToHeaderNotify)

    def iterChannelIoOutsideOfLoop(self):
        for g in self.fromEnter:
            yield from g.members

        for g in self.fromExitToSuccessor:
            for w in g.members:
                yield w.associatedRead

    def iterChannelIoInsideOfLoop(self):
        for g in self.fromEnter:
            for w in g.members:
                yield w.associatedRead

        for g in chain(self.fromReenter, self.fromExitToHeaderNotify):
            for w in g.members:
                yield w
                yield w.associatedRead

        for g in self.fromExitToSuccessor:
            for w in g.members:
                yield w

    def _findLoopChannelIn_bbNumberToPorts(self, lcg: LoopChanelGroup):
        for srcDst, (portChannelGroup, outPort) in self._bbNumberToPorts.items():
            srcDst: Tuple[int, int]
            outPort: HlsNetNodeOut
            if portChannelGroup is lcg:
                return (srcDst, outPort)

        raise KeyError(lcg)

    def getBusyOutPort(self) -> HlsNetNodeOut:
        return self._outputs[1]

    @override
    def getOrderingOutPort(self) -> HlsNetNodeOut:
        return self._outputs[0]

    @override
    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def _connectVoidDataConst(self, w: HlsNetNodeWrite):
        v = self.getHlsNetlistBuilder().buildConst(HVoidData.from_py(None))
        v.connectHlsIn(w._portSrc)

    def addEnterPort(self, srcBlockNumber: int, dstBlockNumber: int, lcg:LoopChanelGroup)\
            ->Tuple[HlsNetNodeRead, HlsNetNodeOut]:
        """
        Register connection of control and data from some block which causes the loop to to execute.

        :note: When transaction on this IO is accepted the loop sync token is changed to busy state if not overridden by exit.
        :note: Loop can be executed directly after reset. This implies that the enter ports are optional. However enter or
            exit port must be present, otherwise this loop status node is not required at all because
        """
        lcg.associateWithLoop(self, LOOP_CHANEL_GROUP_ROLE.ENTER)
        name = f"enterFrom_bb{srcBlockNumber:}"
        # fromStatusOut = self._addOutput(BIT, name)
        w = lcg.getChannelUsedAsControl()
        r: HlsNetNodeReadBackedge = w.associatedRead
        busy = self.getBusyOutPort()
        busy_n = self.getHlsNetlistBuilder().buildNot(busy)
        LoopChanelGroup.appendToListOfPriorityEncodedReads(self.fromEnter, busy_n, busy, lcg, name)

        assert isinstance(r, HlsNetNodeRead), r
        # # assert not r._isBlocking, r
        # b: HlsNetlistBuilder = self.getHlsNetlistBuilder()
        # if self.fromEnter:
        #    lastEnter: HlsNetNodeRead = self.fromEnter[0].getChannelUsedAsControl().associatedRead
        #    lastEnter.setNonBlocking()
        #    lastEc = lastEnter.dependsOn[lastEnter.extraCond.in_i]
        #    enOut = b.buildAnd(lastEc, b.buildNot(lastEnter.getValidNB()))
        # else:
        #    enOut = b.buildNot(self.getBusyOutPort())
        HlsNetNodeOut_connectHlsIn_crossingHierarchy(w.getOrderingOutPort(), self._addInput("orderingIn"), "ordering")
        #self.fromEnter.append(lcg)
        self._bbNumberToPorts[(srcBlockNumber, dstBlockNumber)] = (lcg, None)

        # enOut = b.buildAnd(enOut, r.getValidNB(), name=f"enterFrom_bb{srcBlockNumber:}")
        # return r, enOut

    def addReenterPort(self, srcBlockNumber: int, dstBlockNumber: int, lcg: LoopChanelGroup)\
            ->Tuple[HlsNetNodeRead, HlsNetNodeOut]:
        """
        Register connection of control and data from some block where control flow gets back block where the cycle starts.

        :note: When transaction on this IO is accepted the loop sync token is reused
        """
        lcg.associateWithLoop(self, LOOP_CHANEL_GROUP_ROLE.REENTER)
        name = f"reenterFrom_bb{srcBlockNumber}"
        # fromStatusOut = self._addOutput(BIT, name)
        r: HlsNetNodeReadBackedge = lcg.getChannelUsedAsControl().associatedRead
        assert isinstance(r, HlsNetNodeReadBackedge), r
        busy = self.getBusyOutPort()
        busy_n = self.getHlsNetlistBuilder().buildNot(busy)
        LoopChanelGroup.appendToListOfPriorityEncodedReads(self.fromReenter, busy, busy_n, lcg, name)
        # if self.fromReenter:
        #    lastReenter: HlsNetNodeRead = self.fromReenter[0].getChannelUsedAsControl().associatedRead
        #    b: HlsNetlistBuilder = self.getHlsNetlistBuilder()
        #    lastEC = lastReenter.dependsOn[lastReenter.extraCond.in_i]
        #    enOut = b.buildAnd(lastEC, b.buildNot(lastReenter.getValidNB()), name)
        # else:
        #    enOut = self.getBusyOutPort()
        #
        # assert not r._isBlocking, r
        #self.fromReenter.append(lcg)
        self._bbNumberToPorts[(srcBlockNumber, dstBlockNumber)] = (lcg, None)

        # return r, enOut

    def addExitToHeaderNotifyPort(self, srcBlockNumber: int, dstBlockNumber: int, lcg: LoopChanelGroup)\
            ->HlsNetNodeWrite:
        """
        Register connection of control which causes to break current execution of the loop.
        :note: This channel group leads from exit to a header block. The exit channel from
        from the loop which transfers data outside of the loop is handled on different place.
        (when translating from MIR)

        :note: When transaction on this IO is accepted the loop sync token returned to ready state.
        :note: the loop may not end this implies that this may not be used at all.
        """
        lcg.associateWithLoop(self, LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER)
        w: HlsNetNodeWriteBackedge = lcg.getChannelUsedAsControl()
        assert w.allocationType == CHANNEL_ALLOCATION_TYPE.IMMEDIATE, (
            "Must be IMMEDIATE because this information modifies busy flag immediately",
            w, w.allocationType)
        assert isinstance(w, HlsNetNodeWriteBackedge), w
        r = w.associatedRead
        assert not r._isBlocking, ("Must be non-blocking because busy flag must be reset without blocking to prevent deadlock", r)
        exitIn = self._addInput(f"exit_from_bb{srcBlockNumber:d}_to_bb{dstBlockNumber:d}", True)
        r.getValidNB().connectHlsIn(exitIn)

        self.fromExitToHeaderNotify.append(lcg)
        self._bbNumberToPorts[(srcBlockNumber, dstBlockNumber)] = (lcg, exitIn)
        return w

    def addExitToSuccessorPort(self, lcg: LoopChanelGroup):
        """
        Register connection which is executing code behind the loop.
        """
        lcg.associateWithLoop(self, LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR)
        w: HlsNetNodeWriteBackedge = lcg.getChannelUsedAsControl()
        assert isinstance(w, (HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge)), w
        self.fromExitToSuccessor.append(lcg)
        return w

    def _getAckOfStageWhereNodeIs(self,
                                  n: HlsNetNodeReadOrWriteToAnyChannel) -> Optional[RtlSignal]:
        elm = n.parent
        t = n.scheduledOut[0] if n.scheduledOut else n.scheduledIn[0]
        con: ConnectionsOfStage = elm.connections.getForTime(t)

        selfParent = self.parent
        selfT = n.scheduledOut[0] if n.scheduledOut else n.scheduledIn[0]
        selfCon: ConnectionsOfStage = selfParent.connections.getForTime(selfT)
        if con is selfCon:
            return BIT.from_py(1)

        return con.getRtlStageAckSignal()

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        """
        This node should be lowered before RTL allocation to simplify search for combinational loops etc.
        :see: :class:`HlsAndRtlNetlistPassHlsNetNodeLoopStatus`
        """
        raise AssertionError("This node is not meant for RTL allocation and it should have been lowered before", self)

    @override
    def debugIterShadowConnectionDst(self) -> Generator[Tuple[HlsNetNode, bool], None, None]:
        for g in chain(self.fromEnter, self.fromReenter, self.fromExitToHeaderNotify):
            for w in g.members:
                yield w.associatedRead, False

    def __repr__(self):
        return (f"<{self.__class__.__name__:s}{' ' if self.name else ''}{self.name}"
                f" {self._id:d}{' isEnteredOnExit' if self._isEnteredOnExit else ''}>")

