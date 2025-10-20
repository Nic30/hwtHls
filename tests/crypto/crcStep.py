
from math import ceil
from typing import Optional, Union

from hwt.hdl.commonConstants import b1
from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.frontend.hardBlock import HardBlockHwModule, \
    ComponentGeneratorForHardBlock
from hwtHls.llvm.llvmIr import  Function, Register, Instruction, \
    MachineInstr, MachineRegisterInfo, InstructionToCallInst, CallInst, HwtHlsInstCombinePass
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MirToHlsNetlistTranslatedInstrOpsT
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from hwtLib.logic.crc import Crc
from hwtLib.logic.crcComb import CrcComb
from hwtLib.logic.crcPoly import CRC_POLY
from hwtLib.logic.crc_test_utils import NaiveCrcAccumulator
from pyDigitalWaveTools.vcd.writer import VcdWriter


def _crcFnDoesNotUseLLVMOperator(*args):
    raise NotImplementedError()


OP_CRC_STEP = HOperatorDef(_crcFnDoesNotUseLLVMOperator, idStr="OP_CRC_STEP")


class CrcStepHardblock(HardBlockHwModule):
    """
    Function which takes data and CRC state and computes next CRC state value.
    :note: This is a HLS adapter for HDL implementation :class:`hwtLib.logic.crc.Crc`
    :note: to obtain final CRC value from state use :class:`CrcFinalizeHardblock`
    :ivar poly: polynomial to use for crc computation
    :ivar maxBytesProcessedInParallel: Maximum number of bytes of data to process
        in a single step, if specified this parameter limits the internal width of CRC computation
        circuit and optionally forces to use more CRC units in serial.
        This limits the code size and resource consumption in the cost of longer latency.
    """

    def __init__(self,
            poly: CRC_POLY,
            hwInputT: HBits,
            maxBytesProcessedInParallel: Optional[int]=None,
            name:Optional[str]=None,
            operationRealizationMeta:Optional[OpRealizationMeta]=None):
        self.poly = poly
        hwOutputT = HBits(poly.WIDTH)
        _hwInputT = HStruct(
            (hwOutputT, "state"),
            (hwInputT, "data"),
            (BIT, "mask"),
        )
        self.maxBytesProcessedInParallel = maxBytesProcessedInParallel
        HardBlockHwModule.__init__(self, _hwInputT, hwOutputT=hwOutputT, defaultKwargs={"mask": b1}, name=name,
                                   operationRealizationMeta=operationRealizationMeta)

    @override
    def getFnName(self):
        return (f"hwtHls.pyObjectPlaceholder.{self.placeholderObjectId:d}.crc"
                f".{self.poly.__name__:s}.i{self.hwInputT.field_by_name['data'].dtype.bit_length():d}")

    @override
    def _translateExprHConstHardBlockFunctionDef(self, toLlvm:"ToLlvmIrTranslator"):
        F:Function = HardBlockHwModule._translateExprHConstHardBlockFunctionDef(self, toLlvm)
        # F.addFnAttr(Attribute.AttrKind.Speculatable)
        strCtx = toLlvm.strCtx
        F.setMetadata(strCtx.addStringRef(HwtHlsInstCombinePass.metadataName_mergableFunction_statePlusMaskedData),
                      toLlvm.mdGetTuple([], False))
        platform = toLlvm.parentHwModule._target_platform
        if OP_CRC_STEP not in platform._componentGenerators:
            platform._componentGenerators[OP_CRC_STEP] = CrcStepComponentGenerator(platform, "gen", "crc")
        return F

    @override
    def getComponentGeneratorKey(self):
        return OP_CRC_STEP


class CrcStepComponentGenerator(ComponentGeneratorForHardBlock):
    """
    A generator which provides scheduling for CrcStepHardblock and
    provides info about how to translate it from netlist to RTL.
    """

    @staticmethod
    def _evalFn(resUndefVal: HBitsConst, crcAcc: NaiveCrcAccumulator, dataInWidth: int, stateIn: HBitsConst, dataIn: HBitsConst, maskIn:Optional[HBitsConst]) -> HBitsConst:
        if stateIn is None:
            raise
        if not stateIn._is_full_valid() or not maskIn._is_full_valid():
            res = resUndefVal
        else:
            crcAcc.value = int(stateIn)
            if int(maskIn) != maskIn._dtype.getAllOnesValue():
                off = 0
                nonEnabledByteSeen = False
                res = None
                for maskBit in maskIn:
                    if maskBit:
                        assert not nonEnabledByteSeen, ("mask 1 sequence has to be continuous", maskIn)
                        dataByte = dataIn[off + 8:off]
                        if dataByte._is_full_valid():
                            crcAcc.takeWord(int(dataByte), 8)
                        else:
                            res = resUndefVal
                            break
                    else:
                        nonEnabledByteSeen = True
                    off += 8
                if res is None:
                    res = resUndefVal._dtype.from_py(crcAcc.value)
            else:
                if dataIn._is_full_valid():
                    crcAcc.takeWord(int(dataIn), dataInWidth)
                    res = resUndefVal._dtype.from_py(crcAcc.value)
                else:
                    res = resUndefVal

        return res

    def llvmIrInterpretDecode(self, interpret: "LlvmIrInterpret", instr: Instruction,
                              pyObjectPlaceholder: CrcStepHardblock) -> LlvmIrInstrFunction:
        instr: CallInst = InstructionToCallInst(instr)
        assert instr
        crcAcc = NaiveCrcAccumulator(pyObjectPlaceholder.poly)
        # placeholderId, stateIn, data, mask
        assert instr.arg_size() == 4, instr
        ops = (instr.getArgOperand(1), instr.getArgOperand(2), instr.getArgOperand(3))

        ops = interpret._decodeInstArguments(ops)
        resTy = HBits(instr.getType().getIntegerBitWidth())
        resUndefVal = resTy.from_py(None)
        dataInWidth = instr.getArgOperand(2).getType().getIntegerBitWidth()

        def _intrinsic_crc_step(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]) -> LlvmIrInstrFunction:
            stateIn, dataIn, maskIn = interpret._prepareInstrArguments(ops, regs)
            res = self._evalFn(resUndefVal, crcAcc, dataInWidth, stateIn, dataIn, maskIn)
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _intrinsic_crc_step

    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI: MachineRegisterInfo, instr: MachineInstr,
                               pyObjectPlaceholder: CrcStepHardblock) -> LlvmMirInstrFunction:
        ops = interpret._decodeInstArguments(MRI, instr, instr.operands())[:-1]
        # dst, fnId, dstWidth, stateIn, dataIn, maskIn, stateInWidth, dataWidth, maskInWidth?
        dst, _, dstWidth, stateIn, dataIn, maskIn, _, dataInWidth, _ = ops
        stateInIsConst = isinstance(stateIn, HConst)
        dataInIsConst = isinstance(dataIn, HConst)
        maskInIsConst = isinstance(maskIn, HConst)
        cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)

        resTy = HBits(dstWidth)

        crcAcc = NaiveCrcAccumulator(pyObjectPlaceholder.poly)
        resUndefVal = resTy.from_py(None)

        def _intrinsic_crc_step(nowTime: int, regs: list[HConst]):
            if hasRuntimeCond and not regs[cond]:
                res = resUndefVal
            else:
                if stateInIsConst:
                    _stateIn = stateIn
                else:
                    _stateIn = regs[stateIn]

                if dataInIsConst:
                    _dataIn = dataIn
                else:
                    _dataIn = regs[dataIn]

                if maskInIsConst:
                    _maskIn = maskIn
                else:
                    _maskIn = regs[maskIn]

                res = self._evalFn(resUndefVal, crcAcc, dataInWidth, _stateIn, _dataIn, _maskIn)
            regs[dst] = res

        return _intrinsic_crc_step

    @override
    def llvmMirToHlsNetlist(self,
                            mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                            builder: "HlsNetlistBuilder",
                            mbMeta: "MachineBasicBlockMeta",
                            allBlockingLoadAck: Optional[HlsNetNodeOutAny],
                            name: Optional[str],
                            instr: MachineInstr,
                            dst: Union[Register, tuple[Register]],
                            ops: MirToHlsNetlistTranslatedInstrOpsT,
                            pyObjectPlaceholder: CrcStepHardblock) -> Optional[HlsNetNodeOutAny]:
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        inputs, cond = HardBlockHwModule._llvmMirToHlsNetlist_cutOfIdAndWidthFromOps(ops)
        argCnt = len(inputs)
        assert argCnt == 3, ("inputs in format state, dataIn, maskIn", inputs)
        stateNext = builder.buildOp(OP_CRC_STEP, (pyObjectPlaceholder.poly, pyObjectPlaceholder.maxBytesProcessedInParallel), inputs[0]._dtype, *inputs)

        # rhs = builder.buildConcat(HBits(state._dtype.bit_length() - i1._dtype.bit_length()).from_py(0), i1)
        stateNext.name = name
        opRealizationMeta = pyObjectPlaceholder.operationRealizationMeta
        if opRealizationMeta:
            stateNext.obj.assignRealization(opRealizationMeta)

        valCache.add(mbMeta.block, dst, stateNext, True)

        return allBlockingLoadAck

    @override
    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        argCnt = len(node.dependsOn)
        assert argCnt == 2 or argCnt == 3, node
        dataIn = node.dependsOn[1]
        # resolve how many logic layers are there from crc polynome and data width
        poly, maxBytesProcessedInParallel = node.operatorSpecialization
        poly: CRC_POLY
        polyBits, _ = CrcComb.parsePoly(poly.POLY, poly.WIDTH)
        BYTE_SIZE = 8
        inputDataWidth = dataIn._dtype.bit_length()
        if maxBytesProcessedInParallel is None:
            dataWidth = inputDataWidth
        else:
            dataWidth = min(inputDataWidth, maxBytesProcessedInParallel * BYTE_SIZE)
        crcMatrix = CrcComb.buildCrcXorMatrix(dataWidth, polyBits)
        # compute maximum number of xored bits in each bit of result
        maxExprTerm = 0
        for dataInRow, stateRow in zip(crcMatrix[0], crcMatrix[1]):
            maxExprTerm = max(maxExprTerm, sum(dataInRow) + sum(stateRow))

        netlist = node.netlist
        platform: VirtualHlsPlatform = netlist.parentHwModule._target_platform

        r = platform.get_op_realization(HwtOps.XOR, None, 1, maxExprTerm, netlist.realTimeClkPeriod)
        debugTracer = node.netlist.dbgSubmoduleBuidTracer
        debugTracer.log(("expecting maxXorTerms:", maxExprTerm))
        if maxBytesProcessedInParallel is not None and inputDataWidth > dataWidth:
            rounds = inputDataWidth / dataWidth
            r *= ceil(rounds)
            debugTracer.log(("expecting rounds:", rounds))

        if argCnt == 2:
            return r
        else:
            maskBits = node.dependsOn[2]._dtype.bit_length()
            muxR = platform.get_op_realization(HwtOps.TERNARY, None, poly.WIDTH, maskBits, netlist.realTimeClkPeriod)
            return r + muxR

    @override
    def toRtlForNode(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        operands = []
        for (dep, t) in zip(node.dependsOn, node.scheduledIn):
            assert dep is not None, ("All inputs must be connected", node, node.dependsOn)
            _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, t)
            assert isinstance(_o, TimeIndependentRtlResourceItem), (dep, _o)
            operands.append(_o)

        inputCnt = len(node.dependsOn)
        assert inputCnt == 3, node
        stateIn, dataIn, maskIn = operands
        maskIn = maskIn.data
        stateIn = stateIn.data
        dataIn = dataIn.data

        DATA_WIDTH = dataIn._dtype.bit_length()
        poly, maxBytesProcessedInParallel = node.operatorSpecialization
        poly: CRC_POLY
        assert stateIn._dtype.bit_length() == poly.WIDTH
        BYTE_WIDTH = 8
        # get number of bits processed by a single computation step
        if maxBytesProcessedInParallel is None:
            STEP_DATA_WIDTH = DATA_WIDTH
        else:
            STEP_DATA_WIDTH = maxBytesProcessedInParallel * BYTE_WIDTH
        if maxBytesProcessedInParallel is None:
            dataWidths = [DATA_WIDTH]
        else:
            DW = DATA_WIDTH
            dataWidths = []
            while DW > 0:
                dataWidths.append(min(DW, STEP_DATA_WIDTH))
                DW -= STEP_DATA_WIDTH

        maskBitOffset = 0
        netlist = node.netlist
        cb = AbstractComponentBuilder(netlist.parentHwModule, None, "gen")
        for DW in dataWidths:
            # create and configure instance of Crc
            m = Crc()
            m.setConfig(poly)
            m.CONTAINS_STATE_REG = False
            m.LATENCY = 0
            m.DATA_WIDTH = DW
            m.MASK_GRANULARITY = BYTE_WIDTH if maskIn else None

            name = cb._findSuitableName("Crc")
            setattr(cb.parent, name, m)

            # connect inputs of Crc instance
            m.stateIn(stateIn)
            m.dataIn.vld(1)
            dataBitOffset = maskBitOffset * BYTE_WIDTH
            m.dataIn.data(dataIn[dataBitOffset + DW:dataBitOffset])
            if maskIn is not None:
                m.dataIn.last(0)
                if DW == BYTE_WIDTH:
                    stateIn = maskIn[maskBitOffset]._ternary(m.dataOut._sig, stateIn)
                else:
                    m.dataIn.mask(maskIn[maskBitOffset + (STEP_DATA_WIDTH // BYTE_WIDTH): maskBitOffset])
                    stateIn = m.dataOut._sig
            else:
                stateIn = m.dataOut._sig

            maskBitOffset += STEP_DATA_WIDTH // BYTE_WIDTH

        # register output of Crc for others to connect
        assert len(node._outputs) == 1
        res = allocator.rtlRegisterOutputRtlSignal(
            node._outputs[0],
            stateIn, False, False, False)

        node._isRtlAllocated = True
        return res

