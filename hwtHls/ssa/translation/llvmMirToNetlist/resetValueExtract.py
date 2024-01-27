from typing import Optional, Set, Dict

from hwt.synthesizer.interface import Interface
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, HlsNetNodeOutLazy, \
    HlsNetNodeOut, unlink_hls_nodes, HlsNetNodeIn, \
    unlink_hls_node_input_if_exists
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import MachineEdge, MachineEdgeMeta
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache


class ResetValueExtractor():
    """
    Rewrite multiplexor cases for reset to an initialization of channels.
    """

    def __init__(self, builder: HlsNetlistBuilder,
                 valCache: MirToHwtHlsNetlistValueCache,
                 liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                 blockSync: Dict[MachineBasicBlock, MachineBasicBlockMeta],
                 edgeMeta: Dict[MachineEdge, MachineEdgeMeta],
                 regToIo: Dict[Register, Interface]):
        self.builder = builder
        self.valCache = valCache
        self.liveness = liveness
        self.blockSync = blockSync
        self.edgeMeta = edgeMeta
        self.regToIo = regToIo

    def _rewriteControlOfInfLoopWithReset(self, dbgTracer: DebugTracer, mb: MachineBasicBlock, rstPred: MachineBasicBlock):
        """
        Detect which predecessor is reset and which is continue from loop body.
        Inline MUX values for reset as backedge channel initialization.

        :param mb: header block of this loop
        """
        valCache = self.valCache
        # :note: resetPredEn and otherPredEn do not need to be specified if reset actually does not reset anything
        #        only one can be specified if the value for other in MUXes is always default value which does not have condition
        newResetEdge = self.edgeMeta[(rstPred, mb)].inlineRstDataToEdge
        # assert self.edgeMeta[newResetEdge].etype == MACHINE_EDGE_TYPE.BACKWARD, ("Must be backedge", self.edgeMeta[newResetEdge])
        otherPred, _mb = newResetEdge
        if _mb != mb:
            raise NotImplementedError()

        otherPredEn: Optional[HlsNetNodeOutAny] = valCache._toHlsCache.get((mb, otherPred), None)
        resetPredEn: Optional[HlsNetNodeOutAny] = valCache._toHlsCache.get((mb, rstPred), None)
        newResetEdgeMeta: MachineEdgeMeta = self.edgeMeta[newResetEdge]
        if resetPredEn is None and otherPredEn is None:
            # case where there are no live variables and thus no reset value extraction is required
            for pred in mb.predecessors():
                for r in self.liveness[pred][mb]:
                    r: Register
                    assert r in self.regToIo, (
                        r, "Block is supposed to have no live in registers because any en from predecessor was not used in input mux")
            assert newResetEdgeMeta.reuseDataAsControl is None
            mbSync = self.blockSync[mb]
            if mbSync.needsControl and not mbSync.isLoopHeaderOfFreeRunning:
                rstBuff = newResetEdgeMeta.getBufferForReg(newResetEdge)
                assert HdlType_isVoid(rstBuff.obj._outputs[0]._dtype), (rstBuff, rstBuff.obj._outputs[0]._dtype)
                rstBuffW = rstBuff.obj.associatedWrite
                rstBuffW.channelInitValues = tuple([(), *rstBuffW.channelInitValues])
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

                # assert isinstance(mux, HlsNetNodeMux), mux
                if not isinstance(mux, HlsNetNodeMux):
                    continue
                mux: HlsNetNodeMux
                # pop reset value to initialization of the channel
                backedgeBuffRead: Optional[HlsNetNodeReadBackedge] = None

                v0 = None  # value for otherPredEn which is supposed to be a buffer and where reset value should be inlined
                vRst = None  # value for reset
                vRstI = None  # input for value of reset
                # the mux may contain otherPredEn or resetPredEn or both
                otherPredEnI = None
                resetPredEnI = None
                # mux likely in format  (v0I, v0), (condI, cond), (vRstI, vRst)
                condValuePairs = tuple(mux._iterValueConditionDriverInputPairs())
                for i, ((vDep, vIn), (cDep, cIn)) in enumerate(condValuePairs):
                    if cDep is otherPredEn:
                        otherPredEnI = cIn
                        v0 = vDep
                        if vRst is None:  # check for None because resetPredEn may already have been found
                            vRstI, vRst = condValuePairs[i + 1][0]
                    elif cDep is resetPredEn:
                        resetPredEnI = cIn
                        vRstI = vIn
                        vRst = vDep
                        if v0 is None:  # check for None because otherPredEn may already have been found
                            v0, _ = condValuePairs[i + 1][0]
                assert otherPredEnI is not None or resetPredEnI is not None, (mux, otherPredEn, resetPredEn)
                # assert len(mux.dependsOn) == 3, (mux, "rst", resetPredEn, "nonRst", otherPredEn)
                # (v0I, v0), (condI, cond), (vRstI, vRst) = zip(mux._inputs, mux.dependsOn)
                # if cond is resetPredEn:
                #    # vRst cond v0
                #    (v0, v0I), (vRst, vRstI) = (vRst, vRstI), (v0, v0I)
                # elif cond is otherPredEn:
                #    # v0 cond vRst
                #    pass
                # else:
                #    raise AssertionError("Can not recognize reset value in MUX in loop header")

                # find backedge buffer on value from loop body
                while (isinstance(v0, HlsNetNodeOut) and
                       isinstance(v0.obj, HlsNetNodeExplicitSync) and
                       not isinstance(v0.obj, HlsNetNodeReadBackedge)):
                    v0 = v0.obj.dependsOn[0]

                assert isinstance(v0, HlsNetNodeOut) and isinstance(v0.obj, HlsNetNodeReadBackedge), (mb, v0)
                backedgeBuffRead = v0.obj

                assert backedgeBuffRead is not None
                backedgeBuffRead: HlsNetNodeReadBackedge
                assert not isinstance(vRst, HlsNetNodeOutLazy), (
                    "This transformation should be performed only after all links were resolved and def must be always before use", vRst)
                rstValObj = vRst.obj
                removed = self.builder._removedNodes
                while True:
                    c = rstValObj.__class__
                    if c is HlsNetNodeExplicitSync:
                        dep = rstValObj.dependsOn[0]
                    elif c is HlsNetNodeReadForwardedge:
                        wr = rstValObj.associatedWrite
                        for n in (rstValObj, wr):
                            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, None)
                            unlink_hls_node_input_if_exists(n.skipWhen)
                            unlink_hls_node_input_if_exists(n.extraCond)
                            removed.add(n)

                        removed.add(wr)
                        dep = wr.dependsOn[0]
                        unlink_hls_nodes(dep, wr._inputs[0])
                    else:
                        break

                    assert not isinstance(dep, HlsNetNodeOutLazy), (
                        dep, "This port should lead to some constant which should be already known.", dep.keys_of_self_in_cache)
                    rstValObj = dep.obj

                assert isinstance(rstValObj, HlsNetNodeConst), (
                    "Must be const otherwise it is impossible to extract this as reset",
                    rstValObj, mb)
                # add reset value to backedge buffer init
                init = backedgeBuffRead.associatedWrite.channelInitValues
                if init:
                    raise NotImplementedError("Merge init values")
                else:
                    t = rstValObj.val._dtype
                    assert t == backedgeBuffRead._outputs[0]._dtype, (backedgeBuffRead, t, backedgeBuffRead._outputs[0]._dtype)
                    assert t == mux._outputs[0]._dtype, (mux, t, mux._outputs[0]._dtype)
                    backedgeBuffRead.associatedWrite.channelInitValues = ((rstValObj.val,),)

                # pop mux inputs for reset
                if resetPredEnI is not None:
                    cond = resetPredEn
                    condI = resetPredEnI
                else:
                    assert len(mux._inputs) == 3, mux
                    cond = otherPredEn
                    condI = otherPredEnI

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
        t = threads.threadPerNode[i.obj]
        t.add(c.obj)
        threads.threadPerNode[c.obj] = t

    def apply(self, mf: MachineFunction, threads: HlsNetlistAnalysisPassDataThreadsForBlocks):
        # b = self.builder
        dbgTrace = DebugTracer(None)
        for mb in mf:
            mb: MachineBasicBlock
            mbSync: MachineBasicBlockMeta = self.blockSync[mb]

            if mbSync.rstPredeccessor is not None:
                self._rewriteControlOfInfLoopWithReset(dbgTrace, mb, mbSync.rstPredeccessor)
                # if not mbSync.needsControl:
                # for i in tuple(mbSync.blockEn.dependent_inputs):
                #    i: HlsNetNodeIn
                #    assert isinstance(i.obj, (HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeOperator)), i.obj
                #    self._replaceInputDriverWithConst1b(i, threads)
