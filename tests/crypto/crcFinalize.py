
from typing import Optional, Union

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.hardBlock import HardBlockHwModule, \
    ComponentGeneratorForHardBlock
from hwtHls.llvm.llvmIr import Attribute, Function, Register, Instruction, \
    MachineInstr, MachineRegisterInfo, InstructionToCallInst, CallInst
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MirToHlsNetlistTranslatedInstrOpsT
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtLib.logic.crcPoly import CRC_POLY
from hwtLib.logic.crc_test_utils import NaiveCrcAccumulator
from pyDigitalWaveTools.vcd.writer import VcdWriter
from pyMathBitPrecise.bit_utils import reverse_bits
from tests.crypto.crcStep import _crcFnDoesNotUseLLVMOperator


OP_CRC_FINALIZE = HOperatorDef(_crcFnDoesNotUseLLVMOperator, idStr="OP_CRC_FINALIZE")


class CrcFinalizeHardblock(HardBlockHwModule):
    """
    Function which converts intermediate state to a final CRC value
    (it applies REFOUT and XOROUT of CRC_POLY)
    """

    def __init__(self,
        poly: CRC_POLY,
        name:Optional[str]=None,
        operationRealizationMeta:Optional[OpRealizationMeta]=None):
        self.poly = poly
        T = HBits(poly.WIDTH)
        HardBlockHwModule.__init__(self, T, T, name=name,
                                   operationRealizationMeta=operationRealizationMeta)

    @override
    def _translateExprHConstHardBlockFunctionDef(self, toLlvm:ToLlvmIrTranslator):
        F:Function = HardBlockHwModule._translateExprHConstHardBlockFunctionDef(self, toLlvm)
        F.addFnAttr(Attribute.AttrKind.Speculatable)
        platform = toLlvm.parentHwModule._target_platform
        if OP_CRC_FINALIZE not in platform._componentGenerators:
            platform._componentGenerators[OP_CRC_FINALIZE] = CrcFinalizeComponentGenerator(platform, "gen", "crcFin")
        return F

    def getComponentGeneratorKey(self):
        return OP_CRC_FINALIZE


class CrcFinalizeComponentGenerator(ComponentGeneratorForHardBlock):

    @staticmethod
    def _evalFn(resUndefVal: HBitsConst, crcAcc: NaiveCrcAccumulator, stateIn: HBitsConst) -> HBitsConst:
        if stateIn is not None and stateIn._is_full_valid():
            crcAcc.value = int(stateIn)
            res = resUndefVal._dtype.from_py(crcAcc.getFinalValue())
        else:
            res = resUndefVal
        return res

    @override
    def llvmIrInterpretDecode(self, interpret: LlvmIrInterpret, instr: Instruction,
                              pyObjectPlaceholder: CrcFinalizeHardblock) -> LlvmIrInstrFunction:
        instr: CallInst = InstructionToCallInst(instr)
        assert instr
        crcAcc = NaiveCrcAccumulator(pyObjectPlaceholder.poly)
        # placeholderId, stateIn
        ops = interpret._decodeInstArguments((instr.getArgOperand(1),))
        resTy = HBits(instr.getType().getIntegerBitWidth())
        resUndefVal = resTy.from_py(None)

        def _intrinsic_crc_step(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]) -> LlvmIrInstrFunction:
            stateIn, = interpret._prepareInstrArguments(ops, regs)
            res = self._evalFn(resUndefVal, crcAcc, stateIn)
            interpret._storeInstrResult(waveLog, nowTime, regs, instr, res)

        return _intrinsic_crc_step

    @override
    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI: MachineRegisterInfo, instr: MachineInstr,
                               pyObjectPlaceholder: CrcFinalizeHardblock) -> LlvmMirInstrFunction:
        dst, _, dstWidth, src, _ = interpret._decodeInstArguments(MRI, instr, instr.operands())[:-1]
        cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)

        resTy = HBits(dstWidth)
        srcIsConst = isinstance(src, HConst)
        crcAcc = NaiveCrcAccumulator(pyObjectPlaceholder.poly)
        resUndefVal = resTy.from_py(None)

        def _intrinsic_crc_finalize(nowTime: int, regs: list[HConst]):
            if hasRuntimeCond and not regs[cond]:
                res = resUndefVal
            else:
                if srcIsConst:
                    _src = src
                else:
                    _src = regs[src]

                res = self._evalFn(resUndefVal, crcAcc, _src)
            regs[dst] = res

        return _intrinsic_crc_finalize

    @override
    def llvmMirToHlsNetlist(self,
                            mirToNetlist: HlsNetlistAnalysisPassMirToNetlist,
                            builder: HlsNetlistBuilder,
                            mbMeta: MachineBasicBlockMeta,
                            allBlockingLoadAck: Optional[HlsNetNodeOutAny],
                            name: Optional[str],
                            instr: MachineInstr,
                            dst: Union[Register, tuple[Register]],
                            ops: MirToHlsNetlistTranslatedInstrOpsT,
                            pyObjectPlaceholder: CrcFinalizeHardblock) -> Optional[HlsNetNodeOutAny]:
        """
        :see: based on :meth:`hwtLib.logic.crc.Crc._aply_REFOUT_and_XOROUT`
        """
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        inputs, _ = HardBlockHwModule._llvmMirToHlsNetlist_cutOfIdAndWidthFromOps(ops)
        assert len(inputs) == 1, inputs
        poly = pyObjectPlaceholder.poly
        XOROUT:int = poly.XOROUT
        REFOUT:bool = poly.REFOUT
        res = inputs[0]

        # if XOROUT == 0 and REFOUT:
        #    pass
        # else:
        if REFOUT:
            res = builder.buildBitReverse(res)

        if XOROUT != 0:
            # reverse bit order in XOROUT
            XOROUT = reverse_bits(XOROUT, poly.WIDTH)
            res = builder.buildXor(res, builder.buildConstPy(res._dtype, XOROUT), name=name)

        valCache.add(mbMeta.block, dst, res, True)
        return allBlockingLoadAck
