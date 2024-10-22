from typing import Optional, Set, Dict

from hwt.hwIO import HwIO
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, HlsNetNodeOutLazy, \
    HlsNetNodeOut, unlink_hls_node_input_if_exists
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import MachineEdge, MachineEdgeMeta
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache


class ResetValueExtractor():
    """
    Rewrite multiplexor cases for reset to an initialization of channels.
    """

    def __init__(self,
                 valCache: MirToHwtHlsNetlistValueCache,
                 liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                 blockMeta: Dict[MachineBasicBlock, MachineBasicBlockMeta],
                 edgeMeta: Dict[MachineEdge, MachineEdgeMeta],
                 regToIo: Dict[Register, HwIO],
                 dbgTracer: DebugTracer):
        self.valCache = valCache
        self.liveness = liveness
        self.blockMeta = blockMeta
        self.edgeMeta = edgeMeta
        self.regToIo = regToIo
        self.dbgTracer = dbgTracer

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
        dbgTracer.log(("Inlining reset behavior in ", mb, " newResetEdge:", newResetEdge,
                       " rst:", rstPred, "rstEn: ", resetPredEn, " other:",
                       otherPred, " otherEn:", otherPredEn))

        mbMeta = self.blockMeta[mb]
        if resetPredEn is None and otherPredEn is None:
            # case where there are no live variables and thus no reset value extraction is required
            for pred in mb.predecessors():
                for r in self.liveness[pred][mb]:
                    r: Register
                    assert r in self.regToIo, (
                        r, "Block is supposed to have no live in registers because any en from predecessor was not used in input mux")
            assert newResetEdgeMeta.reuseDataAsControl is None
            if mbMeta.needsControl and not mbMeta.isLoopHeaderOfFreeRunning:
                dbgTracer.log("appending init value to control channel from rst")
                rstBuff = newResetEdgeMeta.getBufferForReg(newResetEdge)
                assert HdlType_isVoid(rstBuff.obj._portDataOut._dtype), (rstBuff, rstBuff.obj._portDataOut._dtype)
                rstBuffR = rstBuff.obj
                rstBuffR.channelInitValues = tuple([(), *rstBuffR.channelInitValues])
            else:
                dbgTracer.log("Ignoring reset behavior because it has no effect")

        else:
            dbgTracer.log("otherPred and rstPred has en")
            assert resetPredEn is None or isinstance(resetPredEn, HlsNetNodeOutLazy), (resetPredEn, "Must not be resolved yet.")
            assert otherPredEn is None or isinstance(otherPredEn, HlsNetNodeOutLazy), (otherPredEn, "Must not be resolved yet.")

            # must copy because we are updating it
            if resetPredEn is None:
                dependentOnControlInput = tuple(otherPredEn.dependent_inputs)
            elif otherPredEn is None:
                dependentOnControlInput = tuple(resetPredEn.dependent_inputs)
            else:
                dependentOnControlInput = resetPredEn.dependent_inputs + otherPredEn.dependent_inputs

            builder = mbMeta.parentElement.builder
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
                dbgTracer.log(("Rewriting livein mux", mux))

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

                assert isinstance(v0, HlsNetNodeOut) and isinstance(v0.obj, HlsNetNodeReadBackedge), (
                    "Expected channel for livein initialization from reset", mb, v0, )
                backedgeBuffRead = v0.obj

                assert backedgeBuffRead is not None
                backedgeBuffRead: HlsNetNodeReadBackedge
                assert not isinstance(vRst, HlsNetNodeOutLazy), (
                    "This transformation should be performed only after all links were resolved and def must be always before use", vRst)
                rstValObj = vRst.obj
                while True:
                    if isinstance(rstValObj, HlsNetNodeReadForwardedge):
                        wr = rstValObj.associatedWrite
                        for n in (rstValObj, wr):
                            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, None)
                            unlink_hls_node_input_if_exists(n.skipWhen)
                            unlink_hls_node_input_if_exists(n.extraCond)
                            n.markAsRemoved()

                        dep = wr.dependsOn[0]
                        wr._inputs[0].disconnectFromHlsOut(dep)
                    else:
                        break

                    assert not isinstance(dep, HlsNetNodeOutLazy), (
                        dep, "This port should lead to some constant which should be already known.", dep.keys_of_self_in_cache)
                    rstValObj = dep.obj

                assert isinstance(rstValObj, HlsNetNodeConst), (
                    "Must be const otherwise it is impossible to extract this as reset",
                    rstValObj, mb)
                # add reset value to backedge buffer init
                init = backedgeBuffRead.channelInitValues
                if init:
                    raise NotImplementedError("Merge init values")
                else:
                    t = rstValObj.val._dtype
                    assert t == backedgeBuffRead._portDataOut._dtype, (backedgeBuffRead, t, backedgeBuffRead._portDataOut._dtype)
                    assert t == mux._outputs[0]._dtype, (mux, t, mux._outputs[0]._dtype)
                    backedgeBuffRead.channelInitValues = ((rstValObj.val,),)

                # pop mux inputs for reset
                if resetPredEnI is not None:
                    cond = resetPredEn
                    condI = resetPredEnI
                else:
                    assert len(mux._inputs) == 3, mux
                    cond = otherPredEn
                    condI = otherPredEnI

                builder.unregisterOperatorNode(mux)
                vRstI.disconnectFromHlsOut(vRst)
                mux._removeInput(vRstI.in_i)  # remove reset input which was moved to backedge buffer init

                condI.disconnectFromHlsOut(cond)
                mux._removeInput(condI.in_i)  # remove condition because we are not using it

                builder.registerOperatorNode(mux)
                alreadyUpdated.add(mux)

        # :attention: If there is a control channel we must place an initial CFG token into it once it is generated

    def apply(self, mf: MachineFunction):
        for mb in mf:
            mb: MachineBasicBlock
            mbMeta: MachineBasicBlockMeta = self.blockMeta[mb]

            if mbMeta.rstPredeccessor is not None:
                self._rewriteControlOfInfLoopWithReset(self.dbgTracer, mb, mbMeta.rstPredeccessor)

