from typing import Set, Tuple, Dict, List, Union, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.defs import BIT
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, \
    MachineInstr, TargetOpcode, MachineLoop
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge, \
    HlsNetNodeWriteBackwardEdge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopHeader import HlsLoopGate
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutLazy, \
    link_hls_nodes, unlink_hls_nodes, HlsNetNodeOutAny, HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.datapath import HlsNetlistAnalysisPassMirToNetlistDatapath, \
    BlockLiveInMuxSyncDict
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.opCache import MirToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer, \
    getTopLoopForBlock, BranchOutLabel, HlsNetNodeExplicitSyncInsertBehindLazyOut


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

    def _rewriteControlOfInfLoopWithReset(self, mb: MachineBasicBlock, rstPred: MachineBasicBlock):
        """
        Detect which predecessor is reset and which is continue from loop body.
        Inline MUX values for reset as backedge channel initialization.
        
        :param mb: header block of this loop
        """
        valCache = self.valCache
        # :note: resetPredEn and otherPredEn do not need to be specified if reset actually does not reset anything
        #        only one can be specified if the value for other in MUXes is always default value which does not have condition
        resetPredEn: Optional[HlsNetNodeOutAny] = None
        otherPredEn: Optional[HlsNetNodeOutAny] = None
        topLoop: MachineLoop = self.loops.getLoopFor(mb)
        assert topLoop, (mb, "must be a loop with a reset otherwise it is not possible to extract the reset")
        topLoop = getTopLoopForBlock(mb, topLoop)
        
        for pred in mb.predecessors():
            enFromPred = valCache._toHlsCache.get((mb, pred), None)
            # if there are multiple predecessors this is a loop with reset
            # otherwise it is just a reset
            if pred is rstPred:
                assert not topLoop.containsBlock(pred)
                assert resetPredEn is None
                resetPredEn = enFromPred
            else:
                assert topLoop.containsBlock(pred)
                assert otherPredEn is None
                otherPredEn = enFromPred
     
        if resetPredEn is None and otherPredEn is None:
            # case where there are no live variables and thus no reset value extraction is required
            for pred in mb.predecessors():
                for r in self.liveness[pred][mb]:
                    r: Register
                    assert r in self.regToIo, (r, "Block is supposed to have no live in registers because any en from predecessor was not used in input mux")
            return
                
        assert resetPredEn is None or isinstance(resetPredEn, HlsNetNodeOutLazy), (resetPredEn, "Must not be resolved yet.")
        assert otherPredEn is None or isinstance(otherPredEn, HlsNetNodeOutLazy), (otherPredEn, "Must not be resolved yet.")
        
        # must copy because we are updating it
        if resetPredEn is None:
            dependentOnControlInput = tuple(otherPredEn.dependent_inputs)
        elif otherPredEn is None:
            dependentOnControlInput = tuple(resetPredEn.dependent_inputs)
        else:
            dependentOnControlInput = resetPredEn.dependent_inputs + otherPredEn.dependent_inputs
        
        builder = self.builder
        alreadyUpdated: Set[HlsNetNode] = set()
        for i in dependentOnControlInput:
            # en from predecessor should now be connected to all MUXes as some selector/condition
            # we search all such MUXes and propagate selected value to backedge
            # :note: The MUX must be connected to a single backedge because otherwise
            #        the it would not be possible to replace control with reset in the first place
            mux = i.obj
            if mux in alreadyUpdated:
                continue

            assert isinstance(mux, HlsNetNodeMux), mux
            mux: HlsNetNodeMux
            # pop reset value to initialization of the channel
            backedgeBuffRead: Optional[HlsNetNodeReadBackwardEdge] = None
            assert len(mux.dependsOn) == 3, mux
            (v0I, v0), (condI, cond), (vRstI, vRst) = zip(mux._inputs, mux.dependsOn)
            if cond is resetPredEn:
                # vRst cond v0
                (v0, v0I), (vRst, vRstI) = (vRst, vRstI), (v0, v0I)  
            elif cond is otherPredEn:
                # v0 cond vRst
                pass
            else:
                raise AssertionError("Can not recognize reset value in MUX in loop header")

            # find backedge buffer on value from loop body
            while (isinstance(v0, HlsNetNodeOut) and 
                   isinstance(v0.obj, HlsNetNodeExplicitSync) and
                   not isinstance(v0.obj, HlsNetNodeReadBackwardEdge)):
                v0 = v0.obj.dependsOn[0]
            assert isinstance(v0, HlsNetNodeOut) and isinstance(v0.obj, HlsNetNodeReadBackwardEdge), (mb, v0)
            backedgeBuffRead = v0.obj

            assert backedgeBuffRead is not None
            backedgeBuffRead: HlsNetNodeReadBackwardEdge
            rstValObj = vRst.obj
            while rstValObj.__class__ is HlsNetNodeExplicitSync:
                rstValObj = rstValObj.dependsOn[0].obj

            assert isinstance(rstValObj, HlsNetNodeConst), (
                "must be const otherwise it is impossible to extract this as reset",
                rstValObj)
            # add reset value to backedge buffer init
            init = backedgeBuffRead.associated_write.channel_init_values
            if init:
                raise NotImplementedError("Merge init values")
            else:
                t = rstValObj.val._dtype
                assert t == backedgeBuffRead._outputs[0]._dtype, (backedgeBuffRead, t, backedgeBuffRead._outputs[0]._dtype)
                assert t == mux._outputs[0]._dtype, (mux, t, mux._outputs[0]._dtype)
                backedgeBuffRead.associated_write.channel_init_values = ((int(rstValObj.val),),)

            # pop mux inputs for reset
            builder.unregisterOperatorNode(mux)
            unlink_hls_nodes(vRst, vRstI)
            mux._removeInput(vRstI.in_i)  # remove reset input which was moved to backedge buffer init
            unlink_hls_nodes(cond, condI)
            mux._removeInput(condI.in_i)  # remove condition because we are not using it
            builder.registerOperatorNode(mux)
            alreadyUpdated.add(mux)

    def extractRstValues(self, mf: MachineFunction, threads: HlsNetlistAnalysisPassDataThreads):
        """
        Rewrite multiplexor cases for reset to an initialization of channels.
        """
        for mb in mf:
            mb: MachineBasicBlock
            mbSync: MachineBasicBlockSyncContainer = self.blockSync[mb]
            
            if mbSync.rstPredeccessor:
                self._rewriteControlOfInfLoopWithReset(mb, mbSync.rstPredeccessor)
                
                for i in tuple(mbSync.blockEn.dependent_inputs):
                    i: HlsNetNodeIn
                    assert isinstance(i.obj, (HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeOperator)), i.obj
                    self._replaceInputDriverWithConst1b(i, threads)

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
        :returns: list of control en flag from any predecessor
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
                    fromPredBrCond = self._constructBackedgeBuffer("c", pred, mb, None, fromPredBrCond, isControl=True)
                    wn: HlsNetNodeWriteBackwardEdge = fromPredBrCond.obj.associated_write
                    self._addExtraCond(wn, _fromPredBrCond, predEn)
                    self._addSkipWhen_n(wn, _fromPredBrCond, predEn)

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

    def resolveLoopHeaders(self,
                           mf: MachineFunction,
                           blockLiveInMuxInputSync: BlockLiveInMuxSyncDict):
        """
        Construct the loop control logic at the header of the loop.
        """
        valCache: MirToHwtHlsNetlistOpCache = self.valCache
        netlist: HlsNetlistCtx = self.netlist
        builder = self.builder
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
                    loopGate = HlsLoopGate(netlist, f"loop_bb_{mb.getNumber():d}")
                    self.nodes.append(loopGate)
                    self.nodes.append(loopGate._sync_token_status)
    
                    for (exitBloc, exitSucBlock) in topLoop.getExitEdges():
                        # if exiting loop return token to HlsLoopGate
                        control = valCache.get(exitBloc, BranchOutLabel(exitSucBlock), BIT)
                        control = self._constructBackedgeBuffer("c_loopExit", exitBloc, mb, None, control)
                        # wn: HlsNetNodeWriteBackwardEdge = control.obj.associated_write
                        # self._addExtraCond(wn, control, mbSync.blockEn)
                        # self._addSkipWhen_n(wn, control, mbSync.blockEn)
                        
                        controlSync = HlsNetNodeExplicitSync(netlist, control._dtype)
                        self.nodes.append(controlSync)
                        link_hls_nodes(control, controlSync._inputs[0])
                        loopGate.connect_break(controlSync._outputs[0])

                    # in a format of tuples (control, allInputDataChannels)
                    loopReenters: List[Tuple[HlsNetNodeExplicitSync, List[HlsNetNodeExplicitSync]]] = []
                    loopExecs: List[Tuple[HlsNetNodeExplicitSync, List[HlsNetNodeExplicitSync]]] = [] 
                    for pred in mb.predecessors():
                        if mbSync.rstPredeccessor and pred == mbSync.rstPredeccessor:
                            # :note: rstPredeccessor will is inlined
                            continue
                        
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
                            loopGate.connect_reenter(control._outputs[0])
                            loopReenters.append((control, allInputDataChannels))                                
                        else:
                            loopGate.connect_predec(control._outputs[0])
                            loopExecs.append((control, allInputDataChannels))
                    
                    # loopBussy select if loop should process inputs from loopReenters or from loopExecs
                    loopBusy = loopGate._sync_token_status._outputs[0] 
                    loopBusy_n = builder.buildNot(loopBusy)
                    self._createSyncForAnyInputSelector(builder, loopReenters, loopBusy, loopBusy_n)
                    self._createSyncForAnyInputSelector(builder, loopExecs, loopBusy_n, loopBusy)

    @staticmethod
    def _createSyncForAnyInputSelector(builder: HlsNetlistBuilder,
                                       inputCases: List[Tuple[HlsNetNodeExplicitSync, List[HlsNetNodeExplicitSync]]],
                                       externalEn: HlsNetNodeOut,
                                       externalEn_n: HlsNetNodeOut):
        """
        Create a logic circuit which select a first control input which is valid and enables all its associated data inputs.
        :param inputCases: list of case tuple (control channel, all input data channels)
        """
        anyPrevVld = None
        for last, (control, data) in iter_with_last(inputCases):
            controlSrc = control.dependsOn[0]
            vld = builder.buildReadSync(controlSrc)
            vld_n = builder.buildNot(vld)
            control.add_control_extraCond(externalEn)
            if anyPrevVld is None:
                if last:
                    cEn = 1
                else:
                    cEn = vld_n

                # first item
                if data:
                    dEn = builder.buildAnd(externalEn_n, vld)
                    dSw = builder.buildOr(externalEn, builder.buildNot(vld))
                anyPrevVld = vld
            else:
                if last:
                    cEn = anyPrevVld
                else:
                    cEn = builder.buildOr(anyPrevVld, vld_n)
                    
                if data:
                    en = builder.buildAnd(builder.buildNot(anyPrevVld), vld)
                    dEn = builder.buildAnd(externalEn_n, en)
                    dSw = builder.buildOr(externalEn, builder.buildNot(en))
                anyPrevVld = builder.buildOr(anyPrevVld, vld)

            if isinstance(cEn, int):
                assert cEn == 1, cEn
                cEn = externalEn_n
            else:
                cEn = builder.buildOr(externalEn_n, cEn)

            control.add_control_skipWhen(cEn)
            for liveInSync in data:
                liveInSync.add_control_extraCond(dEn)
                liveInSync.add_control_skipWhen(dSw)

        return anyPrevVld

    def resolveBlockEn(self, mf: MachineFunction,
                       threads: HlsNetlistAnalysisPassDataThreads):
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

        self._injectVldMaskToSkipWhenConditions()

    def _injectVldMaskToExpr(self, out: HlsNetNodeOut) -> HlsNetNodeOut:
        """
        For channels which are read optionally we may have to mask incoming data if the data is used directly in this clock cycle
        to decide if some IO channel should be enabled.
        """
        assert isinstance(out, HlsNetNodeOut), (out, "When this function is called every output should be already resolved")
        outObj = out.obj
        builder = self.builder
        if isinstance(outObj, HlsNetNodeReadSync):
            return out, None

        elif isinstance(outObj, (HlsNetNodeRead, HlsNetNodeWrite)):
            maskToApply = builder.buildReadSync(out)

        elif isinstance(outObj, HlsNetNodeOperator):
            ops = []
            needsRebuild = False
            maskToApply = None
            for o in outObj.dependsOn:
                _o, _maskToApply = self._injectVldMaskToExpr(o)
                ops.append(_o)
                if _o is not o:
                    needsRebuild = True
                if _maskToApply is not None:
                    if maskToApply is None:
                        maskToApply = _maskToApply
                    elif maskToApply is not _maskToApply:
                        maskToApply = builder.buildAnd(maskToApply, _maskToApply)
                    else:
                        pass

            if needsRebuild:
                if outObj.operator == AllOps.AND:
                    out = builder.buildAnd(*ops)
                elif isinstance(outObj, HlsNetNodeMux):
                    out = builder.buildMux(out._dtype, tuple(ops))
                else:
                    out = builder.buildOp(outObj.operator, out._dtype, *ops)

        elif isinstance(outObj, HlsNetNodeExplicitSync):
            # inject mask to expression on other side of this node
            oldI = outObj.dependsOn[0]
            newI, maskToApply = self._injectVldMaskToExpr(outObj.dependsOn[0])
            if newI is not oldI:
                builder.replaceInputDriver(outObj._inputs[0], newI)
            # return original out because we did not modify the node itself
        else:
            maskToApply = None

        if maskToApply is not None and out._dtype.bit_length() == 1:
            return builder.buildAnd(out, maskToApply), None
        else:
            return out, maskToApply
        
    def _injectVldMaskToSkipWhenConditions(self):
        """
        We need to assert that the skipWhen condition is never in invalid state.
        Because it drives if the channel is used during synchronization.
        To assert this we need to and each value with a validity flag for each source of value.
        To have expression as simple as possible we add this "and" to top most 1b signal generated from the input.
        (There must be some because the original condition is 1b wide.)
        """
        for n in self.netlist.iterAllNodes():
            if isinstance(n, HlsNetNodeExplicitSync):
                n: HlsNetNodeExplicitSync
                if n.skipWhen is not None:
                    o = n.dependsOn[n.skipWhen.in_i]
                    _o, maskToApply = self._injectVldMaskToExpr(o)
                    assert maskToApply is None, "Should be already applied, because this should be 1b signal"
                    if o is not _o:
                        self.builder.replaceInputDriver(n.skipWhen, _o)

    def connectOrderingPorts(self,
                             mf: MachineFunction):
        """
        finalize ordering connections after all IO is instantiated
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
        raise NotImplementedError("This class does not have run() method because it is"
                                  " a special case customized for each build in Platform class."
                                  "Use object netlist translation methods directly.")
