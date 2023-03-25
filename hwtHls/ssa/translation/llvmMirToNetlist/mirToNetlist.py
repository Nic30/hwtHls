from typing import Set, Tuple, List

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.types.defs import BIT
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, \
    MachineInstr, TargetOpcode, MachineLoop
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge, \
    HlsNetNodeWriteBackwardEdge, BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopGate import HlsLoopGate
from hwtHls.netlist.nodes.orderable import HVoidData
from hwtHls.netlist.nodes.ports import HlsNetNodeOutLazy, \
    link_hls_nodes, HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.ssa.translation.llvmMirToNetlist.branchOutLabel import BranchOutLabel
from hwtHls.ssa.translation.llvmMirToNetlist.datapath import HlsNetlistAnalysisPassMirToNetlistDatapath, \
    BlockLiveInMuxSyncDict
from hwtHls.ssa.translation.llvmMirToNetlist.opCache import MirToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MachineBasicBlockSyncContainer, \
    getTopLoopForBlock, HlsNetNodeExplicitSyncInsertBehindLazyOut, _createSyncForAnyInputSelector
from hwtHls.ssa.translation.llvmMirToNetlist.resetValueExtract import ResetValueExtractor


class HlsNetlistAnalysisPassMirToNetlist(HlsNetlistAnalysisPassMirToNetlistDatapath):
    """
    This object translates LLVM MIR to hwtHls HlsNetlist (this class specifically contains control related things)

    When converting from MIR we are using:
    * Forward analysis of block synchronization type to avoid complexities on synchronization type change.
    * Each ordering between IO is strictly specified (can be specified to none). This is used to generate channel synchronization
      flags and to improve thread level parallelism.
    * MIR object may override its translation. This is used to implemented various plugins with minimum effort.
      For example the read from some interface may lower itself to multiple nodes which will implement bus protocol.
    * Loops and backedges are handled explicitly. The loop recognizes "break", "continue", "predecessor" branches and has internal state
      which describes if the loop is bussy or not. This state is used to control individual channels.

    Errors in synchronization are usually caused faulty user input. For example if the user code can contain obvious deadlock.
    But the main problem is that for an user it is nearly impossible to debug this if tool implements
    the synchronization for the circuit (which is the case). From this reason a translation from MIR to netlist must be done
    1 to 1 as much as possible. The goal is to be able to find ordering and buffer depletion errors from MIR and from the timeline
    and to have a method to specify the ordering for any node.


    The problem of channel synchronization when translating from MIR:
    * The MIR is assembler like format, control flow is specified as a position in code and data is globally visible.
      Reads and writes do happen one by one.
    * In netlist the control flow is represented as a enable flag, any instruction can run in parallel if restrictions allow it.
    * The :class:`hwtLib.handshaked.streamNode.StreamNode` uses extraCond,skipWhen notation to build arbitrary
      IO synchronization, but the problem is that we have to avoid combinational loops and deadlocks.
    * Resolving of this condition is hard to debug because the thing does not have any linear code flow.
       * From this reason we need to

    Consider this example:
    * Code simply adds incoming values from "channels" if there is an incoming data from every channel,
      and continuously writing sum to output "out".

    .. code-block:: Python

        x = 0
        # a channel with a control flag from predecessor of the loop which will be read only if loop is not running
        # to execute the loop
        while True:
            # value of 'x' is passed from end of the loop to loop header using backedge buffer,
            # which is a hidden IO of the loop body and header
            # We also need a flag which describes the predecessor of this block, for this we need:
            #  * a backedge buffer from the end of loop body will be read only if the loop is running
            if all(ch.hasData() for ch in channels):
                for ch in channels:
                    x += ch.read()
            out.write(x)

    * It is easy to see that if everything is scheduled to 1 clock cycle all input channels have to provide the data
      and out must be ready to accept the data (the hidden channels for "x" and control will be always ready).

    * However consider this modification:

    .. code-block:: Python

        x = 0
        while True:
            if all(ch.hasData() for ch in channels):
                for ch in channels:
                    if x == 10:
                       delay(2*clkPeriod)
                    x += ch.read()

            out.write(x)

    * With code branches where which do not have a constant duration there is this problem:
      There are multiple times when "ch" can be read which is likely to result in modification of order in which "channels" are read.
      This may result in deadlock (e.g. one of the "channels" is "out" and second of "channels" is "out" 1 clk delayed).
    """

    def extractRstValues(self, mf: MachineFunction, threads: HlsNetlistAnalysisPassDataThreadsForBlocks):
        return ResetValueExtractor(self.builder, self.valCache, self.liveness, self.loops, self.blockSync, self.regToIo).apply(mf, threads)

    def _resolveBranchEnFromPredecessor(self, pred: MachineBasicBlock, mb: MachineBasicBlock):
        """
        Resolve expression which specifies if CFG jumps to a specified block from specified predecessor.
        """
        builder = self.builder
        fromPredBrCond = None  # condition which controls if the control moves to mb block
        predEn = self.blockSync[pred].blockEn  # condition which specifies if the control is in pred block
        # :note: there can be multiple terminators in each block and we have to resolve
        #        fromPredBrCond from all of them
        for ter in pred.terminators():
            ter: MachineInstr
            opc = ter.getOpcode()
            # predEn = self.blockSync[pred].blockEn

            if opc == TargetOpcode.G_BR:
                # mb is only successor of pred, we can use en of pred block
                assert mb == ter.getOperand(0).getMBB(), ("This must be branch to mb", mb, ter)

            elif opc == TargetOpcode.G_BRCOND:
                # mb is conditional successor of pred, we need to use end of pred and branch cond to get en fo mb
                c, dstBlock = ter.operands()
                assert c.isReg(), c
                assert dstBlock.isMBB(), dstBlock
                c = self._translateRegister(pred, c.getReg())
                dstBlock = dstBlock.getMBB()
                if dstBlock != mb:
                    c = builder.buildNot(c)

                if fromPredBrCond is None:
                    fromPredBrCond = builder.buildAnd(predEn, c)
                else:
                    fromPredBrCond = builder.buildNot(fromPredBrCond)
                    fromPredBrCond = builder.buildAndVariadic((fromPredBrCond, predEn, c))

                if dstBlock == mb:
                    break

            elif opc == TargetOpcode.PseudoRET:
                raise AssertionError("This block is not predecessor of mb if it ends with return.", pred, mb)
            else:
                raise NotImplementedError("Unknown terminator", ter)

        return fromPredBrCond, predEn

    def _resolveEnFromPredecessors(self, mb: MachineBasicBlock,
                                   mbSync: MachineBasicBlockSyncContainer,
                                   backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]]) -> List[HlsNetNodeOutLazy]:
        """
        :note: we generate enFromPredccs even if the block does not need control because it may still require require enFromPredccs
            for input MUXes
        :return: list of control en flag from any predecessor
        """

        valCache: MirToHwtHlsNetlistOpCache = self.valCache
        # construct CFG flags
        enFromPredccs = []
        brCond = None

        for pred in mb.predecessors():
            pred: MachineBasicBlock
            fromPredBrCond = None  # condition which controls if the control moves to mb block
            predEn = self.blockSync[pred].blockEn  # condition which specifies if the control is in pred block
            if mbSync.needsControl:
                fromPredBrCond, predEn = self._resolveBranchEnFromPredecessor(pred, mb)

            if fromPredBrCond is None and mbSync.needsControl:
                fromPredBrCond = predEn

            if (pred, mb) in backedges:
                _fromPredBrCond = fromPredBrCond
                if mbSync.needsControl:
                    # we need to insert backedge buffer to get block en flag from pred to mb
                    # [fixme] write order must be asserted because we can not release a control token until all block operations finished
                    assert fromPredBrCond is not None, fromPredBrCond
                    valCache.add(pred, BranchOutLabel(mb), fromPredBrCond, False)  # the BranchOutLabel is set only once
                    v = self.builder.buildConst(HVoidData.from_py(None))
                    fromPredBrCond = self._constructBackedgeBuffer("c", pred, mb, None, v, isControl=True)
                    wn: HlsNetNodeWriteBackwardEdge = fromPredBrCond.obj.associated_write
                    self._addExtraCond(wn, _fromPredBrCond, predEn)
                    self._addSkipWhen_n(wn, _fromPredBrCond, predEn)
                    if mbSync.rstPredeccessor is not None:
                        assert not wn.channel_init_values
                        # we must add CFG token because we removed rst predecessor and now
                        # the circuit does not have way to start
                        wn.channel_init_values = (tuple(),)

                for _, srcMb, srcVal in mbSync.backedgeBuffers:
                    srcMb: MachineBasicBlock
                    srcVal: HlsNetNodeReadBackwardEdge
                    if srcMb != pred:
                        continue
                    wn: HlsNetNodeWriteBackwardEdge = srcVal.obj.associated_write
                    self._addExtraCond(wn, 1, _fromPredBrCond)
                    self._addSkipWhen_n(wn, 1, _fromPredBrCond)

            elif mbSync.needsControl and fromPredBrCond is not None:
                # brCond is a normal branch signal
                valCache.add(pred, BranchOutLabel(mb), fromPredBrCond, False)  # the BranchOutLabel is set only once

            elif mbSync.needsControl:
                if mbSync.rstPredeccessor is pred:
                    # skip because all live ins were inlined to backedge buffer initialization
                    continue
                else:
                    raise NotImplementedError("No control from predecessor but block needs control")

            if mbSync.needsControl:
                assert fromPredBrCond is not None, (mb.getName(), mb.getNumber())
                valCache.add(mb, pred, fromPredBrCond, False)
                # because we need to use latest value not the input value which we just added (r_from_in)
                brCond = valCache.get(mb, pred, fromPredBrCond._dtype)
                enFromPredccs.append(brCond)
            else:
                assert brCond is None, brCond
                brCond = self._translateIntBit(1)
                valCache.add(mb, pred, brCond, False)
                brCond = None

        return enFromPredccs

    def _resolveLoopExits(self, loopGate: HlsLoopGate, loop: MachineLoop, headerBlock: MachineBasicBlock):
        valCache: MirToHwtHlsNetlistOpCache = self.valCache
        netlist: HlsNetlistCtx = self.netlist

        for (exitBloc, exitSucBlock) in loop.getExitEdges():
            # if exiting loop return token to HlsLoopGate
            mbSync = self.blockSync[exitBloc]
            _control = valCache.get(exitBloc, BranchOutLabel(exitSucBlock), BIT)
            v = self.builder.buildConst(HVoidData.from_py(None))
            control = self._constructBackedgeBuffer(f"c_loop{loopGate._id}Exit", exitBloc, headerBlock, None, v, isControl=True)
            wn: HlsNetNodeWriteBackwardEdge = control.obj.associated_write
            wn.allocationType = BACKEDGE_ALLOCATION_TYPE.IMMEDIATE

            self._addExtraCond(wn, _control, mbSync.blockEn)
            self._addSkipWhen_n(wn, _control, mbSync.blockEn)

            controlSync = HlsNetNodeExplicitSync(netlist, control._dtype)
            self.nodes.append(controlSync)
            link_hls_nodes(control.obj.getValid(), controlSync._inputs[0])
            loopGate.connectExit(controlSync._outputs[0])

    def _resolveLoopInputSync(self, mb: MachineBasicBlock,
                              mbSync: MachineBasicBlockSyncContainer,
                              loopGate: HlsLoopGate,
                              loop: MachineLoop,
                              blockLiveInMuxInputSync: BlockLiveInMuxSyncDict):
        valCache: MirToHwtHlsNetlistOpCache = self.valCache
        netlist: HlsNetlistCtx = self.netlist
        builder = self.builder
        # in a format of tuples (control, allInputDataChannels)
        loopReenters: List[Tuple[HlsNetNodeExplicitSync, List[HlsNetNodeExplicitSync]]] = []
        loopExecs: List[Tuple[HlsNetNodeExplicitSync, List[HlsNetNodeExplicitSync]]] = []
        for pred in mb.predecessors():
            if mbSync.rstPredeccessor and pred == mbSync.rstPredeccessor:
                # :note: rstPredeccessor will is inlined
                continue

            # [fixme] the inputs from before the loop are not guaranteed to be stable
            #         maybe loop initialization should be handled differently
            # * where the state should be kept? predecessor or the successor?
            #   * predecessor has storage facility, however this may limit pipelining
            #   * there is a problem that the input from predecessor starts the loop
            #     this signal controls input loop body input muxes, in this specific case
            #     the optimization of synchronization does not work because the the synchronization
            #     for this signal drives just input mux but does not touch the input ports itself
            #      * this results in the situation when inputs are required and the input is consummed
            #        but the loop inputs should be skiped and this input token should swith loop to a bussy state

            # insert explicit sync on control input
            control = valCache.get(mb, pred, BIT)
            if isinstance(control, HlsNetNodeOut):
                assert isinstance(control, HlsNetNodeReadBackwardEdge), control
            else:
                assert isinstance(control, HlsNetNodeOutLazy), (
                    "Branch control from predecessor must be lazy output because we did not connect it from pred block yet.",
                    mb, pred, control)
                _control = HlsNetNodeExplicitSyncInsertBehindLazyOut(netlist, valCache, control)
                control = _control

            allInputDataChannels: List[HlsNetNodeExplicitSync] = []
            for liveIn in self.liveness[pred][mb]:
                if liveIn in self.regToIo:
                    continue

                liveInSync: HlsNetNodeExplicitSync = blockLiveInMuxInputSync[(pred, mb, liveIn)]
                allInputDataChannels.append(liveInSync)

            if loop.containsBlock(pred):
                loopGate.connectReenter(control._outputs[0])
                loopReenters.append((control, allInputDataChannels))
            else:
                loopGate.connectEnter(control._outputs[0])
                loopExecs.append((control, allInputDataChannels))

        # loopBussy select if loop should process inputs from loopReenters or from loopExecs
        loopBusy = loopGate._sync_token_status._outputs[0]
        loopBusy_n = builder.buildNot(loopBusy)
        _createSyncForAnyInputSelector(builder, loopReenters, loopBusy, loopBusy_n)
        _createSyncForAnyInputSelector(builder, loopExecs, loopBusy_n, loopBusy)

    def resolveLoopHeaders(self,
                           mf: MachineFunction,
                           blockLiveInMuxInputSync: BlockLiveInMuxSyncDict):
        """
        Construct the loop control logic at the header of the loop.
        """
        netlist: HlsNetlistCtx = self.netlist
        for mb in mf:
            mb: MachineBasicBlock
            mbSync: MachineBasicBlockSyncContainer = self.blockSync[mb]

            if mbSync.needsControl and mb.pred_size() > 2 or mbSync.rstPredeccessor is None:
                # The loop gate is required if this block is loop and body can be entered from multiple blocks
                # we need this component to manage status of the loop and to assert order of loop body executions
                loop = self.loops.getLoopFor(mb)
                if loop is not None and loop.getHeader() == mb:
                    loop: MachineLoop
                    topLoop = getTopLoopForBlock(mb, loop)
                    # build 1 HlsLoopGate for all loops which do have this block as a header
                    # [fixme] loop may have just 2 predecessors and required loop gate
                    # [fixme] The loop gate is instantiated only for top loop,
                    #     The purpose of loop gate is to select input data for the loop body.
                    #     If this block is a header of multiple loops there must be multiple loop header to enable a correct subset of backedges.
                    loopGate = HlsLoopGate(netlist, f"loop_bb_{mb.getNumber():d}")
                    self.nodes.append(loopGate)
                    self.nodes.append(loopGate._sync_token_status)
                    self._resolveLoopExits(loopGate, topLoop, mb)
                    self._resolveLoopInputSync(mb, mbSync, loopGate, topLoop, blockLiveInMuxInputSync)

    def resolveBlockEn(self, mf: MachineFunction,
                       threads: HlsNetlistAnalysisPassDataThreadsForBlocks):
        """
        Resolve control flow enable for instructions in the block.
        """
        builder = self.builder
        backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]] = self.backedges
        for mb in mf:
            mb: MachineBasicBlock
            # resolve control enable flag for a block
            mbSync: MachineBasicBlockSyncContainer = self.blockSync[mb]
            assert mbSync.block == mb

            if mbSync.needsStarter:
                if mbSync.needsControl:
                    # add starter and use it as en
                    n = HlsProgramStarter(self.netlist)
                    self.nodes.append(n)
                    blockEn = n._outputs[0]
                else:
                    # no en and extract the constants set there as a reset values
                    blockEn = None
            else:
                enFromPredccs = self._resolveEnFromPredecessors(mb, mbSync, backedges)
                if enFromPredccs and mbSync.needsControl:
                    if None in enFromPredccs:
                        raise AssertionError(enFromPredccs)
                    blockEn = builder.buildOrVariadic(enFromPredccs)
                else:
                    blockEn = None

            assert isinstance(mbSync.blockEn, HlsNetNodeOutLazy), (mbSync.blockEn, "Must not be resolved yet")

            if blockEn is None:
                # replace with '1' because there is nothing but internal presure blocking the block execution
                blockEn = 1

            if isinstance(blockEn, int) and blockEn == 1:
                for i in tuple(mbSync.blockEn.dependent_inputs):
                    i: HlsNetNodeIn
                    if isinstance(i, HlsNetNodeIn):
                        self._replaceInputDriverWithConst1b(i, threads)
                    else:
                        raise NotImplementedError(i)

                mbSync.blockEn.dependent_inputs.clear()
                blockEn = None

            if blockEn is None:
                assert not mbSync.blockEn.dependent_inputs, (mb, mbSync.blockEn.dependent_inputs)
            else:
                mbSync.blockEn.replaceDriverObj(blockEn)

            assert mbSync.blockEn.replaced_by is blockEn or not mbSync.blockEn.dependent_inputs, (mbSync.blockEn, blockEn)
            mbSync.blockEn = blockEn

    def connectOrderingPorts(self,
                             mf: MachineFunction):
        """
        Tinalize ordering connections after all IO is instantiated.
        """
        # cancel ordering between last IO at the end of the loop and write to control channel of that block
        # this allow for a new iteration to start before the end of previous one if data dependency allows it
        backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]] = self.backedges
        for mb in mf:
            mb: MachineBasicBlock
            orderingInputs = []
            for pred in mb.predecessors():
                pred: MachineBasicBlock
                if (pred, mb) not in backedges:
                    o = self.blockSync[pred].orderingOut
                    if o is not None:
                        orderingInputs.append(o)

            mbSync: MachineBasicBlockSyncContainer = self.blockSync[mb]
            if not orderingInputs:
                # must remove ordering because this is a first ordered operation and it does not have any ordering dependence
                for i in mbSync.orderingIn.dependent_inputs:
                    i.obj._removeInput(i.in_i)

                if mbSync.orderingIn is mbSync.orderingOut:
                    mbSync.orderingOut = None
                mbSync.orderingIn = None
            else:
                for last, i in iter_with_last(orderingInputs):
                    if last:
                        if mbSync.orderingIn is mbSync.orderingOut:
                            mbSync.orderingOut = i
                        mbSync.orderingIn.replaceDriverObj(i)
                    else:
                        for depI in mbSync.orderingIn.dependent_inputs:
                            depI: HlsNetNodeIn
                            # create a new input for ordering connection
                            depI2 = depI.obj._addInput("orderingIn")
                            link_hls_nodes(i, depI2)

    def run(self):
        raise NotImplementedError("This class does not have run() method because it is "
                                  "a special case customized for each build in Platform class. "
                                  "Use object netlist translation methods directly.")
