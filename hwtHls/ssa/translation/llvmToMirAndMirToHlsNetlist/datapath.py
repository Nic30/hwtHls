from typing import Set, Tuple, Dict, List

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT, SLICE, INT
from hwt.pyUtils.arrayQuery import grouper
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, MachineInstr, MachineOperand, CmpInst, TargetOpcode
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HOrderingVoidT, HlsNetNodeRead, \
    HlsNetNodeWrite, HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutLazy, link_hls_nodes, \
    HlsNetNodeOutAny
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.opCache import MirToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer, \
    LiveInMuxMeta


BlockLiveInMuxSyncDict = Dict[Tuple[MachineBasicBlock, MachineBasicBlock, Register], HlsNetNodeExplicitSync]

class HlsNetlistAnalysisPassMirToNetlistDatapath(HlsNetlistAnalysisPassMirToNetlistLowLevel):
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
                    self._addSkipWhen_n(n, cond, mbSync.blockEn)
                    mbSync.addOrderedNode(n)
                    self.inputs.append(n)
                    valCache.add(mb, dst, n._outputs[0], True)

                elif opc == TargetOpcode.GENFPGA_CSTORE:
                    srcVal, dstIo, cond = ops
                    assert isinstance(dstIo, Interface), dstIo
                    n = HlsNetNodeWrite(netlist, NOT_SPECIFIED, dstIo)
                    link_hls_nodes(srcVal, n._inputs[0])
                    self._addExtraCond(n, cond, mbSync.blockEn)
                    self._addSkipWhen_n(n, cond, mbSync.blockEn)
                    mbSync.addOrderedNode(n)
                    self.outputs.append(n)

                elif opc == TargetOpcode.G_ICMP:
                    predicate, lhs, rhs = ops
                    opDef = self.CMP_PREDICATE_TO_OP[predicate]
                    signed = predicate in self.SIGNED_CMP_OPS
                    if signed:
                        lhs = self._castSign(netlist, lhs, True)
                        rhs = self._castSign(netlist, rhs, True)

                    n = HlsNetNodeOperator(netlist, opDef, 2, BIT)
                    self.nodes.append(n)
                    for i, arg in zip(n._inputs, (lhs, rhs)):
                        link_hls_nodes(arg, i)
                    res = n._outputs[0]
                    if signed:
                        res = self._castSign(netlist, res, None)
                        
                    valCache.add(mb, dst, res, True)

                elif opc == TargetOpcode.G_BR or opc == TargetOpcode.G_BRCOND:
                    pass  # will be translated in next step when control is generated, (condition was already translated)
                    
                elif opc == TargetOpcode.GENFPGA_EXTRACT:
                    src, offset, width = ops
                    if isinstance(offset, int):
                        n = HlsNetNodeOperator(netlist, AllOps.INDEX, 2, Bits(width))
                        self.nodes.append(n)
                        if width == 1:
                            # to prefer more simple notation
                            index = INT.from_py(offset)
                        else:
                            index = SLICE.from_py(slice(offset + width, offset, -1))
                        i = HlsNetNodeConst(self.netlist, index)
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
                    cur = builder.buildConcatVariadic(ops[:half])
                    valCache.add(mb, dst, cur, True)

                elif opc == TargetOpcode.PseudoRET:
                    pass
                else:
                    raise NotImplementedError(instr)

    def _constructLiveInMuxes(self, mf: MachineFunction,
                              backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                              liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]]) -> BlockLiveInMuxSyncDict:
        """
        For each block for each live in register create a MUX which will select value of register for this block.
        (Or just propagate value from predecessor if there is just a single one)
        """
        valCache: MirToHwtHlsNetlistOpCache = self.valCache
        netlist: HlsNetlistCtx = self.netlist
        blockLiveInMuxInputSync: BlockLiveInMuxSyncDict = {}
        for mb in mf:
            mb: MachineBasicBlock
            # Construct block input MUXes.
            # the liveIns are not required to be same because in some cases
            # the libeIn is used only by MUX input for a specific predecessor
            # First we collect all inputs for all variant then we build MUX.
            
            # Mark all inputs from predec as not required and stalled while we do not have sync token ready.
            # Mark all inputs from reenter as not required and stalled while we have a sync token ready.

            loop = self.loops.getLoopFor(mb)
            liveInOrdered = []  # list of liveIn variables so we process them in deterministic order
            # liveIn -> List[Tuple[value, condition]]
            liveIns: Dict[Register, List[LiveInMuxMeta]] = {}
            for pred in mb.predecessors():
                pred: MachineBasicBlock
                isBackedge = (pred, mb) in backedges

                for liveIn in liveness[pred][mb]:
                    liveIn: Register
                    if liveIn in self.regToIo:
                        continue  # we will use interface not the value of address where it is mapped

                    meta = liveIns.get(liveIn, None)
                    if meta is None:
                        # we step upon a new liveIn variable, we create a list for its values
                        liveInOrdered.append(liveIn)
                        meta = liveIns[liveIn] = LiveInMuxMeta()

                    meta: LiveInMuxMeta
                    dtype = Bits(self.registerTypes[liveIn])
                    v = valCache.get(pred, liveIn, dtype)
                    if isBackedge:
                        v = self._constructBackedgeBuffer(f"r_{liveIn.virtRegIndex():d}", pred, mb, (pred, liveIn), v)
                    c = valCache.get(mb, pred, BIT)
                    if loop:
                        es = HlsNetNodeExplicitSync(netlist, dtype)
                        blockLiveInMuxInputSync[(pred, mb, liveIn)] = es
                        self.nodes.append(es)
                        link_hls_nodes(v, es._inputs[0])
                        v = es._outputs[0]

                    meta.values.append((v, c))

            predCnt = mb.pred_size()
            for liveIn in liveInOrdered:
                liveIn: Register
                cases = liveIns[liveIn].values
                assert cases, ("MUX for liveIn has to have some cases (even if it is undef)", liveIn)
                if predCnt == 1:
                    assert len(cases) == 1
                    v, _ = cases[0]
                else:
                    dtype = Bits(self.registerTypes[liveIn])
                    mux = HlsNetNodeMux(netlist, dtype)
                    self.nodes.append(mux)

                    for last, (src, cond) in iter_with_last(cases):
                        mux._add_input_and_link(src)
                        if not last:
                            # last case must be always satisfied because the block must have been entered somehow
                            mux._add_input_and_link(cond)

                    v = mux._outputs[0]

                valCache.add(mb, liveIn, v, False)
        return blockLiveInMuxInputSync

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
    
