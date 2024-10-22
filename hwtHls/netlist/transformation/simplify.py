from typing import Optional

from hwt.hdl.operatorDefs import HwtOps, COMPARE_OPS, CAST_OPS
from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchElementTermPropagationCtx, \
    ArchSyncNodeTerm
from hwtHls.netlist.analysis.consistencyCheck import HlsNetlistPassConsistencyCheck
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortOut, \
    HlsNetNodeAggregate
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.fsmStateEn import HlsNetNodeStageAck
from hwtHls.netlist.nodes.fsmStateWrite import HlsNetNodeFsmStateWrite
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifyExpr.cmp import netlistReduceEqNe, \
    netlistReduceCmpConstAfterConstAddSub
from hwtHls.netlist.transformation.simplifyExpr.cmpNormalize import netlistCmpNormalize, _DENORMALIZED_CMP_OPS
from hwtHls.netlist.transformation.simplifyExpr.concat import netlistReduceConcatOfVoid, \
    netlistReduceConcat
from hwtHls.netlist.transformation.simplifyExpr.loops import netlistReduceLoopWithoutEnterAndExit
from hwtHls.netlist.transformation.simplifyExpr.normalizeConstToRhs import netlistNormalizeConstToRhs, \
    BINARY_OPS_WITH_SWAPABLE_OPERANDS
from hwtHls.netlist.transformation.simplifyExpr.rehash import HlsNetlistPassRehashDeduplicate
from hwtHls.netlist.transformation.simplifyExpr.simplifyAbc import runAbcControlpathOpt
from hwtHls.netlist.transformation.simplifyExpr.simplifyBitwise import netlistReduceNot, netlistReduceAndOrXor
from hwtHls.netlist.transformation.simplifyExpr.simplifyIndex import netlistReduceIndexOnIndex
from hwtHls.netlist.transformation.simplifyExpr.simplifyIndexOnConcat import netlistReduceIndexOnConcat
from hwtHls.netlist.transformation.simplifyExpr.simplifyIndexOnMuxOfConcats import netlistReduceIndexOnMuxOfConcats
from hwtHls.netlist.transformation.simplifyExpr.simplifyIo import netlistReduceReadReadSyncWithReadOfValidNB
from hwtHls.netlist.transformation.simplifyExpr.simplifyLlvmIrExpr import runLlvmCmpOpt, \
    runLlvmMuxCondOpt
from hwtHls.netlist.transformation.simplifyExpr.simplifyMul import netlistReduceMulConst
from hwtHls.netlist.transformation.simplifyExpr.simplifyMux import netlistReduceMux
from hwtHls.netlist.transformation.simplifyExpr.validAndOrXorEqValidNb import netlistReduceValidAndOrXorEqValidNb
from hwtHls.netlist.transformation.simplifySync.readOfRawValueToDataAndVld import netlistReadOfRawValueToDataAndVld
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncFlags
from hwtHls.netlist.transformation.simplifySync.simplifySync import HlsNetlistPassSimplifySync
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import disconnectAllInputs, \
    replaceOperatorNodeWith, iterAllHierachies
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


# from hwtHls.netlist.transformation.simplifyExpr.cmpInAnd import netlistReduceCmpInAnd
# https://fitzgeraldnick.com/2020/01/13/synthesizing-loop-free-programs.html
class HlsNetlistPassSimplify(HlsNetlistPass):
    """
    HlsNetlist simplification pass

    :var REST_OF_EVALUABLE_OPS: set of operators which can evaluated and are not a specific case
    :var NON_REMOVABLE_CLS: tuple of node classes which can not be removed by dead code removal
    """
    REST_OF_EVALUABLE_OPS = {HwtOps.CONCAT, HwtOps.ADD, HwtOps.SUB, HwtOps.UDIV, HwtOps.SDIV,
                             HwtOps.MUL, HwtOps.INDEX, *COMPARE_OPS, *CAST_OPS}
    OPS_AND_OR_XOR = (HwtOps.AND, HwtOps.OR, HwtOps.XOR)
    NON_REMOVABLE_CLS = (HlsNetNodeLoopStatus, HlsNetNodeExplicitSync, HlsNetNodeStageAck, HlsNetNodeFsmStateWrite)
    OPT_ITERATION_LIMIT = 20

    def __init__(self, dbgTracer: DebugTracer):
        super(HlsNetlistPassSimplify, self).__init__()
        self._dbgTracer = dbgTracer

    def _DCE(self, n: HlsNetNode, worklist: SetList[HlsNetNode], termPropagationCtx: Optional[ArchElementTermPropagationCtx]):
        assert not n._isMarkedRemoved, n
        if not self._isTriviallyDead(n):
            return False

        builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()

        if isinstance(n, HlsNetNodeAggregatePortOut):
            if termPropagationCtx is not None:
                k = ArchSyncNodeTerm((n.parent, n.scheduledZero // n.netlist.normalizedClkPeriod), n.dependsOn[0], None)
                termPropagationCtx.exportedPorts.pop(k, None)
            builder.unregisterNode(n)
            disconnectAllInputs(n, worklist)
            n.markAsRemoved()
            n.parentOut.obj._removeOutput(n.parentOut.out_i)
            return True
        elif isinstance(n, HlsNetNodeReadSync):
            p = n.dependsOn[0].obj
            if isinstance(p, HlsNetNodeExplicitSync):
                cur = p._associatedReadSync
                if cur is n:
                    p._associatedReadSync = None
        # elif isinstance(n, HlsLoopGateStatus):
        #    loop = n._loopGate
        #    disconnectAllInputs(loop, worklist)
        #    removed.add(loop)
        #    builder.unregisterNode(loop)

        builder.unregisterNode(n)
        disconnectAllInputs(n, worklist)
        n.markAsRemoved()
        return True

    @classmethod
    def _isTriviallyDead(cls, n: HlsNetNode):
        if isinstance(n, cls.NON_REMOVABLE_CLS):
            return False
        elif isinstance(n, HlsNetNodeAggregate):
            return not n.subNodes and not n._outputs
        else:
            if not isinstance(n, HlsNetNode):
                raise AssertionError(n)

            for uses in n.usedBy:
                if uses:
                    return False

            if isinstance(n, HlsNetNodeAggregatePortOut):
                return not n.parentOut.obj.usedBy[n.parentOut.out_i]

            return True

    @classmethod
    def _simplifyHlsNetNodeOperator(cls, n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
        o = n.operator
        if isinstance(n, HlsNetNodeMux):
            if netlistReduceMux(n, worklist):
                return True

        elif o == HwtOps.NOT:
            if netlistReduceNot(n, worklist):
                return True

        elif o in BINARY_OPS_WITH_SWAPABLE_OPERANDS and netlistNormalizeConstToRhs(n, worklist):
            return True

        elif o in cls.OPS_AND_OR_XOR:
            if netlistReduceAndOrXor(n, worklist):
                return True

            elif n._outputs[0]._dtype.bit_length() == 1:
                # if runCntr % 2 == 0 and o == HwtOps.AND and netlistReduceCmpInAnd(n, worklist, removed):
                #    # :attention: there is an issue in structure in expression generated by ABC and from this function
                #    # that is why it is required to choose one to generate final result
                #    # otherwise ABC and this function will endlessly rewrite expressions to a different form
                #    didModifyExpr = True
                #    continue

                # el
                if netlistReduceValidAndOrXorEqValidNb(n, worklist):
                    return True

        if o in cls.REST_OF_EVALUABLE_OPS:
            resT: HdlType = n._outputs[0]._dtype
            if o == HwtOps.CONCAT:
                if HdlType_isVoid(resT) and netlistReduceConcatOfVoid(n, worklist):
                    return False
                if netlistReduceConcat(n, worklist):
                    return True

                return False

            c0 = getConstDriverOf(n._inputs[0])
            if c0 is None:
                if o is HwtOps.EQ:
                    if resT.bit_length() == 1 and netlistReduceValidAndOrXorEqValidNb(n, worklist):
                        return True

                if o in _DENORMALIZED_CMP_OPS and netlistCmpNormalize(n, worklist):
                    return True

                if o in (HwtOps.EQ, HwtOps.NE):
                    if netlistReduceEqNe(n, worklist):
                        return True

                    elif netlistReduceCmpConstAfterConstAddSub(n, worklist):
                        return True
                elif o is HwtOps.INDEX:
                    if netlistReduceIndexOnIndex(n, worklist):
                        return True
                    elif netlistReduceIndexOnConcat(n, worklist):
                        return True
                    elif netlistReduceIndexOnMuxOfConcats(n, worklist):
                        return True
                elif o is HwtOps.MUL:
                    if netlistReduceMulConst(n, worklist):
                        return True

                return False

            if len(n._inputs) == 1:
                # operand with a single const input
                v = o._evalFn(c0)
            else:
                c1 = getConstDriverOf(n._inputs[1])
                if c1 is None:
                    # other is not const
                    if o in (HwtOps.EQ, HwtOps.NE):
                        if netlistReduceEqNe(n, worklist):
                            return True

                    return False

                v = o._evalFn(c0, c1)

            if v._dtype != resT:
                assert resT.signed is None, (n, resT)
                assert v._dtype.bit_length() == resT.bit_length(), (v, v._dtype, resT)
                v = v.cast_sign(None)

            replaceOperatorNodeWith(n, n.getHlsNetlistBuilder().buildConst(v), worklist)
            return True

        return  False

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        worklist: SetList[HlsNetNode] = SetList(netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER))
        dbgTracer = self._dbgTracer
        dbgEn = dbgTracer._out is not None
        runCntr = 0
        while True:
            # [todo] it would be more beneficial to use worklist as FIFO because we want to first run DCE and more complex reductions later
            didModifyExpr = False  # flag which is True if we modified some expression and the ABC should be run
            while worklist:
                n: HlsNetNode = worklist.pop()
                if n._isMarkedRemoved or self._DCE(n, worklist, None):
                    continue

                if isinstance(n, HlsNetNodeOperator):
                    if self._simplifyHlsNetNodeOperator(n, worklist):
                        didModifyExpr = True
                        continue

                elif isinstance(n, HlsNetNodeExplicitSync):
                    n: HlsNetNodeExplicitSync
                    netlistReduceExplicitSyncFlags(dbgTracer, n, worklist)
                    if n._isMarkedRemoved:
                        didModifyExpr = True
                        continue
                    if isinstance(n, HlsNetNodeRead):
                        if netlistReduceReadReadSyncWithReadOfValidNB(n, worklist):
                            didModifyExpr = True
                            if dbgEn:
                                HlsNetlistPassConsistencyCheck._checkCycleFree(n.netlist)
                            continue
                        elif n._rawValue is not None and netlistReadOfRawValueToDataAndVld(n, worklist):
                            didModifyExpr = True
                            if dbgEn:
                                HlsNetlistPassConsistencyCheck._checkCycleFree(n.netlist)
                            continue
                elif isinstance(n, HlsNetNodeLoopStatus):
                    if netlistReduceLoopWithoutEnterAndExit(dbgTracer, n, worklist):
                        didModifyExpr = True
                        continue
                assert not isinstance(n, HlsNetNodeReadSync), (n, "Should already be removed")

            if runCntr == 0 or didModifyExpr:
                if dbgEn:
                    HlsNetlistPassConsistencyCheck._checkCycleFree(n.netlist)

                for parent in iterAllHierachies(netlist):
                    runAbcControlpathOpt(parent.builder, worklist, parent.subNodes)
                    if dbgEn:
                        HlsNetlistPassConsistencyCheck._checkCycleFree(n.netlist)
                    if dbgEn:
                        HlsNetlistPassConsistencyCheck._checkCycleFree(n.netlist)

                    runLlvmCmpOpt(parent.builder, worklist, parent.subNodes)
                    runLlvmMuxCondOpt(parent.builder, worklist, parent.subNodes)

            if dbgEn:
                HlsNetlistPassConsistencyCheck._checkConnections(netlist)

            if not worklist:
                HlsNetlistPassSimplifySync(dbgTracer).runOnHlsNetlist(netlist, parentWorklist=worklist)
                dbgTracer.log("rehash")
                HlsNetlistPassRehashDeduplicate().runOnHlsNetlist(netlist, worklist=worklist)
                if not worklist:
                    HlsNetlistPassSimplifySync(dbgTracer).runOnHlsNetlist(netlist, parentWorklist=worklist)
                    if dbgEn:
                        HlsNetlistPassConsistencyCheck._checkCycleFree(n.netlist)
                        HlsNetlistPassConsistencyCheck._checkConnections(netlist)

                    if not worklist:
                        break

            runCntr += 1
            if runCntr > self.OPT_ITERATION_LIMIT:
                while worklist:
                    n = worklist.pop()
                    if n._isMarkedRemoved or self._DCE(n, worklist, None):
                        continue
                dbgTracer.log(("giving up after ", runCntr, " rounds"))
                break

        if netlist.filterNodesUsingRemovedSet(recursive=True):
            if dbgEn:
                HlsNetlistPassConsistencyCheck().runOnHlsNetlist(netlist)

        return PreservedAnalysisSet.preserveReachablity()

