from operator import floordiv, mod
from typing import Optional, Union, Callable

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.llvm.llvmIr import MachineInstr, Register, MachineRegisterInfo
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.extraOps import OP_UDIVREM, OP_SDIVREM
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MirToHlsNetlistTranslatedInstrOpsT
from tests.math.componentGenerators._div.divRestoring import DivRemHwModule
from hwtHls.ssa.analysis.llvmMirInterpretInt import makeDecode_arithmeticBin
from hwtHls.ssa.analysis.llvmIrInterpretInt import _makeDecodeOpcodeFunction_BinaryOperator


def _floorsdiv(a: HBitsConst, b: HBitsConst):
    return (a._signed() // b._signed())._vec()


def _srem(a: HBitsConst, b: HBitsConst):
    return (a._signed() % b._signed())._vec()


class ComponentGeneratorDIVREM(ComponentGenerator):
    """
    :ivar optThroughputVsArea: optimization target specification, 0 means max resource savings, 1.0 means max throughput

    .. code-block:: text
        .. caption:: operands of div/rem like nodes

            %quotient, %remainder, %reqDone OP_UDIVREM/OP_SDIVREM %dividend %divisor %reqEn
            %quotient,             %reqDone UDIV/SDIV             %dividend %divisor %reqEn
                       %remainder, %reqDone UREM/SREM             %dividend %divisor %reqEn
    
    :note: reqEn/reqDone are not present in MIR
    """
    CHECK_FOR_INEFFICIENCY = True
    INT_DIV_HWMODULE_CLS = DivRemHwModule

    def __init__(self, platform: DefaultHlsPlatform,
                 genNamePrefix:str, moduleName:str,
                 isSigned:bool, hasDiv:bool, hasRem:bool,
                 optThroughputVsArea=0.0,):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth -> scheduling
        self.schedulingCache: dict[tuple[float, int], tuple[ComponentRealizationMeta, ComponentRealizationMeta, int]] = {}
        self._isSigned = isSigned
        self._hasDiv = hasDiv
        self._hasRem = hasRem
        self.optThroughputVsArea = optThroughputVsArea
        self._llvmMirInterpretDecodeFn = None
        assert hasDiv or hasRem
        evalFn: Optional[Callable[[int, int], Union[int, tuple[int, int]]]] = None
        if hasDiv:
            if isSigned:
                if hasRem:
                    opDef = OP_SDIVREM
                else:
                    evalFn = _floorsdiv
                    opDef = HwtOps.SDIV
            else:
                if hasRem:
                    opDef = OP_UDIVREM

                else:
                    evalFn = floordiv
                    opDef = HwtOps.UDIV
        else:
            assert hasRem
            if isSigned:
                opDef = HwtOps.SREM
                evalFn = _srem

            else:
                evalFn = mod
                opDef = HwtOps.UREM

        self.opDef = opDef

        if evalFn is not None:
            self.llvmIrInterpretDecode = _makeDecodeOpcodeFunction_BinaryOperator(evalFn)

    def getHlsNetlistInOutNames(self):
        IN_NAMES = ("dividend", "divisor", "reqEn")
        if self._hasDiv and self._hasRem:
            OUT_NAMES = ("quotient", "remainder", "reqDone")
        elif self._hasDiv:
            OUT_NAMES = ("quotient", "reqDone")
        else:
            assert self._hasRem
            OUT_NAMES = ("remainder", "reqDone")
        return IN_NAMES, OUT_NAMES

    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI:MachineRegisterInfo, instr:MachineInstr) -> LlvmMirInstrFunction:
        if self._hasDiv and self._hasRem:
            return self.llvmMirInterpretDecode_binaryOpBinResPredicated(interpret, MRI, instr)
        else:
            return self.llvmMirInterpretDecode_binaryOpPredicated(interpret, MRI, instr)

    def llvmMirInterpretDecode_binaryOpPredicated(self, interpret:"LlvmMirInterpret", MRI:MachineRegisterInfo, instr:MachineInstr) -> LlvmMirInstrFunction:
        try:
            dst, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, tuple(instr.operands())[:-1])
        except:
            raise AssertionError("Instruction operands in invalid format or this is not binary arithmetic instruction", instr)
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)
        cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)

        evalFn = self.opDef._evalFn

        def _opcode_arithmetic(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
                assert isinstance(src0, HConst), (instr, _src0, src0)
            if hasRuntimeCond and not regs[cond]:
                res = src0._dtype.from_py(None)
            else:
                if src1IsConst:
                    src1 = _src1
                else:
                    src1 = regs[_src1]
                    assert isinstance(src1, HConst), (instr, _src1, src1)

                if src0._dtype.signed is not None:
                    src0 = src0._cast_sign(None)
                if src1._dtype.signed is not None:
                    src1 = src1._cast_sign(None)
                try:
                    res = evalFn(src0, src1)
                except ZeroDivisionError:
                    res = src0._dtype.from_py(None)
            regs[dst] = res

        return _opcode_arithmetic

    def llvmMirInterpretDecode_binaryOpBinResPredicated(self, interpret: LlvmMirInterpret, MRI:MachineRegisterInfo, instr:MachineInstr) -> LlvmMirInstrFunction:
        dst0, dst1, _src0, _src1, _ = interpret._decodeInstArguments(MRI, instr, instr.operands())
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)
        cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)

        evalFn = self.opDef._evalFn

        def _opcode_arithmeticBinRes(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
            if hasRuntimeCond and not regs[cond]:
                res0 = src0._dtype.from_py(None)
                res1 = res0
            else:
                if src1IsConst:
                    src1 = _src1
                else:
                    src1 = regs[_src1]

                if src0._dtype.signed is not None:
                    src0 = src0._cast_sign(None)
                if src1._dtype.signed is not None:
                    src1 = src1._cast_sign(None)
                try:
                    res0, res1 = evalFn(src0, src1)
                except ZeroDivisionError:
                    res0 = src0._dtype.from_py(None)
                    res1 = res0

            regs[dst0] = res0
            regs[dst1] = res1

        return _opcode_arithmeticBinRes

    @override
    def llvmMirToHlsNetlist(self,
                            mirToNetlist: HlsNetlistAnalysisPassMirToNetlist,
                            builder: HlsNetlistBuilder,
                            mbMeta: MachineBasicBlockMeta,
                            allBlockingLoadAck: Optional[HlsNetNodeOutAny],
                            name: Optional[str],
                            instr: MachineInstr,
                            dst: Union[Register, tuple[Register]],
                            ops: MirToHlsNetlistTranslatedInstrOpsT) -> Optional[HlsNetNodeOutAny]:
        opSpecialization = None
        IN_NAMES, OUT_NAMES = self.getHlsNetlistInOutNames()
        r = self.resolveRealizationOfLlvmMirMachineInstr(mirToNetlist.MRI, builder.netlist, instr)
        enCond = ops[-1]
        ops = ops[:-1]
        return mirToNetlist._translateOperatorFromComponent(mirToNetlist, builder, mbMeta, allBlockingLoadAck, enCond, name, instr,
                                                            dst, ops, r, self.opDef, opSpecialization, IN_NAMES, OUT_NAMES)

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, DATA_WIDTH:int, UNROLL_FACTOR:int,
                               realization:Optional[ComponentRealizationMeta]):
        hwModule = self.INT_DIV_HWMODULE_CLS()
        hwModule.T = HBits(DATA_WIDTH, signed=self._isSigned)
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.UNROLL_FACTOR = UNROLL_FACTOR
        hwModule.CHECK_FOR_INEFFICIENCY = self.CHECK_FOR_INEFFICIENCY
        if realization:
            hwModule._setIoChannelTypes(realization)
        return hwModule

    @override
    def resolveRealizationOfLlvmMirMachineInstr(self, MRI: MachineRegisterInfo,
                                                netlist: "HlsNetlistCtx", instr: MachineInstr) -> ComponentRealizationMeta:
        dst0 = instr.getOperand(0)
        DATA_WIDTH = MRI.getType(dst0.getReg()).getScalarSizeInBits()
        operatorSpecialization = None
        return self.resolveRealizationForHlsNetlist(netlist, operatorSpecialization, DATA_WIDTH)

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> ComponentRealizationMeta:
        DATA_WIDTH = node.dependsOn[0]._dtype.bit_length()
        return self.resolveRealizationForHlsNetlist(node.netlist,
                                                    node.operatorSpecialization, DATA_WIDTH)

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx",
                                        operatorSpecialization, DATA_WIDTH: int) -> ComponentRealizationMeta:
        cacheKey = (DATA_WIDTH, self.optThroughputVsArea)
        try:
            return self.schedulingCache[cacheKey][1]
        except KeyError:
            pass

        UNROLL_FACTOR = int(DATA_WIDTH * self.optThroughputVsArea)
        if UNROLL_FACTOR == 0:
            UNROLL_FACTOR = 1  # 1 is a minimal value

        # run compilation of IntDiv HwModule to resolve scheduling properties
        intDivModule = self._getConfiguredHwModule(netlist.realTimeClkPeriod, DATA_WIDTH, UNROLL_FACTOR, None)
        _, _, rOutside = self.resolveRealizationOfNode_compileToResolveScheduling(
            netlist.parentHwModule, intDivModule,
            netlist.dbgSubmoduleBuidTracer, cacheKey, (UNROLL_FACTOR,))
        # raise NotImplementedError("[dbg]")
        return rOutside

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:HlsNetNode, worklist: SetList[HlsNetNode]) -> bool:
        """
        Lower to independent HwModule and read/write pairs because
        division contains internal sync logic and can not be easily inlined.
        """
        DATA_WIDTH = node.dependsOn[0]._dtype.bit_length()
        realizationInside, _, UNROLL_FACTOR = self.schedulingCache[(DATA_WIDTH, self.optThroughputVsArea)]
        hwModule = self._getConfiguredHwModule(node.netlist.realTimeClkPeriod, DATA_WIDTH, UNROLL_FACTOR, realizationInside)
        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)
        return True

    @override
    def toRtlForNode(self, node:HlsNetNode, allocator:ArchElement) -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperator", node, node._isMarkedRemoved)


class ComponentGeneratorDIVREM_G_opcodes(ComponentGeneratorDIVREM):
    """
    Variant for LLVM MIR/GISel Generic opcodes like G_UDIV,... this varinats do not have any predicate unline opcodes for :class:`ComponentGeneratorDIVREM`
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._hasDiv and self._hasRem:
            pass
        else:
            self.llvmMirInterpretDecode_binaryOp = _makeDecodeOpcodeFunction_BinaryOperator(self.opDef._evalFn)

    def llvmMirInterpretDecode_binaryOpBinRes(self, interpret: LlvmMirInterpret, MRI:MachineRegisterInfo, instr:MachineInstr) -> LlvmMirInstrFunction:
        dst0, dst1, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, instr.operands())
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)
        cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)

        evalFn = self.opDef._evalFn

        def _opcode_arithmeticBinRes(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
            if hasRuntimeCond and not regs[cond]:
                res0 = src0._dtype.from_py(None)
                res1 = res0
            else:
                if src1IsConst:
                    src1 = _src1
                else:
                    src1 = regs[_src1]

                if src0._dtype.signed is not None:
                    src0 = src0._cast_sign(None)
                if src1._dtype.signed is not None:
                    src1 = src1._cast_sign(None)
                try:
                    res0, res1 = evalFn(src0, src1)
                except ZeroDivisionError:
                    res0 = src0._dtype.from_py(None)
                    res1 = res0

            regs[dst0] = res0
            regs[dst1] = res1

        return _opcode_arithmeticBinRes

    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI:MachineRegisterInfo, instr:MachineInstr) -> LlvmMirInstrFunction:
        if self._hasDiv and self._hasRem:
            return self.llvmMirInterpretDecode_binaryOpBinRes(interpret, MRI, instr)
        else:
            return self.llvmMirInterpretDecode_binaryOp(interpret, MRI, instr)

