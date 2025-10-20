import math

from hwt.hdl.operatorDefs import HOperatorDef
from hwt.pyUtils.typingFuture import override
from hwtHls.llvm.llvmIr import TargetOpcode, MachineRegisterInfo, MachineInstr
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForUnSpecializedHwtHlsFpIntrinsicBinary_FloatInt, \
    ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatInt
from tests.math.hFloatTmp.hFloatTmpOps import fpowi, OP_FPOWI


class ComponentGeneratorFPOWI_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatInt):

    @override
    @staticmethod
    def evalFn(v: float, sh:int) -> float:
        return math.pow(v, sh)


class ComponentGeneratorFPOWI(ComponentGeneratorFp):

    INPUT_CNT = 2
    opDef: HOperatorDef = OP_FPOWI

    llvmIrInterpretDecode = ComponentGeneratorForUnSpecializedHwtHlsFpIntrinsicBinary_FloatInt.llvmIrInterpretDecode

    @staticmethod
    def evalFn(v: float, sh:int) -> float:
        return fpowi(v, sh)

    def llvmMirInterpretDecode(self, interpret:"LlvmMirInterpret", MRI:MachineRegisterInfo, instr:MachineInstr) -> LlvmMirInstrFunction:
        return ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatInt.llvmMirInterpretDecode(
            self, interpret, MRI, instr,
            hsIsSigned=instr.getOpcode() == TargetOpcode.G_FPOWI)

