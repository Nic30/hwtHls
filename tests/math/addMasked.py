
from typing import Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import split_to_segments
from hwt.hdl.commonConstants import b1
from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HOperatorDef, HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.math import log2ceil
from hwt.pyUtils.arrayQuery import grouper
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem, \
    TimeIndependentRtlResource
from hwtHls.frontend.hardBlock import HardBlockHwModule, \
    ComponentGeneratorForHardBlock
from hwtHls.llvm.llvmIr import Function, Instruction, \
    MachineInstr, MachineRegisterInfo, InstructionToCallInst, CallInst, HwtHlsInstCombinePass
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.platform.opRealizationMeta import OpRealizationMeta, \
    ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MirToHlsNetlistTranslatedInstrOpsT
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from pyDigitalWaveTools.vcd.writer import VcdWriter
from tests.crypto.crcStep import _crcFnDoesNotUseLLVMOperator


def _addMaskedFnDoesNotUseLLVMOperator(*args):
    raise NotImplementedError()


OP_ADD_MASKED = HOperatorDef(_crcFnDoesNotUseLLVMOperator, idStr="OP_ADD_MASKED")
OP_ADD_MASKED_FRAGMENT = HOperatorDef(_crcFnDoesNotUseLLVMOperator, idStr="OP_ADD_MASKED_FRAGMENT")  # OP_ADD_MASKED sliced on layers to fit into clock cycle


class AddMaskedHardblock(HardBlockHwModule):

    def __init__(self,
            hwInputT: HBits,
            accumulatorT: HBits,
            maxInputsPerBalancedTree: Optional[int]=None,
            name:Optional[str]=None,
            operationRealizationMeta:Optional[OpRealizationMeta]=None):
        hwOutputT = accumulatorT
        _hwInputT = HStruct(
            (accumulatorT, "state"),
            (hwInputT, "data"),
            (BIT, "mask"),
        )
        self.maxInputsPerBalancedTree = maxInputsPerBalancedTree
        HardBlockHwModule.__init__(self, _hwInputT, hwOutputT=hwOutputT, defaultKwargs={"mask": b1}, name=name,
                                   operationRealizationMeta=operationRealizationMeta)

    @override
    def getFnName(self):
        dataWidth = self.hwInputT.field_by_name['data'].dtype.bit_length()
        stateWidth = self.hwInputT.field_by_name['state'].dtype.bit_length()

        return (f"hwtHls.pyObjectPlaceholder.{self.placeholderObjectId:d}.addMasked"
                f".i{stateWidth:d}.i{dataWidth}")

    @override
    def _translateExprHConstHardBlockFunctionDef(self, toLlvm: ToLlvmIrTranslator):
        F:Function = HardBlockHwModule._translateExprHConstHardBlockFunctionDef(self, toLlvm)
        # F.addFnAttr(Attribute.AttrKind.Speculatable)
        strCtx = toLlvm.strCtx
        F.setMetadata(strCtx.addStringRef(HwtHlsInstCombinePass.metadataName_mergableFunction_statePlusMaskedData),
                      toLlvm.mdGetTuple([], False))
        platform = toLlvm.parentHwModule._target_platform
        if OP_ADD_MASKED not in platform._componentGenerators:
            platform._componentGenerators[OP_ADD_MASKED] = \
            platform._componentGenerators[OP_ADD_MASKED_FRAGMENT] = AddMaskedComponentGenerator(platform, "gen", "addMasked")
        return F

    def getComponentGeneratorKey(self):
        return OP_ADD_MASKED


class HlsNetNodeOperatorAddMasked(HlsNetNodeOperator):

    def getStateWidthInputWidthAndInputCnt(self) -> tuple[int, int, int]:
        if self.operatorSpecialization:
            # this is node which is split on layers, original props are stored in operatorSpecialization
            res = self.operatorSpecialization[0]
            assert len(res) == 3, (self, res)
            return res
        else:
            stateWidth = self.dependsOn[0]._dtype.bit_length()
            inputCnt = self.dependsOn[2]._dtype.bit_length()  # width of the mask
            inputWidth = self.dependsOn[1]._dtype.bit_length() // inputCnt
            assert self.dependsOn[1]._dtype.bit_length() % inputCnt == 0
            return (stateWidth, inputWidth, inputCnt)

    def splitOnClkWindowsClockWindowLayers(self, t0: SchedTime, layerTimes: list[tuple[SchedTime, SchedTime, int]]):
        #  t0 = min(self.scheduledIn) # can not be conputed there because time is already reseted
        netlist = self.netlist
        beginLayerIndex = 0
        prevLayerBegin = t0
        clkPeriod: SchedTime = netlist.normalizedClkPeriod
        clkIndex0 = t0 // clkPeriod
        clkIndexPrev = clkIndex0
        schedResolution:float = netlist.scheduler.resolution
        platform = netlist.platform
        ffStoreTime: SchedTime = platform.get_ff_store_time(netlist.realTimeClkPeriod, schedResolution)
        prevLayerInCnt = layerTimes[0][2]
        for isLast, (layerIndex, (layerBegin, layerEnd, layerInputCnt)) in iter_with_last(enumerate(layerTimes)):
            clkIndex = clkIndex0 + layerBegin // clkPeriod
            if clkIndex == clkIndexPrev:
                # this layer is mapped in the same clock window as predecessor
                # we will merge them into 1 result
                continue

            assert layerIndex > 0, "layer0 can not have begin after clock window boundary, because it is the beginning"
            prevLayerEnd = (clkIndexPrev + 1) * clkPeriod - ffStoreTime - 1
            prevInputWireDelay = prevLayerEnd - prevLayerBegin
            assert prevInputWireDelay < clkPeriod, (self, prevInputWireDelay, clkPeriod)
            prevRealization = OpRealizationMeta(inputWireDelay=prevInputWireDelay * schedResolution)
            prevSchedZero = prevLayerEnd
            prevLayerOutCnt = layerInputCnt
            # print("splitOnClkWindowsClockWindowLayers", prevInputWireDelay, prevRealization, prevSchedZero, prevLayerOutCnt, (beginLayerIndex, layerIndex))
            yield (prevRealization, prevSchedZero, prevLayerInCnt, (beginLayerIndex, layerIndex))
            prevLayerBegin = clkIndex * clkPeriod

            if isLast:
                lastClkWindowBegin = clkIndex * clkPeriod
                inputWireDelay = layerEnd - lastClkWindowBegin
                r = OpRealizationMeta(outputWireDelay=inputWireDelay * schedResolution)
                # print("splitOnClkWindowsClockWindowLayers", r, lastClkWindowBegin, 1, (layerIndex, layerIndex + 1), "last")
                yield (r, lastClkWindowBegin, 1, (layerIndex, layerIndex + 1))

            prevLayerInCnt = layerInputCnt
            beginLayerIndex = layerIndex
            clkIndexPrev = clkIndex

    def splitOnClkWindows(self):
        if not self.isMulticlock:
            return False
        # for each inter layer connections check if it is crossing clock boundary
        # if this is the case, create new node, move out into it and create connected port pairs fo every value
        # crossing the the clock boundary
        netlist = self.netlist
        gen: AddMaskedComponentGenerator = netlist.platform._componentGenerators.get(self.operator)
        assert gen is not None, self
        # with netlist.dbgSubmoduleBuidTracer.scoped(gen, self):
        props = self.getStateWidthInputWidthAndInputCnt()
        _, _, layerTimes = gen.schedulingCache[props]
        layerTimes: list[tuple[SchedTime, SchedTime]]
        t0: SchedTime = min(self.scheduledIn)

        assert len(self._outputs) == 1, self
        stateT: HBits = self._outputs[0]._dtype
        builder: HlsNetlistBuilder = netlist.getHlsNetlistBuilder()
        builder.unregisterOperatorNode(self)

        # remove stateIn as it will be connnected to last layer
        stateIn: HlsNetNodeOut = self.dependsOn[0]
        stateInInp: HlsNetNodeIn = self._inputs[0]
        stateInInp.disconnectFromHlsOut(stateIn)
        self._removeInput(0)

        # clean scheduling props which will be altered
        prevNode: HlsNetNodeOperatorAddMasked = self
        prevNode.resetScheduling()
        prevNode.deleteRealization()

        # disconnect output and backup its users
        outUsers = tuple(self.usedBy[0])
        oOut = self._outputs[0]
        for use in outUsers:
            use: HlsNetNodeIn
            use.disconnectFromHlsOut(oOut)
        oOut.name = None  # name would be misleading because now this output would be used for data to next stage

        clkPeriod = self.netlist.normalizedClkPeriod
        parent: ArchElement = self.parent
        isFirst = True
        prevRealization = None
        prevSchedZero = None
        for isLast, (r, schedZero, layerInputCnt, layerRange) in iter_with_last(self.splitOnClkWindowsClockWindowLayers(t0, layerTimes)):
            # for each layer if the begin is in next clock after previous layer
            # * set realization and scheduling to previous node
            # * add outputs to it
            # * construct next layer node without realization
            if isFirst:
                prevNode.operatorSpecialization = (props, layerRange)
                isFirst = False
                prevRealization = r
                prevSchedZero = schedZero
                continue

            assert len(prevNode._outputs) == 1, (prevNode, len(prevNode._outputs))
            # for _ in range(layerInputCnt - 1):
            #    prevNode._addOutput(stateT, None)

            if isLast:
                assert layerInputCnt == 1, self
                layerInputCnt += 1  # for final stateIn
                newNode = HlsNetNodeOperator(netlist, HwtOps.ADD, 0, stateT)
            else:
                newNode = self.__class__(netlist, OP_ADD_MASKED_FRAGMENT,
                                         0, stateT,
                                         operatorSpecialization=layerRange)
                newNode.operatorSpecialization = (props, layerRange)
            parent.addNode(newNode)  # add to parent so we can freely connect but the newNode is not yet
            # in specific clock window (it is added on yeld)
            # create connection to previous layer
            for i in range(layerInputCnt):
                if i == 0:
                    o = prevNode._outputs[0]
                else:
                    if isLast:
                        # instead out input1 use stateIn because this is the final add
                        assert i == 1, i
                        o = stateIn
                    else:
                        o = prevNode._addOutput(stateT, None)
                i = newNode._addInput(None)
                o.connectHlsIn(i)

            builder.registerOperatorNode(newNode)

            # the first layer is likely to have some offset, the delay is in delay
            # next layers always start at clock window begin, the dealy is out delay

            # schedule previous node
            prevNode.assignRealization(prevRealization)
            prevNode._setScheduleZeroTimeSingleClock(prevSchedZero)
            assert prevNode.scheduledZero >= 0, prevNode
            clkI = prevNode.scheduledZero // clkPeriod
            for iTime in prevNode.scheduledIn:
                assert iTime // clkPeriod == clkI, (iTime, clkI)
            for oTime in prevNode.scheduledIn:
                assert oTime // clkPeriod == clkI, (oTime, clkI)

            if prevNode is not self:
                # can not yeld self because it would duplicate self in the parent
                parent._addNodeIntoScheduled(prevNode.scheduledZero // clkPeriod, prevNode, allowNewClockWindow=True)
            # now prevNode is placed in parent based on scheduling

            prevNode = newNode
            prevRealization = r
            prevSchedZero = schedZero

        # connect top output and reoslve scheduling for last layer
        o = prevNode._addOutput(stateT, None)
        prevNode.assignRealization(prevRealization)
        prevNode._setScheduleZeroTimeSingleClock(prevSchedZero)
        for u in outUsers:
            u: HlsNetNodeIn
            o.connectHlsIn(u)
        return True


class AddMaskedComponentGenerator(ComponentGeneratorForHardBlock):

    def __init__(self, platform:DefaultHlsPlatform, genNamePrefix:str, moduleName:str):
        super().__init__(platform, genNamePrefix, moduleName)
        self.schedulingCache: dict[tuple[int, int, int],  # stateWidth, inputWidth, inputCnt
                                   (ComponentRealizationMeta, ComponentRealizationMeta, list[tuple[SchedTime, SchedTime, int]])
                                   # the list hold in, out time and number of inputs for each layer (relative to schedZero)
                                   ] = {}

    @staticmethod
    def _evalFn(resUndefVal: HBitsConst, stateIn: HBitsConst, dataIn: HBitsConst, maskIn: Optional[HBitsConst]) -> HBitsConst:
        if stateIn is not None and stateIn._is_full_valid():
            itemCnt = maskIn._dtype.bit_length()
            dataItemWidthWidth = dataIn._dtype.bit_length() // itemCnt
            res = stateIn
            # print("_evalFn", maskIn, dataIn, list(split_to_segments(dataIn, dataItemWidthWidth)))
            for d, m in zip(split_to_segments(dataIn, dataItemWidthWidth), maskIn):
                if not m._is_full_valid():
                    res = resUndefVal
                    break
                else:
                    if m:
                        if d._is_full_valid():
                            res = res + d
                        else:
                            res = resUndefVal
                            break
                    else:
                        break
        else:
            res = resUndefVal

        return res

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
                res = self._evalFn(resUndefVal, *(a if isConst else regs[a] for isConst, a in zip(inArgsIsConst, inArgs)))
            regs[dst] = res

        return _intrinsic_addMasked

    @override
    def _llvmMirToHlsNetlistBuildNode(self,
                                   mirToNetlist: HlsNetlistAnalysisPassMirToNetlist,
                                   instr: MachineInstr,
                                   ops: MirToHlsNetlistTranslatedInstrOpsT,
                                   pyObjectPlaceholder: HardBlockHwModule,
                                   builder: HlsNetlistBuilder,
                                   resTy: HBits,
                                   inputs: list[HlsNetNodeOutAny]
                                   ):
        op = pyObjectPlaceholder.getComponentGeneratorKey()
        assert isinstance(op, HOperatorDef), (pyObjectPlaceholder, op)
        res = builder.buildOp(op, None,
                              resTy, *inputs, operatorNodeCls=HlsNetNodeOperatorAddMasked)
        return res

    @override
    def resolveRealizationOfNode(self, node: HlsNetNode) -> ComponentRealizationMeta:
        """
        This generates a tree where first layer is composed of "&" to mask inputs, then there is a balanced tree
        to resolve the sum and thenfinal adder to add stateIn
        """
        netlist = node.netlist
        platform = self.platform
        (stateWidth, inputWidth, inputCnt) = node.getStateWidthInputWidthAndInputCnt()
        assert stateWidth >= inputWidth, (node, stateWidth, inputWidth)
        cacheKey = (stateWidth, inputWidth, inputCnt)
        try:
            return self.schedulingCache[cacheKey][1]
        except KeyError:
            pass

        realTimeClkPeriod:float = netlist.realTimeClkPeriod
        rInMask:OpRealizationMeta = platform.get_op_realization(HwtOps.AND, None, inputWidth, 2, realTimeClkPeriod)
        rAdd:OpRealizationMeta = platform.get_op_realization(HwtOps.ADD, None, inputWidth, 2, realTimeClkPeriod)
        r = rInMask

        clkPeriod: SchedTime = netlist.normalizedClkPeriod
        schedResolution:float = netlist.scheduler.resolution
        ffStoreTime: SchedTime = platform.get_ff_store_time(realTimeClkPeriod, schedResolution)
        clkTimeBudget: SchedTime = clkPeriod - ffStoreTime - netlist.scheduler.epsilon
        adderDelay = (rAdd.inputWireDelay + rAdd.outputWireDelay) // schedResolution
        if adderDelay > clkTimeBudget:
            raise TimeConstraintError(
                    "Impossible scheduling, scheduledZeroMin specifies >=", clkTimeBudget,
                    " but the best adder node can do is ", adderDelay, node)
        if not rAdd.fitsIntoSingleClockWindow():
            raise NotImplementedError()
        layerOutNormalizedTimes: list[tuple[SchedTime, SchedTime, int]] = [
            # layer 0 used for intial mask, rest for adders
            (SchedTime(0), SchedTime((r.inputWireDelay + r.outputWireDelay) // schedResolution), inputCnt)
        ]
        # print("layerOutNormalizedTimes", layerOutNormalizedTimes[0])

        beginTime = layerOutNormalizedTimes[0][1]
        layerInputCnt = inputCnt
        addTreeLayers = log2ceil(inputCnt)
        for _ in range(addTreeLayers + 1):  # +1 for final state adder
            rOut = r + rAdd
            if  rOut.fitsIntoSingleClockWindow():
                curTime = (rOut.inputWireDelay + rOut.outputWireDelay) // schedResolution
            else:
                curTime = rOut.outputClkTickOffset * clkPeriod + (rOut.outputWireDelay // schedResolution)
                assert rOut.inputClkTickOffset == 0

            if curTime > clkTimeBudget:
                if r.fitsIntoSingleClockWindow():
                    # addin next layer of adders would cross the clock boundary
                    rOut = r
                    rOut.inputWireDelay += r.outputWireDelay

                rOut.outputWireDelay = rAdd.inputWireDelay + rAdd.outputWireDelay
                rOut.outputClkTickOffset += 1
                beginTime = rOut.outputClkTickOffset * clkPeriod

            r = rOut
            if r.outputClkTickOffset == 0:
                endTime = SchedTime((r.inputWireDelay + r.outputWireDelay) // schedResolution)
                assert beginTime < endTime, (beginTime, endTime)
                assert beginTime // clkPeriod == endTime // clkPeriod
            else:
                endTime = SchedTime(r.outputClkTickOffset * clkPeriod + (r.outputWireDelay // schedResolution))
                assert beginTime < endTime, (beginTime, endTime)
                assert beginTime // clkPeriod == endTime // clkPeriod

            # print("layerOutNormalizedTimes", (beginTime, endTime, max(1, layerInputCnt)))
            layerOutNormalizedTimes.append((beginTime, endTime, max(1, layerInputCnt)))
            beginTime = endTime
            layerInputCnt //= 2

        r = ComponentRealizationMeta.fromOpRealization(r)
        assert r.inputWireDelay < realTimeClkPeriod, r
        assert r.outputWireDelay < realTimeClkPeriod, r
        self.schedulingCache[cacheKey] = (r, r, layerOutNormalizedTimes)
        return r

    @override
    def toRtlForNode(self, node: "HlsNetNode", allocator: "ArchElement") -> None:
        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        operands = []
        for (dep, t) in zip(node.dependsOn, node.scheduledIn):
            assert dep is not None, ("All inputs must be connected", node, node.dependsOn)
            _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, t)
            assert isinstance(_o, TimeIndependentRtlResourceItem), (dep, _o)
            operands.append(_o)

        props = node.getStateWidthInputWidthAndInputCnt()
        _, _, layerOutNormalizedTimes = self.schedulingCache[props]
        (stateWidth, inputWidth, inputCnt) = props
        assert stateWidth >= inputWidth, (node, stateWidth, inputWidth)
        t0 = min(node.scheduledIn)

        if node.operatorSpecialization is None or node.operatorSpecialization[1][0] == 0:
            if node.operatorSpecialization is None:
                dataIn = operands[1]
                maskIn = operands[2]
            else:
                # :note: stateIn is removed
                dataIn = operands[0]
                maskIn = operands[1]

            layerInputs: list[HBitsRtlSignal] = split_to_segments(dataIn.data, inputWidth)
            maskInputs: list[HBitsRtlSignal] = [m for m in maskIn.data]
            # construct input mask logic
            layerInputs = [m._sext(stateWidth) & i for i, m in zip(layerInputs, maskInputs)]
            t1 = t0 + layerOutNormalizedTimes[0][1]
            layerInputs: list[TimeIndependentRtlResource] = [allocator.rtlRegisterOutputRtlSignal(
                t1, v, False, False, False) for v in layerInputs]
        else:
            layerInputs: list[TimeIndependentRtlResource] = [op.parent for op in operands]

        if node.operatorSpecialization is None:
            selectedLayers = layerOutNormalizedTimes[1:-1]  # skip initila & mask layer
        else:
            _, layerRange = node.operatorSpecialization
            # the layer 0 is initia mask &, the last layer is final add which was extracted as separate node
            layerSliceStart = max(1, layerRange[0])
            layerSliceStop = min(layerRange[1], len(layerOutNormalizedTimes) - 1)
            selectedLayers = layerOutNormalizedTimes[layerSliceStart:layerSliceStop]
            if layerSliceStart != 1:
                t0 -= selectedLayers[0][0]  # substract the begin because this node begins after the original begin of items in layerOutNormalizedTimes
            # print("toRtlForNode", layerOutNormalizedTimes, "\n", layerRange, "\n", layerOutNormalizedTimes)

        # create "+" layer of adder tree
        for layerTimeBegin, layerTimeEnd, expectedLayerInputCnt in selectedLayers:
            assert inputCnt == 1 or inputCnt % 2 == 0, "[todo] this does not work if inputCnt is odd, there is a problem that expectedLayerInputCnt is not computed correctly (e.g. layerInputs=3, expectedLayerInputCnt=1 when it should be 2)"
            assert len(layerInputs) == expectedLayerInputCnt, (node, len(layerInputs), expectedLayerInputCnt)
            layerOutpus: list[TimeIndependentRtlResource] = []
            t = t0 + layerTimeBegin
            assert t > 0
            layerInputs: list[TimeIndependentRtlResourceItem] = [d.get(t) for d in layerInputs]
            t = t0 + layerTimeEnd
            for op0, op1 in grouper(2, layerInputs):
                if op1 is None:
                    # case for final sateIn adder
                    layerOutpus.append(op0.parent)
                else:
                    v = op0.data + op1.data
                    res = allocator.rtlRegisterOutputRtlSignal(
                        t, v, False, False, False)
                    layerOutpus.append(res)

            layerInputs = layerOutpus

        # register outputs
        assert len(layerInputs) == len(node._outputs), (node, layerInputs)
        if node.operatorSpecialization is None:
            assert len(node._outputs) == 1, node
            stateIn = operands[0]
            lastLayerNormalizedTimes = layerOutNormalizedTimes[-1]
            res = layerInputs[0].get(t0 + lastLayerNormalizedTimes[0]).data + stateIn.data
            res = allocator.rtlRegisterOutputRtlSignal(
                node._outputs[0],
                res, False, False, False)
        else:
            for o, oTime, oVal in zip(node._outputs, node.scheduledOut, layerInputs):
                allocator.rtlRegisterOutputRtlSignal(
                    o, oVal.get(oTime).data, False, False, False)
            res = []

        node._isRtlAllocated = True
        return res
