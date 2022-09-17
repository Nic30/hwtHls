from typing import Set

from hwt.code import Concat
from hwt.hdl.operatorDefs import AllOps, COMPARE_OPS, CAST_OPS
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite, \
    HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopHeader import HlsLoopGate
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifyAbc import runAbcControlpathOpt
from hwtHls.netlist.transformation.simplifyUtils import disconnectAllInputs, \
    getConstDriverOf, replaceOperatorNodeWith
from hwtHls.netlist.transformation.simplifyBitwise import netlistReduceMux, \
    netlistReduceNot, netlistReduceAndOrXor
from hwtHls.netlist.transformation.simplifyIo import netlistReduceExplicitSyncConditions, \
    netlistReduceExplicitSyncOrdering, netlistReduceExplicitSync, \
    netlistReduceReadSync, netlistReduceReadNonBlocking


class HlsNetlistPassSimplify(HlsNetlistPass):
    """
    Hls netlist simplification:

    * DCE
    * reduce HlsNetNodeMux with a single input
        * merge HlsNetNodeMux if child mux has parent as only user
    * reduce and/or/xor
    * remove HlsNetNodeExplicitSync (and subclasses like HlsNetNodeRead,HlsNetNodeWrite) skipWhen and extraCond connected to const  
    """
    REST_OF_EVALUABLE_OPS = {AllOps.CONCAT, AllOps.ADD, AllOps.SUB, AllOps.DIV, AllOps.MUL, AllOps.INDEX, *COMPARE_OPS, *CAST_OPS}
    OPS_AND_OR_XOR = (AllOps.AND, AllOps.OR, AllOps.XOR)
    NON_REMOVABLE_CLS = (HlsNetNodeRead, HlsNetNodeWrite, HlsLoopGate, HlsNetNodeExplicitSync)

    def apply(self, hls:"HlsScope", netlist: HlsNetlistCtx):
        threads: HlsNetlistAnalysisPassDataThreads = netlist.getAnalysis(HlsNetlistAnalysisPassDataThreads)
        worklist: UniqList[HlsNetNode] = UniqList(netlist.iterAllNodes())
        removed: Set[HlsNetNode] = set()
        builder = netlist.builder
        firstTime = True
        while True:
            # [todo] it would be more beneficial to use worklist as FIFO because we want to first run DCE and more complex reductions later 
            didModifyExpr = False  # flag which is True if we modified some expression and the ABC should be run
            while worklist:
                n = worklist.pop()
                if n in removed:
                    continue

                if self._isTriviallyDead(n):
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

                    elif o in self.REST_OF_EVALUABLE_OPS:
                        c0 = getConstDriverOf(n._inputs[0])
                        if c0 is None:
                            continue
                        if len(n._inputs) == 1:
                            v = o._evalFn(c0)
                        else:
                            c1 = getConstDriverOf(n._inputs[1])
                            if c1 is None:
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
                    netlistReduceExplicitSyncConditions(n, worklist, removed)
                    netlistReduceExplicitSyncOrdering(n, threads)
                    if isinstance(n, HlsNetNodeRead) and not n._isBlocking:
                        if netlistReduceReadNonBlocking(n, worklist, removed):
                            didModifyExpr = True
                            continue
                    if n.__class__ is HlsNetNodeExplicitSync:
                        if netlistReduceExplicitSync(n, worklist, removed):
                            didModifyExpr = True
                            continue

                elif isinstance(n, HlsNetNodeReadSync):
                    if netlistReduceReadSync(n, worklist, removed):
                        didModifyExpr = True
                        continue

            if firstTime or didModifyExpr:
                runAbcControlpathOpt(netlist.builder, worklist, removed, (n for n in netlist.iterAllNodes() if n not in removed))
                firstTime = False
            
            if not worklist:
                break 
                
        if removed:
            # HlsNetlistPassConsystencyCheck().apply(hls, netlist)
            nodes = netlist.nodes
            netlist.nodes = [n for n in nodes if n not in removed]
            HlsNetlistPassConsystencyCheck().apply(hls, netlist)

    def _isTriviallyDead(self, n: HlsNetNode):
        if isinstance(n, self.NON_REMOVABLE_CLS):
            return False
        else:
            for uses in n.usedBy:
                if uses:
                    return False
            return True

