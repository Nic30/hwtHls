from typing import Tuple, List, Optional, Union, Dict

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.types.defs import BIT
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, \
    MachineInstr, TargetOpcode, Register
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, HlsNetNodeOutLazy, \
    HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.ssa.translation.llvmMirToNetlist.branchOutLabel import BranchOutLabel
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import MachineEdgeMeta, \
    MACHINE_EDGE_TYPE
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.netlist.nodes.portsUtils import HlsNetNodeOutLazy_replace


def _mergeBrachOutConditions(builder: HlsNetlistBuilder,
                             mbEn: Optional[HlsNetNodeOutAny],
                             anyPrevBranchEn: Union[HlsNetNodeOutAny, None, NOT_SPECIFIED],
                             brCond: Optional[HlsNetNodeOutAny],
                             srcBbNumber: int,
                             dstBbNumber: int):
    """
    This function merges condition flags which are used to resolve if the jump should be performed or not.
    
    :param mbEn: enable of the block from which branch jumps
    :param anyPrevBranchEn: any previous branch caused that this branch is not performed
    :param brCond: this branch should be executed
    """
    if anyPrevBranchEn is None or anyPrevBranchEn is NOT_SPECIFIED:
        if brCond is None and mbEn is None:
            _brCond = builder.buildConstBit(1)
        elif brCond is None:
            _brCond = mbEn
        elif mbEn is None:
            _brCond = brCond
        else:
            _brCond = builder.buildAnd(mbEn, brCond)
    else:
        anyPrevBranchEn_n = builder.buildNot(anyPrevBranchEn)
        if brCond is None and mbEn is None:
            _brCond = anyPrevBranchEn_n
        elif brCond is None:
            _brCond = builder.buildAnd(mbEn, anyPrevBranchEn_n)
        elif mbEn is None:
            _brCond = builder.buildAnd(brCond, anyPrevBranchEn_n)
        else:
            _brCond = builder.buildAndVariadic((mbEn, anyPrevBranchEn_n, brCond))

    assert _brCond is not None
    if isinstance(_brCond.obj, HlsNetNodeOperator) and _brCond.obj.name is None:
        _brCond.obj.name = f"bb{srcBbNumber:d}_br_bb{dstBbNumber:d}"
    return _brCond


def _resolveBranchOutLabels(self: "HlsNetlistAnalysisPassMirToNetlist", mb: MachineBasicBlock,
                            mbMeta: MachineBasicBlockMeta,
                            translatedBranchConditions: Dict[Register, HlsNetNodeOutAny]):
    """
    For specified block resolve BranchOutLabel for every exit from this block.
    BranchOutLabel holds the condition under which jump to a specific target is performed.
    """

    valCache = self.valCache
    builder = mbMeta.parentElement.builder
    mbEn = mbMeta.blockEn
    anyPrevBranchEn: Union[HlsNetNodeOutAny, NOT_SPECIFIED, None] = NOT_SPECIFIED
    brCond = None
    for last, ter in iter_with_last(mb.terminators()):
        ter: MachineInstr
        opc = ter.getOpcode()
        if opc == TargetOpcode.HWTFPGA_BR:
            assert last, ("HWTFPGA_BR instruction should be always last in block", mb)
            brCond = None
            dstBlock = ter.getOperand(0).getMBB()

        elif opc == TargetOpcode.HWTFPGA_BRCOND:
            # mb is conditional successor of pred, we need to use end of pred and branch cond to get en fo mb
            c, dstBlock = ter.operands()
            assert c.isReg(), c
            assert dstBlock.isMBB(), dstBlock
            brCond = translatedBranchConditions[c.getReg()]
            if isinstance(brCond, HlsNetNodeOutLazy):
                brCond = brCond.getLatestReplacement()
            dstBlock = dstBlock.getMBB()

        elif opc == TargetOpcode.HWTFPGA_RET:
            assert last, ("return must be last instruction in block", ter)
            return
        else:
            raise NotImplementedError("Unknown terminator", ter)

        _brCond = _mergeBrachOutConditions(builder, mbEn, anyPrevBranchEn, brCond, mb.getNumber(), dstBlock.getNumber())
        valCache.add(mb, BranchOutLabel(dstBlock), _brCond, False)  # the BranchOutLabel is set only once

        if brCond is None:
            anyPrevBranchEn = None  # there must not be any other branch
        elif anyPrevBranchEn is NOT_SPECIFIED:
            anyPrevBranchEn = brCond
        else:
            assert anyPrevBranchEn is not None, "Must not request another branch after HWTFPGA_BR and others"
            anyPrevBranchEn = builder.buildOr(anyPrevBranchEn, brCond)

    fallThroughDstBlock = mb.getFallThrough(False)
    if fallThroughDstBlock is not None:
        brCond = None  # because now it is default jump
        _brCond = _mergeBrachOutConditions(builder, mbEn, anyPrevBranchEn, brCond, mb.getNumber(), fallThroughDstBlock.getNumber())
        # the BranchOutLabel is set only once
        valCache.add(mb, BranchOutLabel(fallThroughDstBlock), _brCond, False)


def _resolveBranchEnFromPredecessor(self: "HlsNetlistAnalysisPassMirToNetlist",
                                    pred: MachineBasicBlock,
                                    mb: MachineBasicBlock,
                                    mbMeta: MachineBasicBlockMeta,
                                    edgeMeta: MachineEdgeMeta)\
        ->Tuple[HlsNetNodeOutAny, HlsNetNodeOutAny, bool]:
    """
    Resolve expression which specifies if CFG jumps to a specified block from specified predecessor.
    :note: sets BranchOutLabel in predecessor.
    :return: fromPredBrCondInMb - HlsNetNodeOut marking that branch was taken to mb block in mb block,
        fromPredBrCondInPred,
    """
    valCache = self.valCache
    dataUsedAsControl = edgeMeta.reuseDataAsControl

    fromPredBrCondInPred = valCache.get(pred, BranchOutLabel(mb), BIT)
    if edgeMeta.etype in (MACHINE_EDGE_TYPE.DISCARDED,
                          MACHINE_EDGE_TYPE.RESET):
        assert (mb, pred) not in valCache
        return None, fromPredBrCondInPred

    curInMb = valCache.get(mb, pred, BIT)
    if not isinstance(curInMb, HlsNetNodeOutLazy):
        return curInMb, fromPredBrCondInPred

    if dataUsedAsControl is None:
        if edgeMeta.etype in (MACHINE_EDGE_TYPE.FORWARD,
                              MACHINE_EDGE_TYPE.BACKWARD):
            # we need to insert backedge buffer to get block en flag from pred to mb
            # [fixme] write order must be asserted because we can not release a control token until all block operations finished

            # add blockEn flag in predecessor to write to the channel for data used to implement control
            assert fromPredBrCondInPred is not None, fromPredBrCondInPred
            fromPredBrCondInMb = edgeMeta.getBufferForReg((pred, mb))
            fromPredBrCondInMb = fromPredBrCondInMb.obj.getValidNB()
            wn: HlsNetNodeWriteBackedge = fromPredBrCondInMb.obj.associatedWrite
            predEn = self.blockMeta[pred].blockEn
            self._addExtraCond(wn, fromPredBrCondInPred, predEn)
            self._addSkipWhen_n(wn, fromPredBrCondInPred, predEn)
            if mbMeta.rstPredeccessor is not None:
                assert not wn.associatedRead.channelInitValues
                # CFG token must be added, because rst predecessor
                # will not physically exist and the circuit does not have way to start
                wn.associatedRead.channelInitValues = (tuple(),)
            # edgeMeta.loopChannelGroupAppendWrite(wn, True)
        else:
            fromPredBrCondInMb = fromPredBrCondInPred

        return fromPredBrCondInMb, fromPredBrCondInPred
    else:
        builder = mbMeta.parentElement.builder
        dRead: HlsNetNodeOut = edgeMeta.getBufferForReg(dataUsedAsControl)
        dRead.obj.setNonBlocking()
        dVld = builder.buildReadSync(dRead)
        if mbMeta.isLoopHeader:
            edge = (pred.getNumber(), mb.getNumber())
            _dRead, fromPredBrCondInMb = mbMeta.loopStatusNode._bbNumberToPorts[edge]
            assert dRead.obj is _dRead, ("Loop port for this predecessor must be this port", edge, dRead.obj, _dRead)
        else:
            fromPredBrCondInMb = dVld

        dWrite: HlsNetNodeWrite = dRead.obj.associatedWrite
        if fromPredBrCondInPred is not None:
            dWrite.addControlSerialExtraCond(fromPredBrCondInPred)
            wBuilder = dWrite.getHlsNetlistBuilder()
            dWrite.addControlSerialSkipWhen(wBuilder.buildNot(fromPredBrCondInPred))

        # should be already a read sync of input channel for dataUsedAsControl
        return fromPredBrCondInMb, fromPredBrCondInPred


def _resolveEnFromPredecessors(self: "HlsNetlistAnalysisPassMirToNetlist", mb: MachineBasicBlock,
                               mbMeta: MachineBasicBlockMeta) -> List[HlsNetNodeOutLazy]:
    """
    :note: enFromPredccs is generated even if the block does not need control because it may still require require enFromPredccs
        for input MUXes
    :return: list of control en flag from any predecessor
    """

    valCache: MirToHwtHlsNetlistValueCache = self.valCache
    builder: HlsNetlistBuilder = mbMeta.parentElement.builder
    # construct CFG flags
    enFromPredccs = []
    for pred in mb.predecessors():
        pred: MachineBasicBlock
        edge = (pred, mb)
        edgeMeta: MachineEdgeMeta = self.edgeMeta[edge]

        if not mbMeta.needsControl or edgeMeta.etype == MACHINE_EDGE_TYPE.RESET or (
                edgeMeta.etype == MACHINE_EDGE_TYPE.DISCARDED and
                not edgeMeta.buffersForLoopExit
            ):
            # skip if control is not required or because all live ins were inlined to backedge buffer initialization
            c1 = builder.buildConstBit(1)
            valCache.add(mb, pred, c1, False)
            continue

        else:
            assert mbMeta.needsControl
            fromPredBrCondInMb, fromPredBrCondInPred = _resolveBranchEnFromPredecessor(self, pred, mb, mbMeta, edgeMeta)

        # dataUsedAsControl = edgeMeta.reuseDataAsControl
        for _, srcVal in edgeMeta.buffers:
            srcValObj: HlsNetNodeReadBackedge = srcVal.obj
            # if dataUsedAsControl is not None and liveIn == dataUsedAsControl:
            #    # avoid synchronizing channel with itself
            #    continue
            w: HlsNetNodeWriteBackedge = srcValObj.associatedWrite
            self._addExtraCond(w, None, fromPredBrCondInPred)
            self._addSkipWhen_n(w, None, fromPredBrCondInPred)

        for rVal in edgeMeta.buffersForLoopExit:
            w: HlsNetNodeWriteBackedge = rVal.obj.associatedWrite
            self._addExtraCond(w, None, fromPredBrCondInPred)
            self._addSkipWhen_n(w, None, fromPredBrCondInPred)

        isLoopHeader = mbMeta.needsControl and mbMeta.isLoopHeader and not mbMeta.isLoopHeaderOfFreeRunning
        if edgeMeta.etype == MACHINE_EDGE_TYPE.DISCARDED:
            c1 = builder.buildConstBit(1)
            if not isLoopHeader:
                valCache.add(mb, pred, c1, False)
        else:
            # fromPredBrCond = valCache.get(pred, brOutLabel, BIT)
            # if mbMeta.needsControl:
            # assert fromPredBrCond is not None, (mb.getName().str(), mb.getNumber())
            # because we need to use latest value not the input value which we just added (r_from_in)
            # if not fromPredBrCondInMbExists:
            if not isLoopHeader:
                valCache.add(mb, pred, fromPredBrCondInMb, False)
            enFromPredccs.append(fromPredBrCondInMb)

    return enFromPredccs


def resolveBlockEn(self: "HlsNetlistAnalysisPassMirToNetlist", mf: MachineFunction,
                   blockMeta: Dict[MachineBasicBlock, MachineBasicBlockMeta]):
    """
    Resolve control flow enable for instructions in the block.
    """
    for mb in mf:
        mb: MachineBasicBlock
        # resolve control enable flag for a block
        mbMeta: MachineBasicBlockMeta = self.blockMeta[mb]
        builder = mbMeta.parentElement.builder
        assert mbMeta.block == mb, ("sanity check", mbMeta.block.getNumber(), mb.getNumber())
        if mbMeta.needsStarter:
            if mbMeta.needsControl:
                assert mb.pred_size() == 0, mb.getNumber()
                # add starter and use it as en
                n = HlsProgramStarter(self.netlist)
                mbMeta.parentElement.addNode(n)
                blockEn = n.getStartEnPort()
            else:
                # no en and extract the constants set there as a reset values
                blockEn = None
        else:
            enFromPredccs = _resolveEnFromPredecessors(self, mb, mbMeta)

            if enFromPredccs and mbMeta.needsControl:
                if None in enFromPredccs:
                    raise AssertionError(enFromPredccs)
                blockEn = builder.buildOrVariadic(enFromPredccs)
            else:
                blockEn = None

        assert isinstance(mbMeta.blockEn, HlsNetNodeOutLazy), (mbMeta.blockEn, "Must not be resolved yet")

        if blockEn is None:
            # replace with '1' because there is nothing but internal presure blocking the block execution
            blockEn = 1

        if isinstance(blockEn, int) and blockEn == 1:
            for i in tuple(mbMeta.blockEn.dependent_inputs):
                i: HlsNetNodeIn
                if isinstance(i, HlsNetNodeIn):
                    i.obj.getHlsNetlistBuilder()._replaceInputDriverWithConst1b(i)
                else:
                    raise NotImplementedError(i)

            mbMeta.blockEn.dependent_inputs.clear()
            blockEn = None

        if blockEn is None:
            assert not mbMeta.blockEn.dependent_inputs, (mb, mbMeta.blockEn.dependent_inputs)
        else:
            HlsNetNodeOutLazy_replace(mbMeta.blockEn, blockEn)

        assert mbMeta.blockEn.replaced_by is blockEn or not mbMeta.blockEn.dependent_inputs, (mbMeta.blockEn, blockEn)
        mbMeta.blockEn = blockEn
        if (blockEn is not None and
                not isinstance(blockEn, HlsNetNodeOutLazy) and
                blockEn.obj.name is None and
                isinstance(blockEn.obj, HlsNetNodeOperator)):
            blockEn.obj.name = f"bb{mb.getNumber():d}_en"
        _resolveBranchOutLabels(self, mb, mbMeta, blockMeta[mb].translatedBranchConditions)
