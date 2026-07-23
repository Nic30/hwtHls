
from dataclasses import dataclass
from typing import Optional

from hwt.code import split_to_segments
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.math import log2ceil
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.hardBlock import ComponentGeneratorForHardBlock
from hwtHls.llvm.llvmIr import Instruction, \
    MachineInstr, MachineRegisterInfo, InstructionToCallInst, CallInst
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from pyDigitalWaveTools.vcd.writer import VcdWriter
from pyMathBitPrecise.bit_utils import mask
from tests.math.addMasked import AddMaskedHardblock
from tests.math.addTree import OP_ADD_TREE
from tests.math.maskSegments import OP_MASK_SEGMENTS


@dataclass(frozen=True)
class AddMaskedProps():
    stateWidth: int
    inputWidth: int
    inputCnt: int
    hasStateIn: bool

# class AddMaskedLayerType(Enum):
#    MASK = auto()
#    ADD_TREE = auto()
#    ADD_FINAL = auto()

# @dataclass(frozen=True)
# class AddMaskedLayerTime():
#    begin: SchedTime
#    end: SchedTime
#    inputCnt: int
#    type: AddMaskedLayerType
#    
#    def duration(self):
#        return self.end - self.begin 
#
#
# @dataclass(frozen=True)
# class AddMaskedLayerSliceMeta():
#    realization: OpRealizationMeta  # realization of component containing this slices
#    schedBegin: SchedTime
#    inputCnt: int
#    layerRange: tuple[int, int]  # specifes which of the origianal layers are members of this slice


class ComponentGeneratorAddMasked(ComponentGeneratorForHardBlock):
    """
    Component generator for :class:`tests.math.addTreeMasked.AddMaskedHardblock`
    """

    def __init__(self, platform:DefaultHlsPlatform, genNamePrefix:str, moduleName:str):
        super().__init__(platform, genNamePrefix, moduleName)
        self.schedulingCache: dict[AddMaskedProps,
                                   (ComponentRealizationMeta,
                                    ComponentRealizationMeta)
                                   # the list hold in, out time and number of inputs for each layer (relative to schedZero)
                                   ] = {}

    @staticmethod
    def _evalFn(resUndefVal: HBitsConst, stateIn: HBitsConst, dataIn: HBitsConst, maskIn: Optional[HBitsConst]) -> HBitsConst:
        if stateIn is not None and not stateIn._is_full_valid():
            return resUndefVal

        itemCnt = maskIn._dtype.bit_length()
        dataItemWidth = dataIn._dtype.bit_length() // itemCnt
        res = int(stateIn if stateIn is not None else 0)
        # print("_evalFn", maskIn, dataIn, list(split_to_segments(dataIn, dataItemWidth)))
        for d, m in zip(split_to_segments(dataIn, dataItemWidth), maskIn):
            if not m._is_full_valid():
                return resUndefVal
            else:
                if m:
                    if d._is_full_valid():
                        res = res + int(d)
                    else:
                        return resUndefVal
                else:
                    break
        T = stateIn._dtype
        res = T.from_py(res & mask(T.bit_length()))
        return res

    @override
    def getOperationSpecialization(self, *args):
        return None

    @staticmethod
    def getStateWidthInputWidthAndInputCnt(node: HlsNetNode) -> AddMaskedProps:
        if node.operatorSpecialization:
            # this is node which is split on layers, original props are stored in operatorSpecialization
            res = node.operatorSpecialization[0]
            assert isinstance(res, AddMaskedProps), (node, res)
            return res
        else:
            # state?, data, mask
            hasStateIn = len(node.dependsOn) == 3
            outWidth = node._outputs[0]._dtype.bit_length()
            if hasStateIn:
                stateWidth = node.dependsOn[0]._dtype.bit_length()
                assert stateWidth == outWidth
                stateInIndex = 0
            else:
                assert len(node.dependsOn) == 2, (node)
                stateInIndex = -1
                stateWidth = outWidth
                
            inputCnt = node.dependsOn[stateInIndex + 2]._dtype.bit_length()  # width of the mask
            inputWidth = node.dependsOn[stateInIndex + 1]._dtype.bit_length() // inputCnt
            assert inputWidth % inputCnt == 0
            return AddMaskedProps(stateWidth, inputWidth, inputCnt, hasStateIn)

    @override
    def llvmIrInterpretDecode(self, interpret: LlvmIrInterpret, instr: Instruction,
                              pyObjectPlaceholder: AddMaskedHardblock) -> LlvmIrInstrFunction:
        instr: CallInst = InstructionToCallInst(instr)
        assert instr
        # e.g. placeholderId, stateIn, dataIn, maskIn
        ops = interpret._decodeInstArguments((o.get() for o in tuple(instr.args())[1:]))
        resTy = HBits(instr.getType().getIntegerBitWidth())
        resUndefVal = resTy.from_py(None)

        def _intrinsic_addMasked(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]) -> LlvmIrInstrFunction:
            inArgs = interpret._prepareInstrArguments(ops, regs)
            res = self._evalFn(resUndefVal, *inArgs)
            interpret._storeInstrResult(waveLog, nowTime, regs, instr, res)

        return _intrinsic_addMasked

    @override
    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI: MachineRegisterInfo, instr: MachineInstr,
                               pyObjectPlaceholder: AddMaskedHardblock) -> LlvmMirInstrFunction:
        ops = interpret._decodeInstArguments(MRI, instr, instr.operands())[:-1]
        cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)
        # e.g. dst, fnId, dstWidth, stateIn, dataIn, maskIn, stateInWidth, dataWidth, maskInWidth, enCond
        inArgCnt = (len(ops) - 3) // 2
        assert inArgCnt == 3, instr
        dst, _, dstWidth = ops[:3]
        resTy = HBits(dstWidth)
        inArgs = tuple(ops[3:3 + inArgCnt])
        inArgsIsConst = tuple(isinstance(a, HConst) for a in inArgs)
        resUndefVal = resTy.from_py(None)

        def _intrinsic_addMasked(nowTime: int, regs: list[HConst]):
            if hasRuntimeCond and not regs[cond]:
                res = resUndefVal
            else:
                res = self._evalFn(resUndefVal, *(a if isConst else regs[a]
                                                  for isConst, a in zip(inArgsIsConst, inArgs)))
            regs[dst] = res

        return _intrinsic_addMasked

    # @override
    # def resolveRealizationOfNode(self, node: HlsNetNode) -> ComponentRealizationMeta:
    #    """
    #    This generates a tree where first layer is composed of "&" to mask inputs, then there is a balanced tree
    #    to resolve the sum and thenfinal adder to add stateIn
    #    """
    #    netlist = node.netlist
    #    platform = self.platform
    #    props = self.getStateWidthInputWidthAndInputCnt(node)
    #    assert props.stateWidth >= props.inputWidth, (node, props.stateWidth, props.inputWidth)
    #    cacheKey = props
    #    try:
    #        return self.schedulingCache[cacheKey][1]
    #    except KeyError:
    #        pass
    #
    #    realTimeClkPeriod:float = netlist.realTimeClkPeriod
    #    rInMask:OpRealizationMeta = platform.get_op_realization(HwtOps.AND, None, props.inputWidth, 2, realTimeClkPeriod)
    #    if not rInMask.fitsIntoSingleClockWindow():
    #        raise NotImplementedError()
    #    rAdd:OpRealizationMeta = platform.get_op_realization(HwtOps.ADD, None, props.inputWidth, 2, realTimeClkPeriod)
    #
    #    clkPeriod: SchedTime = netlist.normalizedClkPeriod
    #    schedResolution:float = netlist.scheduler.resolution
    #    ffStoreTime: SchedTime = platform.get_ff_store_time(realTimeClkPeriod, schedResolution)
    #    # time wich is available in clock window for logic
    #    clkTimeBudget: SchedTime = clkPeriod - ffStoreTime - netlist.scheduler.epsilon
    #    adderDelay = ceil((rAdd.inputWireDelay + rAdd.outputWireDelay) / schedResolution)
    #    if adderDelay > clkTimeBudget:
    #        raise TimeConstraintError(
    #                "Impossible scheduling, scheduledZeroMin specifies >=", clkTimeBudget,
    #                " but the best adder node can do is ", adderDelay, node)
    #    if not rAdd.fitsIntoSingleClockWindow():
    #        raise NotImplementedError("The adde itself must be pipelined, all adders must be instantiated explicitely so they "
    #                                  "can call its ComponnetGenerator")
    #    layerOutNormalizedTimes: list[AddMaskedLayerTime] = [
    #        # layer 0 used for intial mask, rest for adders
    #        AddMaskedLayerTime(SchedTime(0),
    #                           SchedTime(ceil((rInMask.inputWireDelay + rInMask.outputWireDelay) / schedResolution)),
    #                           props.inputCnt,
    #                           AddMaskedLayerType.MASK,
    #                           )
    #    ]
    #    # print("layerOutNormalizedTimes", layerOutNormalizedTimes[0])
    #
    #    beginTime = layerOutNormalizedTimes[0].end
    #    beginTime0 = layerOutNormalizedTimes[0].begin
    #    layerInputCnt = props.inputCnt
    #    addTreeLayers = log2ceil(layerInputCnt)
    #    hasStateIn = len(node.dependsOn) == 3
    #    r = rInMask  # accumulator of delay params for all layers together
    #    for isLast, _ in iter_with_last(range(addTreeLayers + (1 if hasStateIn else 0))):  # +1 for final state adder
    #        r = r.addWithKeepout(0, rAdd, clkPeriod, schedResolution, clkTimeBudget)
    #        assert r.inputWireDelay < realTimeClkPeriod, r
    #        assert r.outputWireDelay < realTimeClkPeriod, r
    #        # compute how, the delays change if if add the adder layer to current layer
    #        # the reaalization automatically spawns new clock cycles if necessary on add
    #        if r.isMulticlock:
    #            endTime = SchedTime((r.inputClkTickOffset + r.outputClkTickOffset + 1) * clkPeriod 
    #                                +ceil(r.outputWireDelay / schedResolution))
    #        else:
    #            endTime = beginTime0 + ceil((r.inputWireDelay + r.outputWireDelay) / schedResolution)
    #            
    #        assert beginTime < endTime, (beginTime, endTime)
    #        if beginTime // clkPeriod != endTime // clkPeriod:
    #            # :note: this assumes that rAdd is single clock
    #            beginTime = (r.inputClkTickOffset + r.outputClkTickOffset + 1) * clkPeriod
    #            assert beginTime // clkPeriod == endTime // clkPeriod, (beginTime, endTime, clkPeriod)
    #
    #        # assert beginTime == layerOutNormalizedTimes[0].end or 
    #        # print("layerOutNormalizedTimes", (beginTime, endTime, max(1, layerInputCnt)))
    #        layerOutNormalizedTimes.append(AddMaskedLayerTime(beginTime, endTime, max(1, layerInputCnt),
    #                                                          AddMaskedLayerType.ADD_FINAL
    #                                                          if isLast and hasStateIn else
    #                                                          AddMaskedLayerType.ADD_TREE))
    #        beginTime = endTime
    #        layerInputCnt //= 2
    #
    #    assert layerInputCnt <= 1, layerInputCnt 
    #    
    #    r = ComponentRealizationMeta.fromOpRealization(r)
    #    self.schedulingCache[cacheKey] = (r, r, layerOutNormalizedTimes)
    #    return r

    # def splitOnClkWindowsClockWindowLayers(self, netlist: HlsNetlistCtx, nodeForDbg: HlsNetNodeOperator, t0: SchedTime,
    #                                       layerTimes: list[AddMaskedLayerTime])\
    #        ->Generator[AddMaskedLayerSliceMeta, None, None]:
    #    clkPeriod: SchedTime = netlist.normalizedClkPeriod
    #    platform = netlist.platform
    #    schedResolution:float = netlist.scheduler.resolution
    #    ffStoreTime: SchedTime = platform.get_ff_store_time(netlist.realTimeClkPeriod, schedResolution)
    #
    #    beginLayerIndex = 0
    #    clkIndex0 = t0 // clkPeriod
    #    
    #    for layerIndex, (layer, nextLayer) in enumerate(iter_with_lookahead(layerTimes)):
    #        layer: AddMaskedLayerTime
    #        nextLayer: Optional[AddMaskedLayerTime]
    #        
    #        clkIndex = clkIndex0 + layer.begin // clkPeriod
    #        isLast = nextLayer is None
    #        if not isLast and layer.type == nextLayer.type:
    #            nextClkIndex = clkIndex0 + nextLayer.begin // clkPeriod
    #            if clkIndex == nextClkIndex:
    #                # the successor will merge with this layer later
    #                # and both will be mapped to a single layer slice in the same clk window
    #                continue
    #
    #        # assert layerIndex > 0, "layer0 can not have begin after clock window boundary, because it is the beginning"
    #        layerSliceEnd = layer.end
    #        assert layerSliceEnd <= (clkIndex + 1) * clkPeriod - ffStoreTime, (nodeForDbg, "must fit into available time")
    #        firstLayer = layerTimes[beginLayerIndex]
    #        wireDelay = layerSliceEnd - firstLayer.begin
    #        assert wireDelay > 0, (wireDelay, layerIndex, layer, nodeForDbg)
    #        assert wireDelay < clkPeriod, (nodeForDbg, wireDelay, clkPeriod)
    #        realization = OpRealizationMeta(outputWireDelay=wireDelay * schedResolution)
    #        # prevLayerOutCnt = layerInputCnt
    #        m = AddMaskedLayerSliceMeta(realization, firstLayer.begin, firstLayer.inputCnt, (beginLayerIndex, layerIndex + 1))
    #        yield m
    #        beginLayerIndex = layerIndex + 1

    @override
    def toHwtCompatibleOperatorBeforeScheduling(self, node: "HlsNetNode", worklist: SetList["HlsNetNode"]) -> bool:
        debugTracer = node.netlist.dbgSubmoduleBuidTracer
        with debugTracer.scoped(self, node):

            assert len(node._outputs) == 1, self

            ops = node.dependsOn
            if len(ops) == 2:
                stateIn = None
                dataIn, maskIn = ops
            else:
                stateIn, dataIn, maskIn = ops
                
            builder = HlsNetlistBuilderWithWorklist(node.getHlsNetlistBuilder(), worklist)
            stateT = node._outputs[0]._dtype
            assert stateT.bit_length() == dataIn._dtype.bit_length() // maskIn._dtype.bit_length(), (node, stateT, dataIn._dtype, maskIn._dtype)
            outCnt = maskIn._dtype.bit_length()
            hasName = node.name is not None
            maskLayer = builder.buildOpManyDst(OP_MASK_SEGMENTS, None,
                                               tuple(stateT for _ in range(outCnt)),
                                               dataIn,
                                               maskIn,
                                               name=node.name + "_mask" if hasName else None)
            adderTreeLayer = builder.buildOp(OP_ADD_TREE, None, stateT, *maskLayer._outputs, name=node.name + "_add" if hasName else None)
    
            if stateIn is not None:
                finalAdd = builder.buildAdd(adderTreeLayer, stateIn, name=node.name + "_finAdd" if hasName else None)
                debugTracer.log(("replacing with", maskLayer, adderTreeLayer.obj, finalAdd.obj))
            else:
                debugTracer.log(("replacing with", maskLayer, adderTreeLayer.obj))
                finalAdd = adderTreeLayer
            
            replaceOperatorNodeWith(node, finalAdd, worklist)
            return True

        # for each inter layer connections check if it is crossing clock boundary
        # if this is the case, create new node, move out into it and create connected port pairs fo every value
        # crossing the the clock boundary
        # netlist = node.netlist
        # with netlist.dbgSubmoduleBuidTracer.scoped(gen, self):
        # props = self.getStateWidthInputWidthAndInputCnt(node)
        # _, _, layerTimes = self.schedulingCache[props]
        # layerTimes: list[tuple[SchedTime, SchedTime]]
        # t0: SchedTime = min(node.scheduledIn)
        # builder.unregisterOperatorNode(node)
        # hadStateIn = props.hasStateIn
        # if hadStateIn:
        #    # remove stateIn as it will be connnected to last layer
        #    stateIn: HlsNetNodeOut = self.dependsOn[0]
        #    stateInInp: HlsNetNodeIn = self._inputs[0]
        #    stateInInp.disconnectFromHlsOut(stateIn)
        #    node._removeInput(0)
        #
        # # clean scheduling props which will be altered
        # node.resetScheduling()
        # node.deleteRealization()

        # disconnect output and backup its users
    #    outUsers = tuple(node.usedBy[0])
    #    oOut = node._outputs[0]
    #    for use in outUsers:
    #        use: HlsNetNodeIn
    #        use.disconnectFromHlsOut(oOut)
    #    # oOut.name = None  # name would be misleading because now this output would be used for data to next stage
    #    builder.unregisterOperatorNode(node)
    #    disconnectAllInputs(node, worklist)
    #    node.markAsRemoved()
    #
    #    clkPeriod = netlist.normalizedClkPeriod
    #    schedResolution = netlist.scheduler.resolution
    #    parent: ArchElement = node.parent
    #    isFirst = True
    #    prevNode = None
    #    for layersSlice, nextLayerSlice in iter_with_lookahead(self.splitOnClkWindowsClockWindowLayers(
    #            netlist, node, t0, layerTimes)):
    #        layersSlice: AddMaskedLayerSliceMeta
    #        
    #        isLast = nextLayerSlice is None
    #
    #        # for each layer if the begin is in next clock after previous layer
    #        # * set realization and scheduling to previous node
    #        # * add outputs to it
    #        # * construct next layer node without realization
    #        inDelay = ceil(layersSlice.realization.inputWireDelay / schedResolution)
    #        if isFirst:
    #            # :note: layer 0 will implement masking only
    #            outCnt = maskIn._dtype.bit_length()
    #            newNode = builder.buildOpManyDst(OP_MASK_SEGMENTS, None,
    #                                             tuple(stateT for _ in range(outCnt)),
    #                                             dataIn,
    #                                             maskIn,
    #                                             name=node.name)
    #            assert t0 + inDelay <= clkPeriod, (t0, inDelay)
    #            isFirst = False
    #        elif isLast and stateIn is not None:
    #            assert prevNode is not None and len(prevNode._outputs) == 1, (prevNode, len(prevNode._outputs))
    #            assert layersSlice.inputCnt == 1, self
    #            assert nextLayerSlice is None
    #            o = builder.buildAdd(prevNode._outputs[0], stateIn)
    #            newNode = o.obj
    #            # add to parent so we can freely connect, but the newNode is not yet
    #            # in a specific clock window (it is added on yeld)
    #        else:
    #            assert layersSlice.inputCnt > 1, (self, "otherwise it would be useless to create add tree with 1 input")
    #            operatorSpecialization = tuple(layerTimes[layersSlice.layerRange[0]:layersSlice.layerRange[1]])
    #            if isLast:
    #                outCnt = 1
    #            else:
    #                outCnt = nextLayerSlice.inputCnt
    #            newNode = builder.buildOpManyDst(OP_ADD_TREE_FRAGMENT,
    #                                             operatorSpecialization,
    #                                             tuple(stateT for _ in range(outCnt)),
    #                                             *prevNode._outputs
    #                                     )
    #
    #        netlist.dbgSubmoduleBuidTracer.log(("OP_ADD_MASKED", node._id, "replacing layers ", layersSlice.layerRange, " with", newNode._id, newNode.operator))
    #        # the first layer is likely to have some offset, the delay is in delay
    #        # next layers always start at clock window begin, the dealy is out delay
    #
    #        # schedule previous node once it has all outputs instantiated
    #        newNode.assignRealization(layersSlice.realization)
    #        newNode._setScheduleZeroTimeSingleClock(layersSlice.schedBegin + inDelay)
    #        assert newNode.scheduledZero >= 0, newNode
    #        clkI = newNode.getFirstSchedZeroClkI()
    #        for iTime in newNode.scheduledIn:
    #            assert iTime // clkPeriod == clkI, (iTime, clkI)
    #        for oTime in newNode.scheduledIn:
    #            assert oTime // clkPeriod == clkI, (oTime, clkI)
    #    
    #        # can not yeld self because it would duplicate self in the parent
    #        parent._addNodeIntoScheduled(newNode.getFirstSchedZeroClkI(), newNode, allowNewClockWindow=True)
    #        # now newNode is placed in parent based on scheduling
    #        prevNode = newNode
    #
    #    # connect top output and reoslve scheduling for last layer
    #    o = prevNode._outputs[0]
    #
    #    for u in outUsers:
    #        u: HlsNetNodeIn
    #        o.connectHlsIn(u)
    #    return True

    # @override
    # def toRtlForNode(self, node: "HlsNetNode", allocator: "ArchElement") -> None:
    #    raise NotImplementedError("Should be already lowered in toHwtCompatibleOperatorAfterScheduling")
    #    assert not node._isMarkedRemoved, node
    #    assert not node._isRtlAllocated, node
    #    operands = []
    #    for (dep, t) in zip(node.dependsOn, node.scheduledIn):
    #        assert dep is not None, ("All inputs must be connected", node, node.dependsOn)
    #        _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, t)
    #        assert isinstance(_o, TimeIndependentRtlResourceItem), (dep, _o)
    #        operands.append(_o)
    #
    #    minInTime = min(node.scheduledIn)
    #    props = self.getStateWidthInputWidthAndInputCnt(node)
    #    _, _, layerOutNormalizedTimes = self.schedulingCache[props]
    #    layerOutNormalizedTimes:list[AddMaskedLayerTime]
    #    assert props.stateWidth >= props.inputWidth, (node, props.stateWidth, props.inputWidth)
    #
    #    hasStateIn = False
    #    hasMaskIn = False
    #    if node.operator == OP_ADD_MASKED:
    #        hasMaskIn = True
    #        if node.operatorSpecialization is None or node.operatorSpecialization[1][0] == 0:
    #            # :note: operatorSpecialization if the node fits to 1 clk window
    #            #        or if it is OP_ADD_TREE_FRAGMENT
    #            if len(operands) == 3:
    #                hasStateIn = True
    #                dataIn = operands[1]
    #                maskIn = operands[2]
    #            else:
    #                assert len(operands) == 2, node
    #                # :note: stateIn is removed
    #                dataIn = operands[0]
    #                maskIn = operands[1]
    #        
    #    if hasMaskIn:
    #        layerInputs: list[HBitsRtlSignal] = split_to_segments(dataIn.data, props.inputWidth)
    #        maskInputs: list[HBitsRtlSignal] = [m for m in maskIn.data]
    #        # construct input mask logic
    #        layerInputs = [m._sext(props.stateWidth) & i for i, m in zip(layerInputs, maskInputs)]
    #        minInTime += layerOutNormalizedTimes[0].duration()
    #        layerInputs: list[TimeIndependentRtlResource] = [
    #            allocator.rtlRegisterOutputRtlSignal(minInTime, v, False, False, False)
    #            for v in layerInputs]
    #        # :note: the layer 0 was initial mask &
    #        layerSliceStart = 1
    #    else:
    #        layerInputs: list[TimeIndependentRtlResource] = [op.parent for op in operands]
    #        layerSliceStart = 0
    #    
    #    layerSliceStop = None
    #    if node.operatorSpecialization is not None:
    #        _, layerRange = node.operatorSpecialization
    #        # :note: if the node had stateIn, the last layer is final add which was extracted as separate node
    #        layerSliceStart = layerSliceStart + layerRange[0] 
    #        layerSliceStop = layerRange[1]
    #        assert layerSliceStart <= layerSliceStop, (self, layerSliceStart, layerSliceStop, props)
    #    selectedLayers = layerOutNormalizedTimes[layerSliceStart:layerSliceStop]
    #        # if layerSliceStart != 1:
    #        #    t0 -= selectedLayers[0].begin 
    #            # substract the begin because this node begins after the original begin of items in layerOutNormalizedTimes
    #        # print("toRtlForNode", layerOutNormalizedTimes, "\n", layerRange, "\n", layerOutNormalizedTimes)
    #
    #    # assert selectedLayers
    #
    #    # create "+" layer of adder tree
    #    maxOutTime = max(node.scheduledOut)
    #    # :note: the time of layers is for default implementatino,
    #    #        the concrete nodes may have been moved into a different time
    #    #        from this reason we can not directly use layer.begin/end times
    #    t = minInTime
    #    clkPeriod = node.netlist.normalizedClkPeriod
    #    clkI = t // clkPeriod
    #    for layer in selectedLayers:
    #        layer: AddMaskedLayerTime
    #        assert props.inputCnt == 1 or props.inputCnt % 2 == 0, (
    #            "[todo] this does not work if inputCnt is odd, there is a problem that expectedLayerInputCnt is not computed correctly"
    #            " (e.g. layerInputs=3, expectedLayerInputCnt=1 when it should be 2)")
    #        assert len(layerInputs) == layer.inputCnt, (node, len(layerInputs), layer.inputCnt)
    #
    #        assert minInTime <= t <= maxOutTime, (minInTime, t, maxOutTime, node)
    #        layerInputs: list[TimeIndependentRtlResourceItem] = [d.get(t) for d in layerInputs]
    #        
    #        # layerDelay = layer.begin - layer.end
    #        duration = layer.duration()
    #        if duration > clkPeriod:
    #            raise NotImplementedError("NotImplemented otherwise")
    #
    #        t += duration
    #        if t // clkPeriod != clkI:
    #            t = (clkI + 1) * clkPeriod + duration
    #            clkI += 1
    #        assert t <= maxOutTime, (t, maxOutTime, node, layer) 
    #        layerOutpus: list[TimeIndependentRtlResource] = []
    #        for op0, op1 in grouper(2, layerInputs):
    #            if op1 is None:
    #                # case for final sateIn adder or odd number of inputs
    #                assert props.hasStateIn, node
    #                layerOutpus.append(op0.parent)
    #            else:
    #                v = op0.data + op1.data
    #                res = allocator.rtlRegisterOutputRtlSignal(
    #                    t, v, False, False, False)
    #                layerOutpus.append(res)
    #
    #        layerInputs = layerOutpus
    #
    #    # register outputs
    #    assert len(layerInputs) == len(node._outputs), ("The layers of add tree must reduce number of ",
    #                                                    len(node._outputs), len(layerInputs), node)
    #    if hasStateIn:
    #        assert len(node._outputs) == 1, node
    #        stateIn = operands[0]
    #        lastLayerNormalizedTimes: AddMaskedLayerTime = layerOutNormalizedTimes[-1]
    #        # construct final state add
    #        res = layerInputs[0].get(t + lastLayerNormalizedTimes.begin).data + stateIn.data
    #        res = allocator.rtlRegisterOutputRtlSignal(
    #            node._outputs[0],
    #            res, False, False, False)
    #    else:
    #        for o, oTime, oVal in zip(node._outputs, node.scheduledOut, layerInputs):
    #            allocator.rtlRegisterOutputRtlSignal(
    #                o, oVal.get(oTime).data, False, False, False)
    #        res = []
    #
    #    node._isRtlAllocated = True
    #    return res


class ComponentGeneratorAdd1sComplMasked(ComponentGeneratorAddMasked):

    @override
    @staticmethod
    def _evalFn(resUndefVal: HBitsConst, stateIn: HBitsConst, dataIn: HBitsConst, maskIn: Optional[HBitsConst]) -> HBitsConst:
        if stateIn is not None and not stateIn._is_full_valid():
            return resUndefVal

        itemCnt = maskIn._dtype.bit_length()
        dataItemWidth = dataIn._dtype.bit_length() // itemCnt
        res = int(stateIn if stateIn is not None else 0)
        # print("_evalFn", maskIn, dataIn, list(split_to_segments(dataIn, dataItemWidth)))
        for d, m in zip(split_to_segments(dataIn, dataItemWidth), maskIn):
            if not m._is_full_valid():
                return resUndefVal
            else:
                if m:
                    if d._is_full_valid():
                        res = res + int(d)
                    else:
                        return resUndefVal
                else:
                    break

        T = stateIn._dtype
        w = T.bit_length()
        m = mask(w)
        while True:
            overflow = res >> w
            if overflow == 0:
                break
            else:
                res = (res & m) + overflow
            
        res = T.from_py(res)
        return res
    
    @override
    def toHwtCompatibleOperatorBeforeScheduling(self, node: "HlsNetNode", worklist: SetList["HlsNetNode"]) -> bool:
        """
        Conceptionally similar to "FPGA-based TCP/IP Checksum Offloading Engine for 100 Gbps Networks" "Reduction tree version 3"
        * https://doi.org/10.1109/RECONFIG.2018.8641729 
        * https://github.com/R-EAjks-Compute/FPGA-Based-TCP-IP-Checksum-Offloading-Engine-for-100-Gbps-Networks/
        but this generator instantiates only adder trees using OP_ADD_TREE and the decision about adder implementation
        is done in component generator for it.
        """
    
        debugTracer = node.netlist.dbgSubmoduleBuidTracer
        with debugTracer.scoped(self, node):
            assert len(node._outputs) == 1, self
            ops = node.dependsOn
            if len(ops) == 2:
                stateIn = None
                dataIn, maskIn = ops
            else:
                stateIn, dataIn, maskIn = ops
                
            builder = HlsNetlistBuilderWithWorklist(node.getHlsNetlistBuilder(), worklist)
            stateT = node._outputs[0]._dtype
            inBitwidth = dataIn._dtype.bit_length() // maskIn._dtype.bit_length()
            assert stateT.bit_length() >= inBitwidth, (node, stateT, dataIn._dtype, maskIn._dtype)
            outCnt = maskIn._dtype.bit_length()
            name = node.name
            hasName = node.name is not None
            
            maskLayer = builder.buildOpManyDst(OP_MASK_SEGMENTS, None,
                                               tuple(stateT for _ in range(outCnt)),
                                               dataIn,
                                               maskIn,
                                               name=name + "_mask" if hasName else None)
            
            # build adder tree which will sum the values without overflowing
            minNoOverflowWidthForIn = inBitwidth + log2ceil(outCnt + 1)
            terms: list[HlsNetNodeOut] = []
            for term in maskLayer._outputs:
                term = builder.buildZExt(term, minNoOverflowWidthForIn)
                terms.append(term)
            
            adderTreeLayer = builder.buildOp(OP_ADD_TREE, None, HBits(minNoOverflowWidthForIn), *terms, name=name + "_add" if hasName else None)
            
            # buid adder tree for, sum, overflow and stateIn (to implement ones complement addition)
            terms = []
            outWidth = stateT.bit_length()
            minNoOverflowWidthForOut = max(outWidth, minNoOverflowWidthForIn) + log2ceil(len(terms) + 1 + 1)
            off = 0
            res = adderTreeLayer
            assert res._dtype.bit_length() == minNoOverflowWidthForIn
            while True:
                w = min(minNoOverflowWidthForIn - off, outWidth)
                if w <= 0:
                    del res
                    break
    
                overflow = builder.buildIndexConstSlice(HBits(w), res, off + w, off)
                overflow = builder.buildZExt(overflow, minNoOverflowWidthForOut)
                terms.append(overflow)
                off += w
    
            if stateIn is not None:
                terms.append(builder.buildZExt(stateIn, minNoOverflowWidthForOut))
            
            if len(terms) == 2:
                add2 = builder.buildAdd(terms[0], terms[1], name=name + "_add2" if hasName else None)
            else:
                assert len(terms) > 2, (node, len(terms))
                add2 = builder.buildOp(OP_ADD_TREE, None, terms[0]._dtype, *terms, name=name + "_add2" if hasName else None)
            
            leftoverWidth = minNoOverflowWidthForOut - outWidth
            if leftoverWidth > outWidth:
                raise NotImplementedError("[todo] must repeat previous step to reduce number of add operands") 
            
            # .. code-block::vhld
            #   -- https://doi.org/10.1109/RECONFIG.2018.8641729 
            #   L5(0) = L4(1) + L4(0);
            #   L5(1) = L4(1) + L4(0) + 1;
            #   sumFinal = L5(0) when (L5(0)(16) = '0') else L5(1);
            #
            # [todo] maybe it would be better to create class AddTree1sComplHwModule(AddTreeHwModule) instead
            #        doing this there (readability and code sharing would improve)

            addL = builder.buildTrunc(add2, outWidth, name=name + "_addL0" if hasName else None)
            addH = builder.buildIndexConstSlice(HBits(leftoverWidth), add2, outWidth + leftoverWidth, outWidth, name=name + "_addH0" if hasName else None)
            addH = builder.buildZExt(addH, outWidth)
            addP0 = builder.buildAdd(addL, addH, name=name + "_addP0" if hasName else None)

            addL, addH = (builder.buildConcat(builder.buildConstBit(1), builder.buildZExt(addL, outWidth + 1, name=name + "_addL1" if hasName else None))
                          for term, name in ((addL, "_addL1"), (addH, "_addH1"),)
                          )
            addP1 = builder.buildAdd(addL, addH, name=name + "_addP1" if hasName else None)
            addP1val = builder.buildIndexConstSlice(stateT, addP1, stateT.bit_length() + 1, 1)
            sumFinal = builder.buildMux(stateT, (addP1val, builder.buildGetMsb(addP1), addP0), name=name)
            
            debugTracer.log(("replacing with", sumFinal.obj))
            replaceOperatorNodeWith(node, sumFinal, worklist)
            return True
