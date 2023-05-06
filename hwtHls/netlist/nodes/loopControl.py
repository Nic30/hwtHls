from typing import List, Optional, Generator, Union, Tuple, Dict, Set

from hwt.code import If, Or
from hwt.code_utils import rename_signal
from hwt.hdl.types.defs import BIT
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge, BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.explicitSync import IO_COMB_REALIZATION
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge, HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HVoidData, HlsNetNodeOrderable, \
    HVoidOrdering, HdlType_isVoid
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes, \
    HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite

HlsNetNodeLoopPortAny = Union[
    HlsNetNodeReadForwardedge,
    HlsNetNodeWriteForwardedge,
    HlsNetNodeReadBackedge,
    HlsNetNodeWriteBackedge]


class HlsNetNodeLoopStatus(HlsNetNodeOrderable):
    """
    This status node holds the state of execution of all loops for some loop header block.
    It locks enter ports while the loop body is running to assert that loop exits before it takes new data.

    Not all hardware loops necessary need this:
    * Top loops with a single predecessor may have this predecessor liveIn variables values inlined to an initialization
      of backedges of this loop if all values comming from this predecessor are constant.
      (This removes enter to loop which is important for next items in this list.)
    * Loops with no enter and exit do not need this as they are always running.
    * Loops with no enter and no live variables on reenter edges do not need this as there are no inter iteration dependencies.

    :attention: Loop ports may be shared betwen loops. E.g. one exit may be also enter to other loop and also exit from parent loop.
    :attention: Loop ports may hold data if some data channel is resused as a control.
    :attention: For correct functionality the loop body must be separated from rest of the circuit.
        This is required because various blocking operations which are not inside of the loop must be separated.
    :attention: There should be ordering connected from last IO in the loop to achieve better results in
        :meth:`~.HlsNetNodeLoopStatus.scheduleAlapCompaction` because without it this does not have any outputs
        and will stay at the end of current cycle which is sub-optimal if the whole loop shifts in time.
    :note: This node does not contain any multiplexers or explicit synchronization it is just a state-full control logic
        which provides "enable signals".

    :note: For nested loops the top loop is always guaranted to be bussy if child is.
        If the child has same header block as parent, the children status is most important. Because we need to continue executing the lowest loop.

    :ivar fromEnter: for each direct predecessor which is not in cycle body a tuple input for control and variable values.
        Signalizes that the loop has data to be executed.
    :ivar fromReenter: For each direct predecessor which is a part of a cycle body a tuple control input and associated variables.
        Note that the channels are usually connected to out of pipeline interface because the HlsNetlistCtx does not support cycles.
    :ivar fromExit: For each block which is part of the cycle body and does have transition outside of the cycle a control input
        to mark the return of the synchronization token.
    """

    def __init__(self, netlist:"HlsNetlistCtx", name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        # :note: other outputs are added for each predecessor for the block where loop is
        #    ports are used to separate loop body from circuit outside of loop
        # self._addOutput(BIT, "canEnter")
        self._addOutput(HVoidOrdering, "orderingOut")
        self._addOutput(BIT, f"busy")

        self.debugUseNamedSignalsForControl = False
        # a dictonary port node -> RtlSignal
        self._rtlPortNodeSigs: Dict[HlsNetNodeLoopPortAny, RtlSignal] = {}
        self._rtlAllocated = False

        self.fromEnter: List[Union[HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge]] = []
        self.fromReenter: List[Union[HlsNetNodeReadBackedge]] = []
        self.fromExit: List[Union[HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge]] = []

        self._bbNumberToPorts: Dict[tuple(int, int), Tuple[HlsNetNodeLoopPortAny, HlsNetNodeOut]] = {}
        self._isEnteredOnExit: bool = False

    def filterSubnodes(self, removed:Set["HlsNetNode"]):
        builder = self.netlist.builder
        toRm = []
        for srcDst, (portNode, outPort) in self._bbNumberToPorts.items():
            outPort: HlsNetNodeOut
            if portNode in removed:
                if outPort is not None:  # None=exit port
                    uses = self.usedBy[outPort.out_i]
                    if uses:
                        if portNode in self.fromEnter and\
                                len(self.fromEnter) == 1:
                            exits = [e for e in self.fromExit if e not in removed]
                            if exits:
                                # implicit enter = enter on any exit
                                enterReplacement = builder.buildOrVariadic(tuple(n.associatedRead.getValidNB() for n in exits))
                                e0: HlsNetNodeWriteBackedge = exits[0]
                                assert HdlType_isVoid(e0.associatedRead._outputs[0]._dtype), (e0, "This must be of void type because it only triggers the loop exit")
                                assert not e0.channelInitValues, (e0, e0.channelInitValues)
                                e0.channelInitValues = ((),)
                                self._isEnteredOnExit = True
                                
                            else:
                                # build enter = not any(reenter)
                                # or  enter = 1 if len(reenter) == 0
                                reenters = []
                                for e in self.fromReenter:
                                    if e in removed:
                                        continue
                                    found = False
                                    for (pn, op) in self._bbNumberToPorts.values():
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
                            
                            bussyO = self.getBussyOutPort()
                            if self.usedBy[bussyO.out_i]:
                                # this loop is always bussy and this node will probably be removed in next step of optimization
                                builder.replaceOutput(bussyO, builder.buildConstBit(1), True)

                        else:
                            raise NotImplementedError(self, srcDst, portNode)
                            
                    assert not self.usedBy[outPort.out_i], ("If port should be removed it should be disconnected first", outPort)
                    self._removeOutput(outPort.out_i)
                toRm.append(srcDst)

        for srcDst in toRm:
            self._bbNumberToPorts.pop(srcDst)

        self.fromEnter[:] = (n for n in self.fromEnter if n not in removed)
        self.fromReenter[:] = (n for n in self.fromReenter if n not in removed)
        self.fromExit[:] = (n for n in self.fromExit if n not in removed)

    def getBussyOutPort(self) -> HlsNetNodeOut:
        return self._outputs[1]

    def getOrderingOutPort(self) -> HlsNetNodeOut:
        return self._outputs[0]

    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

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
        
        isAlwaysBussy = self._isEnteredOnExit and not self.fromEnter
        if isAlwaysBussy:
            statusBusyReg = BIT.from_py(1)
        else:
            statusBusyReg = allocator._reg(
                f"{name:s}_busy",
                def_val=0 if self.fromEnter else 1)  # busy if is executed at 0 time
        bbNumberToPortsSorted = sorted(self._bbNumberToPorts.items(), key=lambda x: x[0])
        portNodeSigs = self._rtlPortNodeSigs
        for _, (portNode, portOut) in bbNumberToPortsSorted:
            s = allocator._sig(f"{name:s}_{portNode.name:s}" if portOut is None else f"{name:s}_{portOut.name:s}")
            portNodeSigs[portNode] = s

        useNamedSignals = self.debugUseNamedSignalsForControl
        parentU = self.netlist.parentUnit

        # has the priority and does not require sync token (because it already owns it)
        assert self.fromReenter, (self, "Must have some reenters otherwise this is not the loop")
        for portNode in self.fromReenter:
            s = portNodeSigs[portNode]
            s(self._resolveBackedgeDataRtlValidSig(portNode))

        newExit = NOT_SPECIFIED
        if self.fromExit:
            # returns the control token
            fromExit = []
            for portNode in self.fromExit:
                # e.allocateRtlInstance(allocator)
                s = portNodeSigs[portNode]
                fromExit.append(s)
                assert isinstance(portNode, HlsNetNodeWriteBackedge)
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
            for portNode in self.fromEnter:
                portNode._allocateRtlIo()
                _s = portNodeSigs[portNode]
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
        if isAlwaysBussy:
            pass
        
        elif not self.fromEnter and not self.fromExit:
            # this is infinite loop without predecessor, it will run infinitely but in just one instance
            assert newExe is NOT_SPECIFIED, newExe
            assert newExit is NOT_SPECIFIED, newExit
            statusBusyReg(1)
            # raise AssertionError("This node should be optimized out if state of the loop can't change", self)

        elif self.fromEnter and not self.fromExit:
            # this is an infinite loop which has a predecessor, once started it will be closed for new starts
            # :attention: we pick the data from any time because this is kind of back edge
            assert newExe is not NOT_SPECIFIED, newExe
            assert newExit is NOT_SPECIFIED, newExit
            If(newExe,
               statusBusyReg(1)
            )
        elif self.fromEnter and self.fromExit:
            # loop with a predecessor and successor
            assert newExe is not NOT_SPECIFIED, newExe
            assert newExit is not NOT_SPECIFIED, newExit
            becomesBussy = newExe & ~newExit
            becomesFree = ~newExe & newExit
            if isinstance(becomesBussy, HValue):
                if becomesBussy:
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
                resStm = If(becomesBussy,
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

        elif not self.fromEnter and self.fromExit:
            # loop with no predecessor and successor
            assert newExe is NOT_SPECIFIED, newExe
            assert newExit is not NOT_SPECIFIED, newExit
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
        netNodeToRtl[self.getBussyOutPort()] = TimeIndependentRtlResource(busy, t, allocator, False)
        # netNodeToRtl[self.getEnterOutPort()] = TimeIndependentRtlResource(~statusBusyReg, t, allocator, False)
        for _, (portNode, portOut) in bbNumberToPortsSorted:
            s = portNodeSigs[portNode]
            if isinstance(portOut, HlsNetNodeIn):
                # exits don't have portOut
                continue
            elif portNode in self.fromReenter:
                s = s & statusBusyReg
            elif portNode in self.fromEnter:
                if newExit is NOT_SPECIFIED:
                    s = s & ~statusBusyReg
                else:
                    s = s & (~statusBusyReg | newExit)
            else:
                raise AssertionError("unknown type of port node", portNode)

            allocator.netNodeToRtl[portOut] = TimeIndependentRtlResource(
                    s, self.scheduledOut[portOut.out_i], allocator, False)

        res = netNodeToRtl[self] = []
        return res

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        yield from self.fromReenter
        yield from self.fromExit

    def _connectVoidDataConst(self, w: HlsNetNodeWrite):
        v = self.netlist.builder.buildConst(HVoidData.from_py(None))
        link_hls_nodes(v, w._inputs[0])

    def addEnterPort(self, srcBlockNumber: int, dstBlockNumber: int, r: HlsNetNodeReadBackedge)\
            ->Tuple[HlsNetNodeRead, HlsNetNodeOut]:
        """
        Register connection of control and data from some block which causes the loop to to execute.

        :note: When transaction on this IO is accepted the loop sync token is changed to bussy state if not overriden by exit.
        :note: Loop can be executed directly after reset. This implies that the enter ports are optional. However enter or exit port must be present,
            otherwise this loop status node is not required at all because
        """
        name = f"enterFrom_bb{srcBlockNumber:}"
        fromStatusOut = self._addOutput(BIT, name)
        # w: HlsNetNodeWrite = None
        # if controlPortObj is None:
        #    w, r = HlsNetNodeLoopEnterRead.createPredSucPair(self, srcBlockNumber)
        #    self._connectVoidDataConst(w)
        # else:
        assert isinstance(r, HlsNetNodeRead), r
        w = r.associatedWrite

        link_hls_nodes(w.getOrderingOutPort(), self._addInput("orderingIn"))
        self.fromEnter.append(r)
        self._bbNumberToPorts[(srcBlockNumber, dstBlockNumber)] = (r, fromStatusOut)
        return r, fromStatusOut

    def addReenterPort(self, srcBlockNumber: int, dstBlockNumber: int, r: HlsNetNodeReadBackedge)\
            ->Tuple[HlsNetNodeRead, HlsNetNodeOut]:
        """
        Register connection of control and data from some block where control flow gets back block where the cycle starts.

        :note: When transaction on this IO is accepted the loop sync token is reused
        """
        name = f"reenterFrom_bb{srcBlockNumber}"
        fromStatusOut = self._addOutput(BIT, name)
        assert isinstance(r, HlsNetNodeReadBackedge), r

        # if controlPortObj is None:
        #    w = HlsNetNodeWriteBackedge(self.netlist, name=f"{name}_in")
        #    self.netlist.outputs.append(w)
        #    r = HlsNetNodeReadControlBackedge(self.netlist, HVoidOrdering, name=f"{name}_out")
        #    w.associateRead(r)
        #    link_hls_nodes(r.getOrderingOutPort(), w._addInput("orderingIn"))
        #    self.netlist.inputs.append(r)
        #    self._connectVoidDataConst(w)
        # else:
        self.fromReenter.append(r)
        self._bbNumberToPorts[(srcBlockNumber, dstBlockNumber)] = (r, fromStatusOut)
        return r, fromStatusOut

    def addExitPort(self, srcBlockNumber: int, dstBlockNumber: int, w: HlsNetNodeWriteBackedge)\
            ->HlsNetNodeWrite:
        """
        Register connection of control which causes to break current execution of the loop.

        :note: When transaction on this IO is accepted the loop sync token returned to ready state.
        :note: the loop may not end this implies that this may not be used at all.
        """
        # if controlPortObj is None:
        #    if isBackedge:
        #        w, r = HlsNetNodeLoopExitWriteBackedge.createPredSucPair(self, srcBlockNumber)
        #    else:
        #        w, r = HlsNetNodeLoopExitWrite.createPredSucPair(self, srcBlockNumber)
        #    self._connectVoidDataConst(w)
        # else:
        assert isinstance(w, HlsNetNodeWriteBackedge), w
        # d = HlsNetNodeDelayClkTick(self.netlist, 1, HVoidOrdering, "loopExitDelay")
        # self.netlist.nodes.append(d)
        # link_hls_nodes(self.getOrderingOutPort(), d._inputs[0])
        # link_hls_nodes(d._outputs[0], r._addInput("orderingIn"))
        r = w.associatedRead
        exitIn = self._addInput(f"exit_from_bb{srcBlockNumber:d}_to_bb{dstBlockNumber:d}", True)
        link_hls_nodes(r.getValidNB(), exitIn)

        self.fromExit.append(w)
        self._bbNumberToPorts[(srcBlockNumber, dstBlockNumber)] = (w, exitIn)
        return w

    def __repr__(self):
        return f"<{self.__class__.__name__:s}{' ' if self.name else ''}{self.name} {self._id:d}>"

