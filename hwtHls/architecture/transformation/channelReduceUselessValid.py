from typing import Union

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
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import isAndedToExpression
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding


class HlsArchPassChannelReduceUselessValid(HlsArchPass):

    @staticmethod
    def _reduceBackedgeValid(w: HlsNetNodeWriteBackedge,
                             worklist: SetList[HlsNetNode]):
        """
        If backedge write.extraCond=And(read.valid, ...) and write.skipWhen=And(~read.valid, ...)
        it means that the read.valid is directly implied from read.valid
        :note: case with AND with just 1 item is also supported (and in this case the and operator is not present)
        
        If the channel has initValue the valid is always 1, if it has not it is 0
        """
        r = w.associatedRead
        if r is None or not r._isBlocking:
            return False

        if r.parent is not w.parent:
            return False
        
        
        if not w._isBlocking:
            return False
        
        clkPeriod = w.netlist.normalizedClkPeriod
        if w.scheduledZero // clkPeriod != r.scheduledZero // clkPeriod:
            if not isinstance(r.parent, ArchElementFsm):
                return False  # both read and write must be in same clock or it can not be active at once

        anyValid = [vld for vld in (r._valid, r._validNB) if vld is not None]
        if not anyValid:
            return False

        anyValid_n = []
        builder: HlsNetlistBuilder = r.getHlsNetlistBuilder()
        for valid in anyValid:
            valid_n, _ = builder._tryToFindInCache(HwtOps.NOT, None, (valid,))
            if valid_n is None:
                for _valid_n in builder._tryToFindInUseList(HwtOps.NOT, None, (valid, )):
                    anyValid_n.append(_valid_n)
            else:
                anyValid_n.append(valid_n)

        if not anyValid_n:
            return False

        ec = w.getExtraCondDriver()
        if ec is None or not any(isAndedToExpression(valid, ec) for valid in anyValid):
            return False

        sw = w.getSkipWhenDriver()
        if sw is None or not any(isAndedToExpression(valid_n, sw) for valid_n in anyValid_n):
            return False

        hasInit = bool(r.channelInitValues)
        # if hasInit:
        #     "backedge resolved to always contain valid data"
        # else:
        #     "backedge resolved to never contain valid data"

        c = builder.buildConstBit(int(hasInit))
        for valid in anyValid:
            for u in r.usedBy[valid.out_i]:
                worklist.append(u.obj)
            builder.replaceOutput(valid, c, True)
            r._removeOutput(valid.out_i)

        return True

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        changed = False
        worklist: SetList[HlsNetNode] = SetList()
        dbgTracer = DebugTracer(None)
        modifiedElements: SetList[Union[HlsNetNodeAggregate, HlsNetlistCtx]] = SetList()
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if isinstance(n, HlsNetNodeWrite):
                changed |= self._reduceBackedgeValid(n, worklist)

        if changed:
            ArchElementValuePropagation(dbgTracer, modifiedElements, worklist, None)
            ArchElementDCE(netlist, netlist.subNodes, None)
            for elm in modifiedElements:
                elm: HlsNetNodeAggregate
                elm.filterNodesUsingRemovedSet(recursive=False)

            pa = PreservedAnalysisSet.preserveScheduling()
            pa.add(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
            return pa
        else:
            assert not worklist
            return PreservedAnalysisSet.preserveAll()

