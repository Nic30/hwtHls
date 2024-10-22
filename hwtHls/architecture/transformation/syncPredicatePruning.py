from typing import Union, List

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.transformation.dce import ArchElementDCE
from hwtHls.architecture.transformation.hlsArchPass import HlsArchPass
from hwtHls.architecture.transformation.simplify import ArchElementValuePropagation
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import iterAllHierachies
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsArchPassSyncPredicatePruning(HlsArchPass):
    """
    If there is a blocking read/write in multi stage pipeline it guaranteed that the next stage is executed
    only with read.validNb==1/write.readyNB (value is passed trough registers on the way)
    as the node blocks the execution of next stage.
    Same thing applies for predecessor states in FSM.
    
    This pass replaces such valid/validNB/ready/readyNB uses with 1 and performs simple value propagation.
    """

    @staticmethod
    def _getOtherOperand(n: HlsNetNode, op: HlsNetNodeOut):
        for dep in n.dependsOn:
            if dep is op:
                continue
            return dep
        raise AssertionError("missing operands", n)

    def _replaceUsesOfOutWith1InLaterClkWindows(self,
                                                modifiedElements: SetList[Union[HlsNetNodeAggregate, HlsNetlistCtx]],
                                                worklist: SetList[HlsNetNode],
                                                out: HlsNetNodeOut,
                                                replacementValue:Union[bool, HlsNetNodeOut]):
        n = out.obj
        clkPeriod = n.netlist.normalizedClkPeriod
        outTime = n.scheduledOut[out.out_i]
        defClkI = outTime // clkPeriod
        hasUseInLaterClocks = False
        nagationOfOut: List[HlsNetNodeOut] = []
        andOps: List[HlsNetNodeOut] = []
        orOps: List[HlsNetNodeOut] = []
        xorOps: List[HlsNetNodeOut] = []

        for u in n.usedBy[out.out_i]:
            useClkI = u.obj.scheduledIn[u.in_i] // clkPeriod
            if defClkI < useClkI:
                # used in later cycle, for this user the out will be replaced with 1
                worklist.append(u.obj)
                hasUseInLaterClocks = True
            else:
                assert defClkI == useClkI, (out, u, defClkI, useClkI)
                # used in same cycle, try cases for logical operators to discover cases
                # where propagated value is something known
                uObj = u.obj
                if isinstance(uObj, HlsNetNodeOperator):
                    op = uObj.operator
                    if op == HwtOps.NOT:
                        nagationOfOut.append(uObj._outputs[0])
                    elif op == HwtOps.OR:
                        orOps.append(uObj._outputs[0])
                    elif op == HwtOps.AND:
                        andOps.append(uObj._outputs[0])
                    elif op == HwtOps.XOR:
                        xorOps.append(uObj._outputs[0])

        if hasUseInLaterClocks:
            b: HlsNetlistBuilder = n.getHlsNetlistBuilder()
            if isinstance(replacementValue, bool):
                c1 = b.buildConstBit(int(replacementValue))
                c1.obj.resolveRealization()
                c1.obj._setScheduleZeroTimeSingleClock(outTime)
                newOut = c1
            else:
                newOut = replacementValue
            b.replaceOutputIf(out, newOut, lambda i: i.obj.scheduledIn[i.in_i] // clkPeriod > defClkI)
            modifiedElements.append(n.parent if n.parent else n.netlist)

        if isinstance(replacementValue, bool):
            for out_n in nagationOfOut:
                if self._replaceUsesOfOutWith1InLaterClkWindows(
                    modifiedElements, worklist, out_n, not replacementValue):
                    worklist.append(out_n.obj)

            if replacementValue:
                # x & 1 = x
                for _out in andOps:
                    self._replaceUsesOfOutWith1InLaterClkWindows(
                        modifiedElements, worklist, _out, self._getOtherOperand(_out.obj, out))

                # x | 1 = 1
                for _out in orOps:
                    self._replaceUsesOfOutWith1InLaterClkWindows(
                        modifiedElements, worklist, _out, True)
                # [TODO] x ^ 1 = ~x (insert and schedule a potentially new NOT operator)

            else:
                # x & 0 = 0
                for _out in andOps:
                    self._replaceUsesOfOutWith1InLaterClkWindows(
                        modifiedElements, worklist, _out, False)

                # x | 0 = x
                for _out in orOps:
                    self._replaceUsesOfOutWith1InLaterClkWindows(
                        modifiedElements, worklist, _out, self._getOtherOperand(_out.obj, out))

                # x ^ 0 = x
                for _out in xorOps:
                    self._replaceUsesOfOutWith1InLaterClkWindows(
                        modifiedElements, worklist, _out, False)

        else:
            # x & x = x
            for _out in andOps:
                otherOp = self._getOtherOperand(_out.obj, out)
                if otherOp is replacementValue:
                    self._replaceUsesOfOutWith1InLaterClkWindows(
                        modifiedElements, worklist, _out, otherOp)

            # x | x = x
            for _out in orOps:
                otherOp = self._getOtherOperand(_out.obj, out)
                if otherOp is replacementValue:
                    self._replaceUsesOfOutWith1InLaterClkWindows(
                        modifiedElements, worklist, _out, otherOp)

        return hasUseInLaterClocks

    @override
    def runOnHlsNetlistImpl(self, netlist:HlsNetlistCtx):
        changed = False
        dbgTracer = DebugTracer(None)
        modifiedElements: SetList[Union[HlsNetNodeAggregate, HlsNetlistCtx]] = SetList()
        worklist: SetList[HlsNetNode] = SetList()  # worklist for value propagation and DCE
        for parent in iterAllHierachies(netlist):
            for n in parent.subNodes:
                n: HlsNetNode
                if isinstance(n, HlsNetNodeRead) and n._isBlocking:
                    for vld in (n._valid, n._validNB):
                        if vld is not None:
                            self._replaceUsesOfOutWith1InLaterClkWindows(modifiedElements, worklist, vld, True)

                elif isinstance(n, HlsNetNodeWrite) and n._isBlocking:
                    for rd in (n._ready, n._readyNB):
                        if rd is not None:
                            self._replaceUsesOfOutWith1InLaterClkWindows(modifiedElements, worklist, rd, True)

        ArchElementValuePropagation(dbgTracer, modifiedElements, worklist, None)
        ArchElementDCE(netlist, netlist.subNodes, None)
        
        for elm in modifiedElements:
            elm: HlsNetNodeAggregate
            elm.filterNodesUsingRemovedSet(recursive=False)

        if changed:
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()
