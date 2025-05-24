from typing import Callable, Optional, Sequence, Generator

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOStruct import HwIOStruct, HwIOStructRdVld, HwIOStructVld, \
    HwIOStructRd
from hwt.hwIOs.std import HwIOSignal
from hwt.hwModule import HwModule
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.syncUtils import HwIO_getSyncSignals
from hwtHls.netlist.analysis.ioOrdering import HlsNetlistAnalysisPassIoOrdering
from hwtHls.netlist.builder import HlsNetlistBuilder, \
    HlsNetlistBuilderWithWorklist
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync, \
    createOrderingLink
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.scheduler import asapSchedulePartlyScheduled
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import disconnectAllInputs
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder


HwModuleHwIoForNodePortGetter = Callable[[HlsNetNodeOperator, HwModule], Sequence[HwIO]]


def replaceHlsNetNodeWithExpression(n: HlsNetNodeOperator,
                                    newO: HlsNetNodeOut,
                                    newNodeCnt: Optional[int],
                                    newNodeTypeCheckFn: Callable[[HlsNetNode], bool],
                                    worklist:SetList[HlsNetNode]):
    assert len(n._outputs) == 1, n
    parent: ArchElement = n.parent
    netlist = n.netlist
    clkI = n.scheduledZero // netlist.normalizedClkPeriod
    newlyScheduledNodes = asapSchedulePartlyScheduled(newO, newNodeTypeCheckFn, beginOfFirstClk=n.scheduledIn[0])
    assert newNodeCnt is None or len(newlyScheduledNodes) == newNodeCnt, newlyScheduledNodes
    for newNode in newlyScheduledNodes:
        parent._addNodeIntoScheduled(clkI, newNode)

    builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
    netlist.dbgSubmoduleBuidTracer.log(("replacing with", newO))
    builder.replaceOutput(n._outputs[0], newO, True)
    disconnectAllInputs(n, [] if worklist is None else worklist)
    n.markAsRemoved()
    return newlyScheduledNodes


def _getUseReadyUseValid(hwio):
    if isinstance(hwio, HwIOStructRdVld):
        return True, True
    elif isinstance(hwio, HwIOStructVld):
        return False, True
    elif isinstance(hwio, HwIOStructRd):
        return True, False
    elif isinstance(hwio, (HwIOStruct, HwIOSignal)):
        return False, False
    else:
        raise NotImplementedError(hwio)


def _replaceHlsNetNodeOperatorInputWithWrite(netlist: HlsNetlistCtx,
                                             parent: ArchElement,
                                             inpHwIo: HwIO,
                                             inputUseReadyValid: Optional[tuple[bool, bool]],
                                             inpTime: SchedTime,
                                             inpVal: HlsNetNodeOut) -> HlsNetNodeWrite:

    if inputUseReadyValid is None:
        inUseReady, inUseValid = _getUseReadyUseValid(inpHwIo)
    else:
        inUseReady, inUseValid = inputUseReadyValid
    inpWrite = HlsNetNodeWrite(netlist, inpHwIo, mayBecomeFlushable=False)
    # inpWrite.setNonBlocking()
    inpWrite.setRtlUseReady(inUseReady)
    inpWrite.setRtlUseValid(inUseValid)
    inpWrite.assignRealization(EMPTY_OP_REALIZATION)
    inpWrite._setScheduleZeroTimeSingleClock(inpTime)
    inpWrite._mayBecomeFlushable = False
    parent._addNodeIntoScheduled(inpTime // netlist.normalizedClkPeriod, inpWrite)

    # :note: ordering links are required because other synchronization analysis depends on it
    #  it it used to resolve data dependencies to implement sync for synchronization nodes
    inN = inpVal.obj
    inIsSync = isinstance(inN, HlsNetNodeExplicitSync)
    if not inIsSync or inN._validNB is not inpVal:
        if not inIsSync:
            toSearch: SetList[HlsNetNode] = SetList((inN,))
            seen: set[HlsNetNode] = set()
            dataPredecs = HlsNetlistAnalysisPassIoOrdering._getDirectDataPredecessorsRaw(toSearch, seen)
        else:
            dataPredecs = [inN, ]
        for pred in dataPredecs:
            if isinstance(pred, HlsNetNodeExplicitSync):
                createOrderingLink(pred, inpWrite)

    inpVal.connectHlsIn(inpWrite._portSrc)
    return inpWrite


def _replaceHlsNetNodOperatorOutputWithRead(netlist: HlsNetlistCtx,
                                            parent: ArchElement,
                                            outHwIo: HwIO,
                                            outputUseReadyValid: Optional[tuple[bool, bool]],
                                            dtype: HdlType,
                                            outTime: SchedTime,
                                            firstInputWrite: Optional[HlsNetNodeWrite],
                                            users: list[HlsNetNodeIn],
                                            ) -> HlsNetNodeRead:

    if outputUseReadyValid is None:
        outUseReady, outUseValid = _getUseReadyUseValid(outHwIo)
    else:
        outUseReady, outUseValid = outputUseReadyValid

    outRead = HlsNetNodeRead(netlist, outHwIo, dtype)
    outRead.setRtlUseReady(outUseReady)
    outRead.setRtlUseValid(outUseValid)
    # outRead.setNonBlocking()
    outRead.assignRealization(EMPTY_OP_REALIZATION)
    outRead._setScheduleZeroTimeSingleClock(outTime)
    parent._addNodeIntoScheduled(outTime // netlist.normalizedClkPeriod, outRead)

    toSearch: SetList[HlsNetNode] = SetList()
    seen: set[HlsNetNode] = set()
    for u in users:
        uObj: HlsNetNode = u.obj
        if uObj in seen:
            continue

        if isinstance(uObj, HlsNetNodeExplicitSync):
            createOrderingLink(outRead, uObj)
            seen.add(uObj)
        else:
            toSearch.append(uObj)

    dataSuccs = HlsNetlistAnalysisPassIoOrdering._getDirectDataSuccessorsRaw(toSearch, seen)
    for suc in dataSuccs:
        if isinstance(suc, HlsNetNodeExplicitSync):
            createOrderingLink(outRead, suc)

    if firstInputWrite is not None:
        createOrderingLink(firstInputWrite, outRead)

    return outRead


def replaceHlsNetNodeOperatorWithHwModule(compBuilder: AbstractComponentBuilder,
                                          n: HlsNetNodeOperator,
                                          m: HwModule,
                                          simplifyWorklist: SetList[HlsNetNode],
                                          inGetter: HwModuleHwIoForNodePortGetter=lambda n, m: (m.data_in,),
                                          outGetter: HwModuleHwIoForNodePortGetter=lambda n, m: (m.data_out,),
                                          inputUseReadyValid:Optional[tuple[bool, bool]]=None,  # (False, False),
                                          outputUseReadyValid:Optional[tuple[bool, bool]]=None,  # (False, False),
                                          inputsConcatenated=False,
                                          outputsConcatenated=False,
                                          inputsMayFlush=False,
                                          outputsBitMap:Optional[Sequence[int]]=None,
                                          ):
    """
    Register the component instance on parent HwModule, reroute ports, remove original node
    
    :param outputsBitMap: if outputsConcatenated this argument may be set to a tuple which contains bit indexes
        where each value for HlsNetNodeOperator output is placed in output of HwModule
    """

    name = n.name
    if name is None:
        name = f"n{n._id:d}_{n.operator.id:s}"
    name = compBuilder._findSuitableName(name)
    debugTracer = n.netlist.dbgSubmoduleBuidTracer
    debugTracer.log(("replacing with HwModule", name))
    setattr(compBuilder.parent, name, m)

    compBuilder._propagateClkRstn(m)
    builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
    builder = HlsNetlistBuilderWithWorklist(builder, simplifyWorklist)
    netlist = n.netlist
    clkPeriod = netlist.normalizedClkPeriod
    parent: ArchElement = n.getParent()
    assert isinstance(parent, ArchElement), (n, parent)

    firstInputWrite: Optional[HlsNetNodeWrite] = None
    if inputsConcatenated:
        # concatenate all input values and construct only a single HlsNetNodeWrite to only HwIO of HwModule
        if n._inputs:
            inpTime = min(n.scheduledIn)

            inpHwIo = inGetter(n, m)[0]
            if len(n.dependsOn) > 1:
                inpVal = builder.buildConcat(*n.dependsOn)
                inpValConc = inpVal.obj
                inpValConc.assignRealization(EMPTY_OP_REALIZATION)
                inpValConc._setScheduleZeroTimeSingleClock(inpTime)
                parent._addNodeIntoScheduled(inpTime // clkPeriod, inpValConc)
            else:
                inpVal = n.dependsOn[0]
            firstInputWrite = inpWrite = _replaceHlsNetNodeOperatorInputWithWrite(netlist, parent, inpHwIo, inputUseReadyValid, inpTime, inpVal)
            inpWrite._mayBecomeFlushable = inputsMayFlush

    else:
        inpCnt = 0
        for inpVal, inpTime, inpHwIo in zip(n.dependsOn, n.scheduledIn, inGetter(n, m)):
            inpVal: HlsNetNodeOut
            assert inpHwIo._dtype == inpVal._dtype, ("Original node input must have same type as in of module replacing it",
                                                  n, inpHwIo._dtype, inpVal._dtype, inpHwIo, inpVal)
            inpWrite:HlsNetNodeWrite = _replaceHlsNetNodeOperatorInputWithWrite(netlist, parent, inpHwIo, inputUseReadyValid, inpTime, inpVal)
            inpWrite._mayBecomeFlushable = inputsMayFlush
            if firstInputWrite is None:
                firstInputWrite = inpWrite
            else:
                createOrderingLink(firstInputWrite, inpWrite)

            inpCnt += 1

        assert inpCnt == len(n._inputs), ("Every input must be replaced",
                                          n, inpCnt, len(n._inputs), n._inputs, tuple(inGetter(n, m)))
    disconnectAllInputs(n, simplifyWorklist)

    outCnt = 0
    if outputsConcatenated:
        # HwModule has a single output, values HlsNetNode outputs must be extracted by bit vector slicing
        outTime = max(n.scheduledOut)
        outHwIo = outGetter(n, m)[0]
        outTy = HBits(outHwIo._bit_length() - len(HwIO_getSyncSignals(outHwIo)))
        users = []
        for _users in n.usedBy:
            users.extend(_users)

        outRead = _replaceHlsNetNodOperatorOutputWithRead(netlist, parent, outHwIo, outputUseReadyValid, outTy, outTime, firstInputWrite, users)
        outReadData = outRead._portDataOut
        off = 0
        if outputsBitMap is None:
            outputsBitMap = (None for _ in range(len(n._outputs)))

        for out, offsetOverride in zip(n._outputs, outputsBitMap):
            out: HlsNetNodeOut
            if offsetOverride is not None:
                off = offsetOverride

            w = out._dtype.bit_length()
            d = builder.buildIndexConstSlice(out._dtype, outReadData, off + w, off, name=out.name)
            asapSchedulePartlyScheduled(d, None, beginOfFirstClk=outTime)
            builder.replaceOutput(out, d, True, checkCycleFree=False)
            off += w

    else:
        for outHwIo, out, users, outTime in zip(outGetter(n, m), n._outputs, n.usedBy, n.scheduledOut):
            # for every output port replace it with read from new module output signal
            assert outHwIo._dtype == out._dtype, ("Original node output must have same type as out of module replacing it",
                                                  n, outHwIo._dtype, out._dtype, outHwIo, out)
            outRead = _replaceHlsNetNodOperatorOutputWithRead(netlist, parent, outHwIo, outputUseReadyValid, out._dtype, outTime, firstInputWrite, users)
            builder.replaceOutput(out, outRead._portDataOut, True, checkCycleFree=False)
            outCnt += 1

        assert outCnt == len(n._outputs), ("Every output must be replaced",
                                           n, outCnt, len(n._outputs), n._outputs, tuple(outGetter(n, m)))
    if len(n._inputs) == 1 or inputsConcatenated and (len(n._outputs) == 1 or outputsConcatenated):

        def debugIterShadowConnectionDst() -> Generator[tuple[HlsNetNode, bool], None, None]:
            yield outRead, False

        inpWrite.debugIterShadowConnectionDst = debugIterShadowConnectionDst

    n.markAsRemoved()


def ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(
        generator: ComponentGenerator,
        node: HlsNetNodeOperator,
        hwModule: HwModule,
        simplifyWorklist: SetList[HlsNetNode],
        outputsBitMap:Optional[Sequence[int]]=None,):
    compBuilder = AbstractComponentBuilder(node.netlist.parentHwModule, None, f"{generator._genNamePrefix:s}_{generator._moduleName:s}")
    replaceHlsNetNodeOperatorWithHwModule(
        compBuilder, node, hwModule,
        simplifyWorklist,
        inputsConcatenated=True,
        outputsConcatenated=True,
        outputsBitMap=outputsBitMap,
        inputsMayFlush=not hwModule._isFullyUnrolled(),
    )
