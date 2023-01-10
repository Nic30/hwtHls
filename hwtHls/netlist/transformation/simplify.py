from typing import Set

from hwt.code import Concat
from hwt.hdl.operatorDefs import AllOps, COMPARE_OPS, CAST_OPS
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopGate import HlsLoopGate, HlsLoopGateStatus
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifyExpr.cmpNormalize import netlistCmpNormalize, _DENORMALIZED_CMP_OPS
from hwtHls.netlist.transformation.simplifyExpr.rehash import HlsNetlistPassRehashDeduplicate
from hwtHls.netlist.transformation.simplifyExpr.simplifyAbc import runAbcControlpathOpt
from hwtHls.netlist.transformation.simplifyExpr.simplifyBitwise import netlistReduceMux, \
    netlistReduceNot, netlistReduceAndOrXor
from hwtHls.netlist.transformation.simplifySync.readOfRawValueToDataAndVld import netlistReadOfRawValueToDataAndVld
from hwtHls.netlist.transformation.simplifySync.simplifyIo import netlistReduceReadReadSyncWithReadOfValidNB
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncConditions
from hwtHls.netlist.transformation.simplifySync.simplifySync import HlsNetlistPassSimplifySync
from hwtHls.netlist.transformation.simplifyUtils import disconnectAllInputs, \
    getConstDriverOf, replaceOperatorNodeWith
from hwtHls.netlist.transformation.simplifyExpr.cmpInAnd import netlistReduceCmpInAnd
from hwtHls.netlist.transformation.simplifyExpr.validAndOrXorEqValidNb import netlistReduceValidAndOrXorEqValidNb
from hwtHls.netlist.transformation.simplifyExpr.cmp import netlistReduceEqNe


class HlsNetlistPassSimplify(HlsNetlistPass):
    """
    HlsNetlist simplification pass

    :var REST_OF_EVALUABLE_OPS: set of operators which can evaluated and are not a specific case
    :var NON_REMOVABLE_CLS: tuple of node classes which can not be removed by dead code removal
    """
    REST_OF_EVALUABLE_OPS = {AllOps.CONCAT, AllOps.ADD, AllOps.SUB, AllOps.DIV, AllOps.MUL, AllOps.INDEX, *COMPARE_OPS, *CAST_OPS}
    OPS_AND_OR_XOR = (AllOps.AND, AllOps.OR, AllOps.XOR)
    NON_REMOVABLE_CLS = (HlsNetNodeRead, HlsNetNodeWrite, HlsLoopGate, HlsNetNodeExplicitSync)

    def __init__(self, dbgTracer: DebugTracer):
        super(HlsNetlistPassSimplify, self).__init__()
        self._dbgTracer = dbgTracer

    def apply(self, hls:"HlsScope", netlist: HlsNetlistCtx):
        worklist: UniqList[HlsNetNode] = UniqList(netlist.iterAllNodes())
        removed: Set[HlsNetNode] = netlist.builder._removedNodes
        builder = netlist.builder
        firstTime = True  # used to run ABC at least once
        dbgTracer = self._dbgTracer
        runCntr = 0
        while True:
            # [todo] it would be more beneficial to use worklist as FIFO because we want to first run DCE and more complex reductions later 
            didModifyExpr = False  # flag which is True if we modified some expression and the ABC should be run
            while worklist:
                n = worklist.pop()
                if n in removed:
                    continue

                if self._isTriviallyDead(n):
                    # DCE
                    if isinstance(n, HlsNetNodeReadSync):
                        p = n.dependsOn[0].obj
                        if isinstance(p, HlsNetNodeExplicitSync):
                            cur = p._associatedReadSync
                            if cur is n:
                                p._associatedReadSync = None

                    elif isinstance(n, HlsLoopGateStatus):
                        loop = n._loop_gate
                        disconnectAllInputs(loop, worklist)
                        removed.add(loop)
                        builder.unregisterNode(loop)
                        
                    builder.unregisterNode(n)
                    disconnectAllInputs(n, worklist)
                    removed.add(n)
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
                
                    elif o in self.OPS_AND_OR_XOR:
                        if netlistReduceAndOrXor(n, worklist, removed):
                            didModifyExpr = True
                            continue
                        elif n._outputs[0]._dtype.bit_length() == 1:
                            if runCntr % 2 == 0 and n.operator is AllOps.AND and netlistReduceCmpInAnd(n, worklist, removed):
                                # :attention: there is an issue in structure in expression generated by ABC and from this function
                                # that is why it is required to choose one to generate final result
                                # otherwise ABC and this function will endlesly rewrite expressions to a different form
                                didModifyExpr = True
                                continue

                            elif netlistReduceValidAndOrXorEqValidNb(n, worklist, removed):
                                didModifyExpr = True
                                continue
                                
                    elif o in self.REST_OF_EVALUABLE_OPS:
                        c0 = getConstDriverOf(n._inputs[0])
                        if c0 is None:
                            if o is AllOps.EQ:
                                if n._outputs[0]._dtype.bit_length() == 1 and netlistReduceValidAndOrXorEqValidNb(n, worklist, removed):
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
                            
                            if o == AllOps.CONCAT:
                                v = Concat(c1, c0)
                            else:
                                v = o._evalFn(c0, c1)

                        replaceOperatorNodeWith(n, builder.buildConst(v), worklist, removed)
                        didModifyExpr = True
                        continue

                elif isinstance(n, HlsNetNodeExplicitSync):
                    n: HlsNetNodeExplicitSync
                    netlistReduceExplicitSyncConditions(dbgTracer, n, worklist, removed)
                    if n in removed:
                        didModifyExpr = True
                        continue
                    if isinstance(n, HlsNetNodeRead):
                        if netlistReduceReadReadSyncWithReadOfValidNB(n, worklist, removed):
                            didModifyExpr = True
                            HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                            continue
                        elif n._rawValue is not None and netlistReadOfRawValueToDataAndVld(n, worklist, removed):
                            didModifyExpr = True
                            HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                            continue                            
                                      
                assert not isinstance(n, HlsNetNodeReadSync), (n, "Should already be removed")
                
            if firstTime or didModifyExpr:
                runAbcControlpathOpt(netlist.builder, worklist, removed, (n for n in netlist.iterAllNodes() if n not in removed))
                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                firstTime = False

            HlsNetlistPassConsystencyCheck._checkConnections(netlist, removed)
            HlsNetlistPassRehashDeduplicate().apply(hls, netlist, worklist=worklist, removed=removed)
            HlsNetlistPassSimplifySync(dbgTracer).apply(hls, netlist, parentWorklist=worklist, parentRemoved=removed)
            HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
            HlsNetlistPassConsystencyCheck._checkConnections(netlist, removed)
            if not worklist:
                break

            runCntr += 1
                
        if removed:
            netlist.filterNodesUsingSet(removed)
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

