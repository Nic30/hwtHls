from itertools import chain
from typing import List, Generator, Tuple, Dict, Optional

from hwt.code import If, Or
from hwt.code_utils import rename_signal
from hwt.hdl.types.defs import BIT
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.analysis.nodeParentAggregate import HlsNetlistAnalysisPassNodeParentAggregate
from hwtHls.netlist.hdlTypeVoid import HVoidData, HVoidOrdering
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge, BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitSync import IO_COMB_REALIZATION
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import \
    LoopChanelGroup, LOOP_CHANEL_GROUP_ROLE, HlsNetNodeReadOrWriteToAnyChannel, \
    HlsNetNodeReadAnyChannel
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HlsNetNodeOrderable
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes, \
    HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.typingFuture import override
from hwtLib.logic.rtlSignalBuilder import RtlSignalBuilder


class HlsNetNodeLoopStatus(HlsNetNodeOrderable):
    """
    This status node holds the state of execution of all loops for some loop header block.
    It locks enter ports while the loop body is running to assert that loop exits before it takes new data.

    Not all hardware loops necessary need this:
    * Top loops with a single predecessor may have this predecessor liveIn variables values inlined to an initialization
      of backedges of this loop if all values coming from this predecessor are constant.
      (This removes enter to loop which is important for next items in this list.)
    * Loops with no enter and exit do not need this as they are always running.
    * Loops with no enter and no live variables on reenter edges do not need this as there are no inter iteration dependencies.

    :attention: Loop ports may be shared between loops. E.g. one exit may be also enter to other loop and also exit from parent loop.
    :attention: Loop ports may hold data if some data channel is reused as a control.
    :attention: For correct functionality the loop body must be separated from rest of the circuit.
        This is required because various blocking operations which are not inside of the loop must be separated.
    :attention: There should be ordering connected from last IO in the loop to achieve better results in
        :meth:`~.HlsNetNodeLoopStatus.scheduleAlapCompaction` because without it this does not have any outputs
        and will stay at the end of current cycle which is sub-optimal if the whole loop shifts in time.
    :attention: The status register is not 1 in the first clock and becomes 1 after first clock when loop is executed.
        The busy port value is should control only if data is accepted from loop predecessors or reenter.
    :note: This node does not contain any multiplexers or explicit synchronization it is just a state-full control logic
        which provides "enable signals".

    :note: For nested loops the top loop is always guaranteed to be busy if child is.
        If the child has same header block as parent, the children status is most important. Because we need to
        continue executing the lowest loop.

    :ivar fromEnter: for each direct predecessor which is not in cycle body a tuple input for control and variable values.
        Signalizes that the loop has data to be executed.
    :ivar fromReenter: For each direct predecessor which is a part of a cycle body a tuple control input and associated variables.
        Note that the channels are usually connected to out of pipeline interface because the HlsNetlistCtx does not support cycles.
    :ivar fromExitToHeaderNotify: Group which lead from exit point to a place where this loop status is and it notifies
        the status about the exit from the loop so loop can be reentered again.
    :ivar fromExitToSuccessor: Groups which lead from exit point to section behind the loop to enable it.
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
        self.channelExtraEnCondtions: Dict[LoopChanelGroup, List[HlsNetNodeIn]] = {}

        self._bbNumberToPorts: Dict[tuple(int, int), Tuple[LoopChanelGroup, HlsNetNodeOut]] = {}
        self._isEnteredOnExit: bool = False

    def addChannelExtraEnCondtion(self, lcg: LoopChanelGroup, en: HlsNetNodeOut, name:str,
                                  addDefaultScheduling=False, inputWireDelay:int=0):
        """
        Add an extra enable condition for channel group which will be anded with enable from channel to control this
        loop status.
        """
        # if role == LOOP_CHANEL_GROUP_ROLE.ENTER:
        #    inList = self.fromEnter
        # elif role == LOOP_CHANEL_GROUP_ROLE.REENTER:
        #    inList = self.fromReenter
        # elif role == LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER:
        #    inList = self.fromExitToHeaderNotify
        # elif role == LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR:
        #    inList = self.fromExitToSuccessor
        # else:
        #    raise ValueError(role)

        i = self._addInput(name, addDefaultScheduling=addDefaultScheduling,
                           inputClkTickOffset=0, # must be 0 because it must be in same clk
                           inputWireDelay=inputWireDelay)
        link_hls_nodes(en, i)
        ens = self.channelExtraEnCondtions.get(lcg)
        if ens is None:
            ens = []
            self.channelExtraEnCondtions[lcg] = ens
        ens.append(i)

    @override
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        nonOrderingInputs = set(v[1] for v in self._bbNumberToPorts.values())
        for i in self._inputs:
            if i not in nonOrderingInputs:
                yield i

    def _findLoopChannelIn_bbNumberToPorts(self, lcg: LoopChanelGroup):
        for srcDst, (portChannelGroup, outPort) in self._bbNumberToPorts.items():
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
        v = self.netlist.builder.buildConst(HVoidData.from_py(None))
        link_hls_nodes(v, w._inputs[0])

    def addEnterPort(self, srcBlockNumber: int, dstBlockNumber: int, lcg:LoopChanelGroup)\
            ->Tuple[HlsNetNodeRead, HlsNetNodeOut]:
        """
        Register connection of control and data from some block which causes the loop to to execute.

        :note: When transaction on this IO is accepted the loop sync token is changed to busy state if not overriden by exit.
        :note: Loop can be executed directly after reset. This implies that the enter ports are optional. However enter or
            exit port must be present, otherwise this loop status node is not required at all because
        """
        lcg.associateWithLoop(self, LOOP_CHANEL_GROUP_ROLE.ENTER)
        name = f"enterFrom_bb{srcBlockNumber:}"
        fromStatusOut = self._addOutput(BIT, name)
        w = lcg.getChannelWhichIsUsedToImplementControl()
        r: HlsNetNodeReadBackedge = w.associatedRead
        assert isinstance(r, HlsNetNodeRead), r
        # assert not r._isBlocking, r

        link_hls_nodes(w.getOrderingOutPort(), self._addInput("orderingIn"))
        self.fromEnter.append(lcg)
        self._bbNumberToPorts[(srcBlockNumber, dstBlockNumber)] = (lcg, fromStatusOut)
        return r, fromStatusOut

    def addReenterPort(self, srcBlockNumber: int, dstBlockNumber: int, lcg: LoopChanelGroup)\
            ->Tuple[HlsNetNodeRead, HlsNetNodeOut]:
        """
        Register connection of control and data from some block where control flow gets back block where the cycle starts.

        :note: When transaction on this IO is accepted the loop sync token is reused
        """
        lcg.associateWithLoop(self, LOOP_CHANEL_GROUP_ROLE.REENTER)
        name = f"reenterFrom_bb{srcBlockNumber}"
        fromStatusOut = self._addOutput(BIT, name)
        r: HlsNetNodeReadBackedge = lcg.getChannelWhichIsUsedToImplementControl().associatedRead
        assert isinstance(r, HlsNetNodeReadBackedge), r
        # assert not r._isBlocking, r
        self.fromReenter.append(lcg)
        self._bbNumberToPorts[(srcBlockNumber, dstBlockNumber)] = (lcg, fromStatusOut)
        return r, fromStatusOut

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
        w: HlsNetNodeWriteBackedge = lcg.getChannelWhichIsUsedToImplementControl()
        assert w.allocationType == BACKEDGE_ALLOCATION_TYPE.IMMEDIATE, (
            "Must be IMMEDIATE because this information modifies busy flag immediately",
            w, w.allocationType)
        assert isinstance(w, HlsNetNodeWriteBackedge), w
        r = w.associatedRead
        assert not r._isBlocking, ("Must be non-blocking because busy flag must be reset without blocking to prevent deadlock", r)
        exitIn = self._addInput(f"exit_from_bb{srcBlockNumber:d}_to_bb{dstBlockNumber:d}", True)
        link_hls_nodes(r.getValidNB(), exitIn)

        self.fromExitToHeaderNotify.append(lcg)
        self._bbNumberToPorts[(srcBlockNumber, dstBlockNumber)] = (lcg, exitIn)
        return w

    def addExitToSuccessorPort(self, lcg: LoopChanelGroup):
        """
        Register connection which is executing code behind the loop.
        """
        lcg.associateWithLoop(self, LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR)
        w: HlsNetNodeWriteBackedge = lcg.getChannelWhichIsUsedToImplementControl()
        assert isinstance(w, (HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge)), w
        self.fromExitToSuccessor.append(lcg)
        return w

    @staticmethod
    def _resolveBackedgeDataRtlValidSig(portNode: HlsNetNodeReadBackedge):
        portNode._allocateRtlIo()
        allocationType = portNode.associatedWrite.allocationType
        if allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER:
            return portNode.src.vld  # & portNode.src.rd
        elif allocationType == BACKEDGE_ALLOCATION_TYPE.REG:
            return portNode.src.vld
        else:
            raise NotImplementedError(portNode, allocationType)

    def allocateRtlInstance(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        """
        :note: drive of this register is generated from :class:`~.HlsNetNodeLoop`
        """
        try:
            return allocator.netNodeToRtl[self]
        except KeyError:
            pass

        name = self.name
        if name:
            name = f"{allocator.namePrefix}{name}"
        else:
            name = f"{allocator.namePrefix}loop{self._id:d}"

        isAlwaysBusy = self._isEnteredOnExit and not self.fromEnter
        if isAlwaysBusy:
            statusBusyReg = BIT.from_py(1)
        else:
            statusBusyReg = allocator._reg(
                f"{name:s}_busy",
                def_val=0 if self.fromEnter else 1)  # busy if is executed at 0 time
        bbNumberToPortsSorted = sorted(self._bbNumberToPorts.items(), key=lambda x: x[0])
        portGroupSigs = self._rtlPortGroupSigs
        for _, (channelGroup, portOut) in bbNumberToPortsSorted:
            s = allocator._sig(f"{name:s}_{channelGroup.name:s}" if portOut is None else f"{name:s}_{portOut.name:s}")
            portGroupSigs[channelGroup] = s

        useNamedSignals = self.debugUseNamedSignalsForControl
        parentU = self.netlist.parentUnit

        # has the priority and does not require sync token (because it already owns it)
        assert self.fromReenter, (self, "Must have some reenters otherwise this is not the loop")
        for channelGroup in self.fromReenter:
            s = portGroupSigs[channelGroup]
            s(self._resolveBackedgeDataRtlValidSig(channelGroup.getChannelWhichIsUsedToImplementControl().associatedRead))

        newExit = NOT_SPECIFIED
        if self.fromExitToHeaderNotify:
            # returns the control token
            fromExit = []
            for channelGroup in self.fromExitToHeaderNotify:
                portNode = channelGroup.getChannelWhichIsUsedToImplementControl()
                assert isinstance(portNode, HlsNetNodeWriteBackedge), (portNode, self)
                # e.allocateRtlInstance(allocator)
                s = portGroupSigs[channelGroup]
                fromExit.append(s)
                portNodeR = portNode.associatedRead
                allocator.instantiateHlsNetNodeOutInTime(portNodeR._validNB, self.scheduledZero)
                # portNode.associatedRead._allocateRtlIo()
                s(portNodeR.src.vld)

            newExit = Or(*fromExit)
            if useNamedSignals:
                newExit = rename_signal(parentU, newExit, f"{name:s}_newExit")

        newExe = NOT_SPECIFIED
        if self.fromEnter:
            fromEnter = []
            # takes the control token
            for channelGroup in self.fromEnter:
                portNode = channelGroup.getChannelWhichIsUsedToImplementControl().associatedRead
                portNode._allocateRtlIo()
                _s = portGroupSigs[channelGroup]
                s = portNode.src.vld
                if newExit is not NOT_SPECIFIED:
                    en = ~statusBusyReg | newExit
                else:
                    en = ~statusBusyReg
                _s(s & en)
                # e.src.rd(~statusBusyReg)
                fromEnter.append(s)

            newExe = Or(*fromEnter)
            if useNamedSignals:
                newExe = rename_signal(parentU, newExe, f"{name:s}_newExe")
            # statusBusy = statusBusyReg | newExe

        if isAlwaysBusy:
            assert isinstance(statusBusyReg, HValue), self
            pass

        elif not self.fromEnter and not self.fromExitToHeaderNotify:
            # this is infinite loop without predecessor, it will run infinitely but in just one instance
            assert newExe is NOT_SPECIFIED, (newExe, self)
            assert newExit is NOT_SPECIFIED, (newExit, self)
            statusBusyReg(1)
            # raise AssertionError("This node should be optimized out if state of the loop can't change", self)

        elif self.fromEnter and not self.fromExitToHeaderNotify:
            # this is an infinite loop which has a predecessor, once started it will be closed for new starts
            # :attention: we pick the data from any time because this is kind of back edge
            assert newExe is not NOT_SPECIFIED, (newExe, self)
            assert newExit is NOT_SPECIFIED, (newExit, self)
            If(newExe,
               statusBusyReg(1)
            )
        elif self.fromEnter and self.fromExitToHeaderNotify:
            # loop with a predecessor and successor
            assert newExe is not NOT_SPECIFIED, (newExe, self)
            assert newExit is not NOT_SPECIFIED, (newExit, self)
            becomesBusy = newExe & (newExit | ~statusBusyReg)
            becomesFree = ~newExe & newExit
            if isinstance(becomesBusy, HValue):
                if becomesBusy:
                    statusBusyReg(1)
                else:
                    if isinstance(becomesFree, HValue):
                        if becomesFree:
                            statusBusyReg(0)
                    else:
                        If(becomesFree,
                            statusBusyReg(0)
                        )
            else:
                resStm = If(becomesBusy,
                   statusBusyReg(1)
                )
                if isinstance(becomesFree, HValue):
                    if becomesFree:
                        resStm.Else(
                            statusBusyReg(0)
                        )
                else:
                    resStm.Elif(becomesFree,
                        statusBusyReg(0)
                    )

        elif not self.fromEnter and self.fromExitToHeaderNotify:
            # loop with no predecessor and successor
            assert newExe is NOT_SPECIFIED, (newExe, self)
            assert newExit is not NOT_SPECIFIED, (newExit, self)
            If(newExit,
               statusBusyReg(0)  # finished work
            )
        else:
            raise AssertionError("All cases should already be covered in this if", self)

        # create RTL signal expression base on operator type
        t = self.scheduledOut[0] + self.netlist.scheduler.epsilon
        netNodeToRtl = allocator.netNodeToRtl
        if newExit is NOT_SPECIFIED:
            busy = statusBusyReg
        else:
            busy = statusBusyReg & ~newExit

        netNodeToRtl[self.getBusyOutPort()] = TimeIndependentRtlResource(busy, t, allocator, False)
        # netNodeToRtl[self.getEnterOutPort()] = TimeIndependentRtlResource(~statusBusyReg, t, allocator, False)
        for _, (channelGroup, portOut) in bbNumberToPortsSorted:
            s = portGroupSigs[channelGroup]
            if isinstance(portOut, HlsNetNodeIn):
                # exits don't have portOut
                continue
            elif channelGroup in self.fromReenter:
                s = s & statusBusyReg
            elif channelGroup in self.fromEnter:
                if newExit is NOT_SPECIFIED:
                    s = s & ~statusBusyReg
                else:
                    s = s & (~statusBusyReg | newExit)
            else:
                raise AssertionError("unknown type of port node", channelGroup)

            allocator.netNodeToRtl[portOut] = TimeIndependentRtlResource(
                    s, self.scheduledOut[portOut.out_i], allocator, False)

        res = netNodeToRtl[self] = []
        return res

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        for g in chain(self.fromEnter, self.fromReenter, self.fromExitToHeaderNotify):
            for w in g.members:
                yield w.associatedRead

    def __repr__(self):
        return f"<{self.__class__.__name__:s}{' ' if self.name else ''}{self.name} {self._id:d}{' isEnteredOnExit' if self._isEnteredOnExit else ''}>"

