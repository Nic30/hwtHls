from typing import Set

from hwt.hdl.operatorDefs import AllOps, COMPARE_OPS, CAST_OPS
from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifyExpr.cmp import netlistReduceEqNe
from hwtHls.netlist.transformation.simplifyExpr.cmpInAnd import netlistReduceCmpInAnd
from hwtHls.netlist.transformation.simplifyExpr.cmpNormalize import netlistCmpNormalize, _DENORMALIZED_CMP_OPS
from hwtHls.netlist.transformation.simplifyExpr.concat import netlistReduceConcatOfVoid,\
    netlistReduceConcat
from hwtHls.netlist.transformation.simplifyExpr.loops import netlistReduceLoopWithoutEnterAndExit
from hwtHls.netlist.transformation.simplifyExpr.normalizeConstToRhs import netlistNormalizeConstToRhs, \
    BINARY_OPS_WITH_SWAPABLE_OPERANDS
from hwtHls.netlist.transformation.simplifyExpr.rehash import HlsNetlistPassRehashDeduplicate
from hwtHls.netlist.transformation.simplifyExpr.simplifyAbc import runAbcControlpathOpt
from hwtHls.netlist.transformation.simplifyExpr.simplifyBitwise import netlistReduceNot, netlistReduceAndOrXor
from hwtHls.netlist.transformation.simplifyExpr.simplifyIo import netlistReduceReadReadSyncWithReadOfValidNB
from hwtHls.netlist.transformation.simplifyExpr.simplifyLlvmIrExpr import runLlvmCmpOpt
from hwtHls.netlist.transformation.simplifyExpr.simplifyMux import netlistReduceMux
from hwtHls.netlist.transformation.simplifyExpr.validAndOrXorEqValidNb import netlistReduceValidAndOrXorEqValidNb
from hwtHls.netlist.transformation.simplifySync.readOfRawValueToDataAndVld import netlistReadOfRawValueToDataAndVld
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncFlags
from hwtHls.netlist.transformation.simplifySync.simplifySync import HlsNetlistPassSimplifySync
from hwtHls.netlist.transformation.simplifyUtils import disconnectAllInputs, \
    getConstDriverOf, replaceOperatorNodeWith


# https://fitzgeraldnick.com/2020/01/13/synthesizing-loop-free-programs.html
class HlsNetlistPassSimplify(HlsNetlistPass):
    """
    HlsNetlist simplification pass

    :var REST_OF_EVALUABLE_OPS: set of operators which can evaluated and are not a specific case
    :var NON_REMOVABLE_CLS: tuple of node classes which can not be removed by dead code removal
    """
    REST_OF_EVALUABLE_OPS = {AllOps.CONCAT, AllOps.ADD, AllOps.SUB, AllOps.UDIV, AllOps.SDIV,
                             AllOps.MUL, AllOps.INDEX, *COMPARE_OPS, *CAST_OPS}
    OPS_AND_OR_XOR = (AllOps.AND, AllOps.OR, AllOps.XOR)
    NON_REMOVABLE_CLS = (HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeLoopStatus, HlsNetNodeExplicitSync)
    OPT_ITERATION_LIMIT = 20

    def __init__(self, dbgTracer: DebugTracer):
        super(HlsNetlistPassSimplify, self).__init__()
        self._dbgTracer = dbgTracer

    def _DCE(self, n: HlsNetNode, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
        if not self._isTriviallyDead(n):
            return False

        builder = n.netlist.builder
        if isinstance(n, HlsNetNodeReadSync):
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
        removed.add(n)
        return True

    def apply(self, hls:"HlsScope", netlist: HlsNetlistCtx):
        worklist: UniqList[HlsNetNode] = UniqList(netlist.iterAllNodes())
        removed: Set[HlsNetNode] = netlist.builder._removedNodes
        builder = netlist.builder
        dbgTracer = self._dbgTracer
        dbgEn = dbgTracer._out is not None
        runCntr = 0
        while True:
            # [todo] it would be more beneficial to use worklist as FIFO because we want to first run DCE and more complex reductions later
            didModifyExpr = False  # flag which is True if we modified some expression and the ABC should be run
            while worklist:
                n = worklist.pop()
                if n in removed or self._DCE(n, worklist, removed):
                    continue

                if isinstance(n, HlsNetNodeOperator):
                    n: HlsNetNodeOperator
                    o = n.operator
                    if isinstance(n, HlsNetNodeMux):
                        if netlistReduceMux(n, worklist, removed):
                            didModifyExpr = True
                            continue
                    
                    elif o == AllOps.NOT:
                        if netlistReduceNot(n, worklist, removed):
                            didModifyExpr = True
                            continue
                    
                    elif o in BINARY_OPS_WITH_SWAPABLE_OPERANDS and netlistNormalizeConstToRhs(n, worklist, removed):
                        didModifyExpr = True
                        continue
                    
                    elif o in self.OPS_AND_OR_XOR:
                        if netlistReduceAndOrXor(n, worklist, removed):
                            didModifyExpr = True
                            continue
                        
                        elif n._outputs[0]._dtype.bit_length() == 1:
                            if runCntr % 2 == 0 and o == AllOps.AND and netlistReduceCmpInAnd(n, worklist, removed):
                                # :attention: there is an issue in structure in expression generated by ABC and from this function
                                # that is why it is required to choose one to generate final result
                                # otherwise ABC and this function will endlessly rewrite expressions to a different form
                                didModifyExpr = True
                                continue

                            elif netlistReduceValidAndOrXorEqValidNb(n, worklist, removed):
                                didModifyExpr = True
                                continue
                
                    elif o in self.REST_OF_EVALUABLE_OPS:
                        resT: HdlType = n._outputs[0]._dtype
                        if o == AllOps.CONCAT:
                            if HdlType_isVoid(resT) and netlistReduceConcatOfVoid(n, worklist, removed):
                                continue
                            if netlistReduceConcat(n, worklist, removed):
                                didModifyExpr = True
                                continue
                            continue
                    
                        c0 = getConstDriverOf(n._inputs[0])
                        if c0 is None:
                            if o is AllOps.EQ:
                                if resT.bit_length() == 1 and netlistReduceValidAndOrXorEqValidNb(n, worklist, removed):
                                    didModifyExpr = True
                                    continue
                            
                            if o in _DENORMALIZED_CMP_OPS and netlistCmpNormalize(n, worklist, removed):
                                didModifyExpr = True
                                continue
                            
                            if o in (AllOps.EQ, AllOps.NE):
                                if netlistReduceEqNe(n, worklist, removed):
                                    didModifyExpr = True
                                    continue
                    
                            continue
                    
                        if len(n._inputs) == 1:
                            # operand with a single const input
                            v = o._evalFn(c0)
                        else:
                    
                            c1 = getConstDriverOf(n._inputs[1])
                            if c1 is None:
                                # other is not const
                                if o in (AllOps.EQ, AllOps.NE):
                                    if netlistReduceEqNe(n, worklist, removed):
                                        didModifyExpr = True
                                        continue
                                continue
                    
                            v = o._evalFn(c0, c1)
                    
                        if v._dtype != resT:
                            assert resT.signed is None, (n, resT)
                            assert v._dtype.bit_length() == resT.bit_length(), (v, v._dtype, resT)
                            v = v.cast_sign(None)
                    
                        replaceOperatorNodeWith(n, builder.buildConst(v), worklist, removed)
                        didModifyExpr = True
                        continue
                
                elif isinstance(n, HlsNetNodeExplicitSync):
                    n: HlsNetNodeExplicitSync
                    netlistReduceExplicitSyncFlags(dbgTracer, n, worklist, removed)
                    if n in removed:
                        didModifyExpr = True
                        continue
                    if isinstance(n, HlsNetNodeRead):
                        if netlistReduceReadReadSyncWithReadOfValidNB(n, worklist, removed):
                            didModifyExpr = True
                            if dbgEn:
                                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                            continue
                        elif n._rawValue is not None and netlistReadOfRawValueToDataAndVld(n, worklist, removed):
                            didModifyExpr = True
                            if dbgEn:
                                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                            continue
                elif isinstance(n, HlsNetNodeLoopStatus):
                    if netlistReduceLoopWithoutEnterAndExit(dbgTracer, n, worklist, removed):
                        didModifyExpr = True
                        continue
                assert not isinstance(n, HlsNetNodeReadSync), (n, "Should already be removed")

            if runCntr == 0 or didModifyExpr:
                if dbgEn:
                    HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                runAbcControlpathOpt(netlist.builder, worklist, removed, netlist.iterAllNodes())
                if dbgEn:
                    HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                runLlvmCmpOpt(builder, worklist, removed, netlist.iterAllNodes())
                if dbgEn:
                    HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)

            if dbgEn:
                HlsNetlistPassConsystencyCheck._checkConnections(netlist, removed)

            if not worklist:
                reachAnalysis = netlist.getAnalysisIfAvailable(HlsNetlistAnalysisPassReachability(netlist, removed))
                HlsNetlistPassSimplifySync(dbgTracer).apply(hls, netlist, parentWorklist=worklist, parentRemoved=removed)
                dbgTracer.log("rehash")
                HlsNetlistPassRehashDeduplicate().apply(hls, netlist, worklist=worklist, removed=removed)
                if not worklist:
                    HlsNetlistPassSimplifySync(dbgTracer).apply(hls, netlist, parentWorklist=worklist, parentRemoved=removed)
                    if dbgEn:
                        HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                        HlsNetlistPassConsystencyCheck._checkConnections(netlist, removed)
                    if reachAnalysis is None:
                        netlist.invalidateAnalysis(HlsNetlistAnalysisPassReachability(netlist, removed))
                    if not worklist:
                        break
                elif reachAnalysis is None:
                    netlist.invalidateAnalysis(HlsNetlistAnalysisPassReachability(netlist, removed))

            runCntr += 1
            if runCntr > self.OPT_ITERATION_LIMIT:
                while worklist:
                    n = worklist.pop()
                    if n in removed or self._DCE(n, worklist, removed):
                        continue
                dbgTracer.log(("giving up after ", runCntr, " rounds"))
                break

        if removed:
            netlist.filterNodesUsingSet(removed)
            if dbgEn:
                HlsNetlistPassConsystencyCheck().apply(hls, netlist)

    def _isTriviallyDead(self, n: HlsNetNode):
        if isinstance(n, self.NON_REMOVABLE_CLS):
            return False
        else:
            if not isinstance(n, HlsNetNode):
                raise AssertionError(n)

            for uses in n.usedBy:
                if uses:
                    return False

            return True

