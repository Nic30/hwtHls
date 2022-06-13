from itertools import chain
from typing import Set, Tuple, Dict, List, Union, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT, SLICE
from hwt.pyUtils.arrayQuery import grouper
from hwt.synthesizer.interface import Interface
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, MachineOperand, Register, \
    MachineInstr, TargetOpcode, CmpInst, MachineLoop
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HOrderingVoidT, HlsNetNodeRead, \
    HlsNetNodeWrite, HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutLazy, \
    link_hls_nodes, unlink_hls_nodes, HlsNetNodeOutAny, HlsNetNodeIn, HlsNetNodeOutLazyIndirect, \
    HlsNetNodeOut
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.utils import hls_op_and, hls_op_or_variadic, hls_op_not, \
    hls_op_and_variadic
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.mirToNetlistLowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.opCache import MirToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer


class HlsNetlistAnalysisPassMirToNetlist(HlsNetlistAnalysisPassMirToNetlistLowLevel):
    """
    This object translates LLVM MIR to hwtHls HlsNetlist
    """

    def _translateDatapathInBlocks(self, mf: MachineFunction):
        """
        Translate all non control instructions which are entirely in some block.
        (Excluding connections between blocks)
        """
        valCache: MirToHwtHlsNetlistOpCache = self.valCache 
        netlist: HlsNetlistCtx = self.netlist
        for mb in mf:
            mb: MachineBasicBlock
            mbSync = MachineBasicBlockSyncContainer(
                mb,
                HlsNetNodeOutLazy(netlist, [], valCache, BIT),
                HlsNetNodeOutLazy(netlist, [], valCache, HOrderingVoidT))

            self.blockSync[mb] = mbSync
            for instr in mb:
                instr: MachineInstr
                dst = None
                ops = []
                for mo in instr.operands():
                    mo: MachineOperand
                    if mo.isReg():
                        if mo.isDef():
                            assert dst is None, (dst, instr)
                            dst = mo.getReg()
                        else:
                            ops.append(self._translateRegister(mb, mo.getReg()))

                    elif mo.isMBB():
                        ops.append(self._translateMBB(mo.getMBB()))
                    elif mo.isImm():
                        ops.append(mo.getImm())
                    elif mo.isCImm():
                        ops.append(self._translateConstant(mo.getCImm()))
                    elif mo.isPredicate():
                        ops.append(CmpInst.Predicate(mo.getPredicate()))
                    else:
                        raise NotImplementedError(instr, mo)

                opc = instr.getOpcode()
                opDef = self.OPC_TO_OP.get(opc, None)
                if opDef is not None:
                    resT = ops[0]._dtype
                    n = HlsNetNodeOperator(netlist, opDef, len(ops), resT)
                    self.nodes.append(n)
                    for i, arg in zip(n._inputs, ops):
                        # a = self.to_hls_expr(arg)
                        link_hls_nodes(arg, i)
                    valCache.add(mb, dst, n._outputs[0], True)
                    continue

                elif opc == TargetOpcode.GENFPGA_MUX:
                    resT = ops[0]._dtype
                    argCnt = len(ops)
                    if argCnt == 1:
                        valCache.add(mb, dst, ops[0], True)

                    else:
                        mux = HlsNetNodeMux(self.netlist, resT)
                        self.nodes.append(mux)
                        if argCnt % 2 != 1:
                            # add current value as a default option in MUX
                            ops.append(self._translateRegister(mb, dst))

                        for (src, cond) in grouper(2, ops):
                            mux._add_input_and_link(src)
                            if cond is not None:
                                mux._add_input_and_link(cond)
                            
                        valCache.add(mb, dst, mux._outputs[0], True)

                elif opc == TargetOpcode.GENFPGA_CLOAD:
                    src, cond = ops
                    assert isinstance(src, Interface), src
                    n = HlsNetNodeRead(netlist, src)
                    self._addExtraCond(n, cond, mbSync.blockEn)
                    mbSync.addOrderedNode(n)
                    self.inputs.append(n)
                    valCache.add(mb, dst, n._outputs[0], True)

                elif opc == TargetOpcode.GENFPGA_CSTORE:
                    srcVal, dstIo, cond = ops
                    assert isinstance(dstIo, Interface), dstIo
                    n = HlsNetNodeWrite(netlist, srcVal, dstIo)
                    self._addExtraCond(n, cond, mbSync.blockEn)
                    mbSync.addOrderedNode(n)
                    self.outputs.append(n)

                elif opc == TargetOpcode.G_ICMP:
                    predicate, lhs, rhs = ops
                    opDef = self.CMP_PREDICATE_TO_OP[predicate]
                    if predicate in self.SIGNED_CMP_OPS:
                        raise NotImplementedError()
                    n = HlsNetNodeOperator(netlist, opDef, 2, BIT)
                    self.nodes.append(n)
                    for i, arg in zip(n._inputs, (lhs, rhs)):
                        link_hls_nodes(arg, i)
                    valCache.add(mb, dst, n._outputs[0], True)

                elif opc == TargetOpcode.G_BR or opc == TargetOpcode.G_BRCOND:
                    pass  # will be translated in next step when control is generated, (condition was already translated)
                    
                elif opc == TargetOpcode.GENFPGA_EXTRACT:
                    src, offset, width = ops
                    if isinstance(offset, int):
                        n = HlsNetNodeOperator(netlist, AllOps.INDEX, 2, Bits(width))
                        self.nodes.append(n)
                        i = HlsNetNodeConst(self.netlist, SLICE.from_py(slice(offset + width, offset, -1)))
                        self.nodes.append(i)
                    else:
                        raise NotImplementedError()

                    link_hls_nodes(src, n._inputs[0])
                    link_hls_nodes(i._outputs[0], n._inputs[1])

                    valCache.add(mb, dst, n._outputs[0], True)

                elif opc == TargetOpcode.GENFPGA_MERGE_VALUES:
                    # src{N}, width{N}
                    assert len(ops) % 2 == 0, ops
                    half = len(ops) // 2
                    
                    cur: HlsNetNodeOutAny = ops[0]
                    curWidth: int = ops[half]
                    for o, w in zip(ops[1:half], ops[half + 1:]):
                        n = HlsNetNodeOperator(netlist, AllOps.CONCAT, 2, Bits(curWidth + w))
                        self.nodes.append(n)
                        for i, arg in zip(n._inputs, (cur, o)):
                            link_hls_nodes(arg, i)
                        cur = n._outputs[0]
                        curWidth += w

                    valCache.add(mb, dst, cur, True)
                elif opc == TargetOpcode.PseudoRET:
                    pass
                else:
                    raise NotImplementedError(instr)

    def _constructLiveInMuxes(self, mf: MachineFunction,
                              backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                              liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]]):
        """
        For each block for each live in register create a MUX which will select value of register for this block.
        (Or just propagate value from predecessor if there is just a single one)
        """
        valCache: MirToHwtHlsNetlistOpCache = self.valCache 
        for mb in mf:
            mb: MachineBasicBlock
            # Construct block input MUXes.
            # the liveIns are not required to be same because in some cases
            # the libeIn is used only by MUX input for a specific predecessor
            # First we collect all inputs for all variant then we build MUX.
            liveInOrdered = []  # list of liveIn variables so we process them in deterministic order
            # liveIn -> List[Tuple[value, condition]]
            liveIns: Dict[Register, List[Tuple[HlsNetNodeOutAny, HlsNetNodeOutAny]]] = {}
            for pred in mb.predecessors():
                pred: MachineBasicBlock
                isBackedge = (pred, mb) in backedges

                for liveIn in liveness[pred][mb]:
                    liveIn: Register
                    if liveIn in self.regToIo:
                        continue  # we will use interface not the value of address where it is mapped

                    caseList = liveIns.get(liveIn, None)
                    if caseList is None:
                        # we step upon a new liveIn variable, we create a list for its values
                        liveInOrdered.append(liveIn)
                        caseList = liveIns[liveIn] = []

                    caseList: List[Tuple[HlsNetNodeOutAny, HlsNetNodeOutAny]]
                    dtype = Bits(self.registerTypes[liveIn])
                    v = valCache.get(pred, liveIn, dtype)
                    if isBackedge:
                        v = self._constructBackedgeBuffer(f"r_{liveIn.virtRegIndex():d}", pred, mb, (pred, liveIn), v)
                    c = valCache.get(mb, pred, BIT)
                    caseList.append((v, c))

            predCnt = mb.pred_size()
            for liveIn in liveInOrdered:
                liveIn: Register
                cases = liveIns[liveIn]
                assert cases, ("MUX for liveIn has to have some cases (even if it is undef)", liveIn)
                if predCnt == 1:
                    assert len(cases) == 1
                    v, _ = cases[0]
                else:
                    dtype = Bits(self.registerTypes[liveIn])
                    mux = HlsNetNodeMux(self.netlist, dtype)
                    self.nodes.append(mux)

                    for last, (src, cond) in iter_with_last(cases):
                        mux._add_input_and_link(src)
                        if not last:
                            # last case must be always satisfied because the block must have been entered somehow
                            mux._add_input_and_link(cond)
                        
                    v = mux._outputs[0]

                valCache.add(mb, liveIn, v, False)

    def _updateThreadsOnPhiMuxes(self, threads: HlsNetlistAnalysisPassDataThreads):
        """
        After we instantiated MUXes for liveIns we need to update threads as the are merged now.
        """
        liveness = self.liveness
        for mb in self.mf:
            mb: MachineBasicBlock
            for pred in mb.predecessors():
                pred: MachineBasicBlock

                for liveIn in liveness[pred][mb]:
                    liveIn: Register
                    if liveIn in self.regToIo:
                        continue  # we will use interface not the value of address where it is mapped

                    dtype = Bits(self.registerTypes[liveIn])
                    srcThread = self._getThreadOfReg(threads, pred, liveIn, dtype)
                    dstThread = self._getThreadOfReg(threads, mb, liveIn, dtype)
                    threads.mergeThreads(srcThread, dstThread)
    
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
        while True:
            p = topLoop.getParentLoop()
            if p is None:
                break
            else:
                topLoop = p
        
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
            
        if resetPredEn is None:
            dependentOnControlInput = otherPredEn.dependent_inputs
        elif otherPredEn is None:
            dependentOnControlInput = resetPredEn.dependent_inputs
        else:
            dependentOnControlInput = chain(resetPredEn.dependent_inputs, otherPredEn.dependent_inputs)
        
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
                raise AssertionError("Can not recognize reset value in mux in loop header")

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
            assert isinstance(rstValObj, HlsNetNodeConst), (
                "must be const otherwise it is impossible to extract this as reset",
                rstValObj)
            # add reset value to backedge buffer init
            init = backedgeBuffRead.associated_write.channel_init_values
            if init:
                raise NotImplementedError("Merge init values")
            else:
                backedgeBuffRead.associated_write.channel_init_values = ((rstValObj.val,),)

            # pop mux inputs for reset
            unlink_hls_nodes(vRst, vRstI)
            mux._removeInput(vRstI.in_i)  # remove reset input which was moved to backedge buffer init
            unlink_hls_nodes(cond, condI)
            mux._removeInput(condI.in_i)  # remove condition because we are not using it
            alreadyUpdated.add(mux)

    def _extractRstValues(self, mf: MachineFunction, threads: HlsNetlistAnalysisPassDataThreads):
        for mb in mf:
            mb: MachineBasicBlock
            # extract rst values
            mbSync: MachineBasicBlockSyncContainer = self.blockSync[mb]
            if mbSync.rstPredeccessor:
                self._rewriteControlOfInfLoopWithReset(mb, mbSync.rstPredeccessor)

                dependentInputs = mbSync.blockEn.dependent_inputs
                replaced: Set[HlsNetNodeIn] = set()
                for i in mbSync.blockEn.dependent_inputs:
                    assert isinstance(i.obj, (HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeOperator)), i.obj
                    self._replaceInputWithConst1(i, threads)
                    replaced.add(i)
 
                if len(replaced) != len(dependentInputs):
                    mbSync.blockEn.dependent_inputs = [i for i in dependentInputs if i not in replaced]
                else:
                    mbSync.blockEn.dependent_inputs.clear()

    def _resolveEnFromPredecessors(self, mb: MachineBasicBlock,
                                   mbSync: MachineBasicBlockSyncContainer,
                                   backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]]) -> List[HlsNetNodeOutLazy]:
        """
        :note: we generate enFromPredccs even if the block does not need control because it may still require require enFromPredccs
            for input MUXes
        :returns: list of control en flag from any predecessor
        """
        
        valCache: MirToHwtHlsNetlistOpCache = self.valCache
        netlist = self.netlist
        # construct CFG flags
        enFromPredccs = []
        for pred in mb.predecessors():
            pred: MachineBasicBlock
            
            predEn = None  # condition which specifies if the control is in pred block
            brCond = None  # condition which controls if the control moves to mb block
            if mbSync.needsControl:
                predEn = self.blockSync[pred].blockEn
                # :note: there can be multiple terminators in each block and we have to resolve
                #        brCond from all of them
                for ter in pred.terminators():
                    ter: MachineInstr
                    opc = ter.getOpcode()
                    predEn = self.blockSync[pred].blockEn
                
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
                            c = hls_op_not(netlist, c)

                        if brCond is None:
                            brCond = hls_op_and(netlist, predEn, c)
                        else:
                            brCond = hls_op_not(netlist, brCond)
                            brCond = hls_op_and_variadic(netlist, brCond, predEn, c)

                        if dstBlock == mb:
                            break

                    elif opc == TargetOpcode.PseudoRET:
                        raise AssertionError("This block is not predecessor of mb if it ends with return.", pred, mb)
                    else:
                        raise NotImplementedError("Unknown terminator", ter)
        
            if brCond is None and mbSync.needsControl:
                brCond = predEn
    
            isBackedge = (pred, mb) in backedges
            if (pred, mb) in backedges and mbSync.needsControl:
                # we need to insert backedge buffer to get block en flag from pred to mb
                # [fixme] write order must be asserted because we can not release a control token until all block operations finished
                assert brCond is not None, brCond
                brCond = self._constructBackedgeBuffer("c", pred, mb, pred, brCond)
    
            elif mbSync.needsControl and brCond is not None:
                # brCond is a normal branch signal
                pass
            elif mbSync.needsControl:
                raise NotImplementedError("No control from predecessor but block needs control")
                
            if mbSync.needsControl:
                assert brCond is not None, (mb.getName(), mb.getNumber())
                if not isBackedge:
                    # it is backedge it was already added during _constructBackedgeBuffer()
                    valCache.add(mb, pred, brCond, False)
                enFromPredccs.append(brCond)
            
        return enFromPredccs

    def _resolveBlockEn(self, mf: MachineFunction,
                        backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                        threads: HlsNetlistAnalysisPassDataThreads):
        self._extractRstValues(mf, threads)
        for mb in mf:
            mb: MachineBasicBlock
            # resolve control enable flag for a block
            mbSync: MachineBasicBlockSyncContainer = self.blockSync[mb]
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
                    blockEn = hls_op_or_variadic(self.netlist, *enFromPredccs)
                else:
                    blockEn = None

            assert isinstance(mbSync.blockEn, HlsNetNodeOutLazy), (mbSync.blockEn, "Must not be resolved yet")

            if blockEn is None:
                # replace with '1' because there is nothing but internal presure blocking the block execution
                blockEn = 1

            if isinstance(blockEn, int) and blockEn == 1:
                for i in mbSync.blockEn.dependent_inputs:
                    i: Union[HlsNetNodeIn, HlsNetNodeOutLazyIndirect]
                    if isinstance(i, HlsNetNodeIn):
                        self._replaceInputWithConst1(i, threads)
                    else:
                        raise NotImplementedError(i)
                    
                mbSync.blockEn.dependent_inputs.clear()
                blockEn = None

            if blockEn is None:
                assert not mbSync.blockEn.dependent_inputs, (mb, mbSync.blockEn.dependent_inputs)
            else:
                mbSync.blockEn.replace_driver(blockEn)

            assert mbSync.blockEn.replaced_by is blockEn or not mbSync.blockEn.dependent_inputs, (mbSync.blockEn, blockEn)
            mbSync.blockEn = blockEn

    def _connectOrderingPorts(self,
                              mf: MachineFunction,
                              backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]]):
        # finalize ordering connections after all IO is instantiated
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
                        mbSync.orderingIn.replace_driver(i)
                    else:
                        for depI in mbSync.orderingIn.dependent_inputs:
                            depI: HlsNetNodeIn
                            # create a new input for ordering connection
                            depI2 = depI.obj._add_input()
                            link_hls_nodes(i, depI2)
            

    def run(self):
        raise NotImplementedError("This class does not have run() method because it is"
                                  " a special case customized for each build in Platform class."
                                  "Use object netlist translation methods directly.")
