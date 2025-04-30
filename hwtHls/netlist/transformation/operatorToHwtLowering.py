from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE, HlsNetNode  # , HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwtHls.architecture.transformation.simplify import ArchElementValuePropagation
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.archElement import ArchElement


class HlsNetlistPassOperatorToHwtLowering(HlsNetlistPass):
    """
    Lower operators which are not compatible with hwt/hdlConvertorAst library to compatible form.
    :note: HwModule classes must be imported on demand because compilation of each may depend on this pass
    """

    def __init__(self, isScheduled: bool) -> None:
        HlsNetlistPass.__init__(self)
        self.isScheduled = isScheduled

    @override
    def runOnHlsNetlistImpl(self, netlist:HlsNetlistCtx) -> PreservedAnalysisSet:
        changed = False
        NATIVE_HWT_OPS = HlsNetNodeOperator.NATIVE_HWT_OPS
        platform = netlist.parentHwModule._target_platform
        _componentGenerators = platform._componentGenerators
        isScheduled = self.isScheduled
        simplifyWorklist: SetList[HlsNetNode] = SetList()
        worklist: SetList[HlsNetNode] = SetList()
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if n._isMarkedRemoved:
                continue
            if isinstance(n, HlsNetNodeOperator):
                # for simple operators (like zext) just replace it with hwt compatible nodes
                # for more complicated operators (like ctlz) create a new HwModule and replace
                # every appearance of of operator like this by component of new HwMoudule
                operator = n.operator
                gen = _componentGenerators.get(operator)
                if gen is None:
                    if n.operator in NATIVE_HWT_OPS:
                        continue
                    else:
                        raise NotImplementedError("Unknown operator is missing componentGenerator", n)

                gen: ComponentGenerator
                if isScheduled:
                    changed |= gen.toHwtCompatibleOperatorAfterScheduling(n, worklist)
                else:
                    changed |= gen.toHwtCompatibleOperatorBeforeScheduling(n, worklist)

        while worklist:
            n = worklist.pop()
            if n._isMarkedRemoved:
                continue
            if isinstance(n, HlsNetNodeOperator):
                operator = n.operator
                gen = _componentGenerators.get(operator)
                if gen is None:
                    if n.operator in NATIVE_HWT_OPS:
                        continue
                    else:
                        raise NotImplementedError("Unknown operator", n)

                gen: ComponentGenerator
                if isScheduled:
                    changed |= gen.toHwtCompatibleOperatorAfterScheduling(n, worklist)
                else:
                    changed |= gen.toHwtCompatibleOperatorBeforeScheduling(n, worklist)

                if not n._isMarkedRemoved:
                    simplifyWorklist.append(n)

            else:
                simplifyWorklist.append(n)

        if changed and simplifyWorklist:
            dbgTracer = DebugTracer(None)
            modifiedArchElements: SetList[ArchElement] = SetList(n.parent for n in simplifyWorklist if n is not None)
            ArchElementValuePropagation(dbgTracer, modifiedArchElements, worklist, None)

        if changed:
            netlist.filterNodesUsingRemovedSet(recursive=True)
            pa = PreservedAnalysisSet.preserveScheduling()
            pa.add(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
            return pa
        else:
            return PreservedAnalysisSet.preserveAll()
