from typing import Tuple, Callable, Sequence

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hwIO import HwIO
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding
from hwtHls.architecture.transformation.hlsAndRtlNetlistPass import HlsAndRtlNetlistPass
from hwtHls.code import OP_LSHR, OP_ASHR, OP_SHL, OP_CTLZ, OP_ZEXT, OP_FSHL, \
    OP_FSHR, OP_ROL, OP_ROR
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE, HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.scheduler import asapSchedulePartlyScheduled
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import disconnectAllInputs
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from hwtSimApi.constants import Time
from hwtSimApi.utils import period_to_freq

HwModuleHwIoForNodePortGetter = Callable[[HlsNetNodeOperator, HwModule], Sequence[HwIO]]


class HlsAndRtlNetlistPassOperatorToHwtLowering(HlsAndRtlNetlistPass):
    """
    Lower operators which are not compatible with hwt/hdlConvertorAst library to compatible form.
    """

    def _createHwModule_OP_CTLZ(self, n: HlsNetNodeOperator) -> Tuple[HwModule, HwModuleHwIoForNodePortGetter, HwModuleHwIoForNodePortGetter]:
        from hwtHls.architecture.transformation._operatorToHwtLowering.operatorHwImplementations.countBits import CountLeadingZeros
        m = CountLeadingZeros()
        m.FREQ = int(period_to_freq(n.netlist.realTimeClkPeriod * Time.s))
        m.DATA_WIDTH = n.dependsOn[0]._dtype.bit_length()
        return m, lambda n, m: (m.data_in,), lambda n, m: (m.data_out,)

    def _replaceHlsNetNodeOperatorWithHwModule(self, compBuilder: AbstractComponentBuilder,
                                               n: HlsNetNodeOperator, m: HwModule,
                                               inGetter: HwModuleHwIoForNodePortGetter,
                                               outGetter: HwModuleHwIoForNodePortGetter):
        """
        Create a component instance, reroute ports, remove original node
        """
        name = n.name
        if name is None:
            name = f"n{n._id:d}_{n.operator.id:s}"
        name = compBuilder._findSuitableName(name)
        setattr(compBuilder.parent, name, m)
        compBuilder._propagateClkRstn(m)
        builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
        netlist = n.netlist
        clkPeriod = netlist.normalizedClkPeriod
        parent: ArchElement = n.getParent()
        assert isinstance(parent, ArchElement), (n, parent)
        inpCnt = 0
        for dep, inpTime, inpHwIo in zip(n.dependsOn, n.scheduledIn, inGetter(n, m)):
            dep: HlsNetNodeOut
            assert inpHwIo._dtype == dep._dtype, ("Original node input must have same type as in of module replacing it",
                                                  n, inpHwIo._dtype, dep._dtype, inpHwIo, dep)
            # for every input port create write to new module input signal
            inpWrite = HlsNetNodeWrite(netlist, inpHwIo, mayBecomeFlushable=False)
            inpWrite.setNonBlocking()
            inpWrite.setRtlUseReady(False)
            inpWrite.setRtlUseValid(False)
            inpWrite.assignRealization(EMPTY_OP_REALIZATION)
            inpWrite._setScheduleZeroTimeSingleClock(inpTime)
            parent._addNodeIntoScheduled(inpTime // clkPeriod, inpWrite)

            dep.connectHlsIn(inpWrite._portSrc)
            inpCnt += 1

        assert inpCnt == len(n._inputs), ("Every input must be replaced",
                                          n, inpCnt, len(n._inputs), n._inputs, tuple(inGetter(n, m)))
        disconnectAllInputs(n, [])

        outCnt = 0
        for outHwIo, out, outTime in zip(outGetter(n, m), n._outputs, n.scheduledOut):
            # for every output port replace it with read from new module output signal
            assert outHwIo._dtype == out._dtype, ("Original node output must have same type as out of module replacing it",
                                                  n, outHwIo._dtype, out._dtype, outHwIo, out)
            outRead = HlsNetNodeRead(netlist, outHwIo, out._dtype)
            outRead.setRtlUseReady(False)
            outRead.setRtlUseValid(False)
            outRead.setNonBlocking()
            outRead.assignRealization(EMPTY_OP_REALIZATION)
            outRead._setScheduleZeroTimeSingleClock(outTime)
            parent._addNodeIntoScheduled(outTime // clkPeriod, outRead)

            builder.replaceOutput(out, outRead._portDataOut, True, checkCycleFree=False)
            outCnt += 1
        assert outCnt == len(n._outputs), ("Every output must be replaced",
                                           n, outCnt, len(n._outputs), n._outputs, tuple(outGetter(n, m)))

        n.markAsRemoved()

    @staticmethod
    def _assertIsConcat(n: HlsNetNode):
        assert isinstance(n, HlsNetNodeOperator) and n.operator == HwtOps.CONCAT, n
        return True

    @staticmethod
    def _assertIsConcatAnyShiftOrIndex(n: HlsNetNode):
        assert isinstance(n, HlsNetNodeOperator) and n.operator in (HwtOps.CONCAT, HwtOps.INDEX, OP_LSHR, OP_ASHR, OP_SHL, OP_ROL, OP_ROR), n
        return True

    def _replaceNodeWithExpression(self, n: HlsNetNodeOperator, newO: HlsNetNodeOut, newNodeCnt: int, newNodeTypeCheckFn: Callable[[HlsNetNode], bool]):
        parent: ArchElement = n.parent
        netlist = n.netlist
        clkI = n.scheduledZero // netlist.normalizedClkPeriod
        newlyScheduledNodes = asapSchedulePartlyScheduled(newO, newNodeTypeCheckFn, beginOfFirstClk=n.scheduledIn[0])
        assert len(newlyScheduledNodes) == newNodeCnt, newlyScheduledNodes
        for newNode in newlyScheduledNodes:
            parent._addNodeIntoScheduled(clkI, newNode)

        builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
        builder.replaceOutput(n._outputs[0], newO, True)
        disconnectAllInputs(n, [])
        n.markAsRemoved()

    def _lower_OP_ZEXT(self, n: HlsNetNodeOperator):
        nodeOut = n._outputs[0]
        paddingWidth = nodeOut._dtype.bit_length() - n.dependsOn[0]._dtype.bit_length()
        assert paddingWidth > 0, n
        builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()

        # replace with Concat(0, src0)
        padding = builder.buildConst(HBits(paddingWidth).from_py(0))
        newO = builder.buildConcat(n.dependsOn[0], padding._outputs[0])
        self._replaceNodeWithExpression(n, newO, 2, self._assertIsConcat)

    def _lower_OP_FSHL(self, n: HlsNetNodeOperator):
        src0, src1, sh = n.dependsOn
        builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
        nodeOut = n._outputs[0]
        isRotateLeft = src0 == src1
        if isRotateLeft:
            newO = builder.buildOp(OP_ROL, None, nodeOut._dtype, src0, sh, name=n.name)
            newNodeCnt = 1
        else:
            # (Concat(src0, src1) << sh)[:width]
            newConc = builder.buildConcat(src1, src0)  # lowest bits first
            newShVal = builder.buildOp(OP_SHL, None, newConc._dtype, (newConc, sh))
            width0 = src0._dtype.bit_length()
            width1 = src1._dtype.bit_length()
            _worklist = []
            newO = builder.buildIndexConstSlice(nodeOut._dtype, newShVal, width0 + width1, width1, _worklist, None, name=n.name)
            assert not _worklist
            newNodeCnt = 3

        self._replaceNodeWithExpression(n, newO, newNodeCnt, self._assertIsConcatAnyShiftOrIndex)

    def _lower_OP_FSHR(self, n: HlsNetNodeOperator):
        src0, src1, sh = n.dependsOn
        builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
        nodeOut = n._outputs[0]
        isRotateRight = src0 == src1
        if isRotateRight:
            newO = builder.buildOp(OP_ROR, None, nodeOut._dtype, src0, sh, name=n.name)
            newNodeCnt = 1
        else:
            # (Concat(src1, src0) >> sh)[width:]
            newConc = builder.buildConcat(src0, src1)  # lowest bits first
            newShVal = builder.buildOp(OP_LSHR, None, newConc._dtype, (newConc, sh))
            width0 = src0._dtype.bit_length()
            _worklist = []
            newO = builder.buildIndexConstSlice(nodeOut._dtype, newShVal, width0, 0, _worklist, None, name=n.name)
            assert not _worklist
            newNodeCnt = 3

        self._replaceNodeWithExpression(n, newO, newNodeCnt, self._assertIsConcatAnyShiftOrIndex)

    @override
    def runOnHlsNetlistImpl(self, netlist:HlsNetlistCtx) -> PreservedAnalysisSet:
        changed = False
        NATIVE_HWT_OPS = HlsNetNodeOperator.NATIVE_HWT_OPS
        compBuilder = AbstractComponentBuilder(netlist.parentHwModule, None, "hls_")
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if n._isMarkedRemoved:
                continue
            if isinstance(n, HlsNetNodeOperator) and n.operator not in NATIVE_HWT_OPS:
                # for simple operators (like zext) just replace it with hwt compatible nodes
                # for more complicated operators (like ctlz) create a new HwModule and replace
                # every appearance of of operator like this by component of new HwMoudule
                if n.operator == OP_ZEXT:
                    self._lower_OP_ZEXT(n)
                elif n.operator == OP_CTLZ:
                    opModule, inGetter, outGetter = self._createHwModule_OP_CTLZ(n)
                    self._replaceHlsNetNodeOperatorWithHwModule(compBuilder, n, opModule, inGetter, outGetter)
                elif n.operator == OP_FSHL:
                    self._lower_OP_FSHL(n)
                elif n.operator == OP_FSHR:
                    self._lower_OP_FSHR(n)
                else:
                    raise NotImplementedError(n)
                changed = True

        if changed:
            netlist.filterNodesUsingRemovedSet(recursive=True)
            pa = PreservedAnalysisSet.preserveScheduling()
            pa.add(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
            return pa
        else:
            return PreservedAnalysisSet.preserveAll()
