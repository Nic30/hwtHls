from typing import Optional, Set, Dict

from hwt.synthesizer.interface import Interface
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, \
    MachineInstr, TargetOpcode, MachineLoop, MachineLoopInfo
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, HlsNetNodeOutLazy, \
    HlsNetNodeOut, unlink_hls_nodes, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.ssa.translation.llvmMirToNetlist.opCache import MirToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.llvmMirToNetlist.utils import getTopLoopForBlock, \
    MachineBasicBlockSyncContainer


class ResetValueExtractor():
    """
    Rewrite multiplexor cases for reset to an initialization of channels.
    """

    def __init__(self, builder: HlsNetlistBuilder,
                 valCache: MirToHwtHlsNetlistOpCache,
                 liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                 loops: MachineLoopInfo,
                 blockSync: Dict[MachineBasicBlock, MachineBasicBlockSyncContainer],
                 regToIo: Dict[Register, Interface]):
        self.builder = builder
        self.valCache = valCache
        self.liveness = liveness
        self.loops = loops
        self.blockSync = blockSync
        self.regToIo = regToIo
    
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
        # otherPred: Optional[MachineBasicBlock] = None
        topLoop: MachineLoop = self.loops.getLoopFor(mb)
        assert topLoop, (mb, "must be a loop with a reset otherwise it is not possible to extract the reset")
        topLoop = getTopLoopForBlock(mb, topLoop)
        assert mb.pred_size() == 2, mb
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
                # otherPred = pred

        if resetPredEn is None and otherPredEn is None:
            # case where there are no live variables and thus no reset value extraction is required
            for pred in mb.predecessors():
                for r in self.liveness[pred][mb]:
                    r: Register
                    assert r in self.regToIo, (r, "Block is supposed to have no live in registers because any en from predecessor was not used in input mux")
        else:
                    
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
                    dep = rstValObj.dependsOn[0]
                    assert not isinstance(dep, HlsNetNodeOutLazy), (dep, "This port should lead to some constant which should be already known.", dep.keys_of_self_in_cache)
                    rstValObj = dep.obj
    
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
        
        # :attention: If there is a control channel we must place an initial CFG token into it once it is generated
    def _replaceInputDriverWithConst1b(self, i: HlsNetNodeIn, threads: HlsNetlistAnalysisPassDataThreadsForBlocks):
        c = self.builder._replaceInputDriverWithConst1b(i)
        threads.mergeThreads(threads.threadPerNode[i.obj], {c.obj, })

    def apply(self, mf: MachineFunction, threads: HlsNetlistAnalysisPassDataThreadsForBlocks):
        # b = self.builder
        for mb in mf:
            mb: MachineBasicBlock
            mbSync: MachineBasicBlockSyncContainer = self.blockSync[mb]
            
            if mbSync.rstPredeccessor is not None:
                self._rewriteControlOfInfLoopWithReset(mb, mbSync.rstPredeccessor)
                # if not mbSync.needsControl:
                for i in tuple(mbSync.blockEn.dependent_inputs):
                    i: HlsNetNodeIn
                    assert isinstance(i.obj, (HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeOperator)), i.obj
                    self._replaceInputDriverWithConst1b(i, threads)
