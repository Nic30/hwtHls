from typing import Optional

from hwt.hdl.operatorDefs import HwtOps
from hwtHls.llvm.llvmIr import TargetOpcode, CmpInst, Instruction, FCmpInst, Intrinsic, Type
from hwtHls.netlist.extraOps import OP_UDIVREM, OP_SDIVREM, OP_MUL_HL
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpretUtils import HwtHlsFpIntrisicName
from tests.math.componentGenerators.divrem import ComponentGeneratorDIVREM, \
    ComponentGeneratorDIVREM_G_opcodes
from tests.math.componentGenerators.fabs import ComponentGeneratorFABS, \
    ComponentGeneratorFABS_hwtHlsFpIntrinsic
from tests.math.componentGenerators.fadd import ComponentGeneratorFADD, \
    ComponentGeneratorFADD_hwtHlsFpIntrinsic
from tests.math.componentGenerators.fatan2 import ComponentGeneratorFATAN2HYPOT, \
    ComponentGeneratorFATAN2_hwtHlsFpIntrinsic, \
    ComponentGeneratorFATAN2_PI_hwtHlsFpIntrinsic, \
    ComponentGeneratorLlvmIntrinsicAtan2
from tests.math.componentGenerators.fcast import ComponentGeneratorFCAST, \
    ComponentGeneratorFCAST_hwtHlsFpIntrinsic_castFromHFloatTmp, \
    ComponentGeneratorFCAST_hwtHlsFpIntrinsic_castToHFloatTmp
from tests.math.componentGenerators.fcmp import ComponentGeneratorFCMP, \
    ComponentGeneratorFCMP_delegate, ComponentGeneratorFCMP_hwtHlsFpIntrinsic
from tests.math.componentGenerators.fdivrem import ComponentGeneratorFDIVREM, \
    ComponentGeneratorFDIV_hwtHlsFpIntrinsic, \
    ComponentGeneratorFREM_hwtHlsFpIntrinsic
from tests.math.componentGenerators.fexp import ComponentGeneratorFEXP, \
    ComponentGeneratorFEXP2, ComponentGeneratorFEXP10, \
    ComponentGeneratorFEXP_hwtHlsFpIntrinsic, \
    ComponentGeneratorFEXP2_hwtHlsFpIntrinsic, \
    ComponentGeneratorFEXP10_hwtHlsFpIntrinsic
from tests.math.componentGenerators.flog import ComponentGeneratorFLOG2
from tests.math.componentGenerators.flog import ComponentGeneratorFLOG_hwtHlsFpIntrinsic, \
    ComponentGeneratorFLOG2_hwtHlsFpIntrinsic, \
    ComponentGeneratorFLOG10_hwtHlsFpIntrinsic
from tests.math.componentGenerators.fmul import ComponentGeneratorFMUL, \
    ComponentGeneratorFMUL_hwtHlsFpIntrinsic
from tests.math.componentGenerators.fneg import ComponentGeneratorFNEG, \
    ComponentGeneratorFNEG_hwtHlsFpIntrinsic
from tests.math.componentGenerators.fpow import ComponentGeneratorFPOW, \
    ComponentGeneratorFPOW_hwtHlsFpIntrinsic
from tests.math.componentGenerators.fpowi import ComponentGeneratorFPOWI_hwtHlsFpIntrinsic, \
    ComponentGeneratorFPOWI
from tests.math.componentGenerators.fpshl import ComponentGeneratorFP_SHL, \
    ComponentGeneratorFP_SHL_UNSPECIALIZED
from tests.math.componentGenerators.fpshr import ComponentGeneratorFP_SHR, \
    ComponentGeneratorFP_SHR_UNSPECIALIZED
from tests.math.componentGenerators.fsincos import ComponentGeneratorFSINCOS, \
    ComponentGeneratorFSINCOS_PI, ComponentGeneratorFSIN_hwtHlsFpIntrinsic, \
    ComponentGeneratorFCOS_hwtHlsFpIntrinsic, \
    ComponentGeneratorFSINPI_hwtHlsFpIntrinsic, \
    ComponentGeneratorFCOSPI_hwtHlsFpIntrinsic
from tests.math.componentGenerators.fsqrt import ComponentGeneratorFSQRT, \
    ComponentGeneratorFSQRT_hwtHlsFpIntrinsic
from tests.math.componentGenerators.fsub import ComponentGeneratorFSUB, \
    ComponentGeneratorFSUB_hwtHlsFpIntrinsic
from tests.math.componentGenerators.ftan import ComponentGeneratorFTAN, \
    ComponentGeneratorFTANPI, ComponentGeneratorFTAN_hwtHlsFpIntrinsic, \
    ComponentGeneratorFTANPI_hwtHlsFpIntrinsic
from tests.math.componentGenerators.mul import ComponentGeneratorMUL
from tests.math.componentGenerators.mul_hl import ComponentGeneratorMUL_HL
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpCast import OP_CAST_HFLOATTMP_TO_HFLOATTMP
from tests.math.hFloatTmp.hFloatTmpOps import OP_FADD, OP_FSUB, OP_FMUL, \
    OP_FCMP_OEQ, OP_FCMP_OGT, OP_FCMP_OGE, OP_FCMP_OLT, OP_FCMP_OLE, OP_FCMP_ONE, \
    OP_FNEG, OP_FP_SHL, OP_FP_SHR, OP_FDIV, OP_FREM, OP_FSIN, OP_FCOS, OP_FSQRT, \
    OP_FSINCOS, OP_FLOG2, OP_FEXP, OP_FSINPI, OP_FCOSPI, OP_FSINCOSPI, OP_FTAN, \
    OP_FTANPI, OP_FEXP2, OP_FEXP10, OP_FPOW, OP_FATAN2, OP_FABS, OP_FPOWI


def installMathLibComponentGenerators(p: VirtualHlsPlatform, optThroughputVsArea=0.0, MAX_TABLE_ADDR_WIDTH=7, genNamePrefix="gen"):
    """
    
    
    :attention: Various libraries, frameworks, languages and hardware typically have imperfect precision of various math functions
        :see: Brian Gladman, Vincenzo Innocente, John Mather, Paul Zimmermann. Accuracy of Mathematical
        Functions in Single, Double, Double Extended, and Quadruple Precision. 2025. hal-03141101v8
        https://inria.hal.science/hal-03141101/document
        This function installs code generators which implements components with 0.5 ulp error if not configured otherwise.
        
        :see: See tests of each component for actual state,
        .. code-block::bash
            # you can use grep to find all components which do not have 0.5 ULP error
            grep -R "ULP *= *[1-9]"

    """
    g = p._componentGenerators

    def _getHFloatType(llvmTy: Optional[Type]=None) -> HFloatTmp:
        return HFloatTmp

    p._getHFloatType = _getHFloatType
    # _FP_UNARY_OPCODES = {
    #    TargetOpcode.HWTFPGA_FP_CEIL,
    #    HwtHlsFpIntrisicName("hwtHls.fp.ceil."): _decodeIntrinsic_fp_unOp(math.ceil),
    #    TargetOpcode.HWTFPGA_FP_FLOOR,
    #    TargetOpcode.HWTFPGA_FP_LOG,
    #    TargetOpcode.HWTFPGA_FP_LOG10,
    #    TargetOpcode.HWTFPGA_FP_ROUND,
    #    TargetOpcode.HWTFPGA_FP_ROUNDEVEN,
    #    TargetOpcode.HWTFPGA_FP_ASIN,
    #    TargetOpcode.HWTFPGA_FP_SINH,
    #    TargetOpcode.HWTFPGA_FP_ACOS,
    #    TargetOpcode.HWTFPGA_FP_COSH,
    #    TargetOpcode.HWTFPGA_FP_ATAN,
    #    TargetOpcode.HWTFPGA_FP_TANH,
    # }
    # _FP_BIN_OPCODES = {
    #    TargetOpcode.HWTFPGA_FP_FMOD,
    # }

    # HwtHlsFpIntrisicName("hwtHls.fp.floor."): _decodeIntrinsic_fp_unOp(math.floor),
    # HwtHlsFpIntrisicName("hwtHls.fp.round."): _decodeIntrinsic_fp_unOp(round),
    # HwtHlsFpIntrisicName("hwthls.fp.roundeven."):  _decodeIntrinsic_fp_unOp(roundeven),

    # g[HwtOps.MUL] = ComponentGeneratorMUL(p, np, "mul")
    # g[OP_MUL_HL] = ComponentGeneratorMUL_HL(p, np, "mul_hl")
    T = TargetOpcode
    np = genNamePrefix
    BinaryOps = Instruction.BinaryOps
    g[T.G_UDIV] = ComponentGeneratorDIVREM_G_opcodes(p, np, "udiv", False, True, False)
    g[T.G_SDIV] = ComponentGeneratorDIVREM_G_opcodes(p, np, "sdiv", True, True, False)
    g[T.G_UREM] = ComponentGeneratorDIVREM_G_opcodes(p, np, "urem", False, False, True)
    g[T.G_SREM] = ComponentGeneratorDIVREM_G_opcodes(p, np, "srem", True, False, True)
    g[T.G_UDIVREM] = ComponentGeneratorDIVREM_G_opcodes(p, np, "udivrem", False, True, True)
    g[T.G_SDIVREM] = ComponentGeneratorDIVREM_G_opcodes(p, np, "sdivrem", True, True, True)

    g[BinaryOps.UDiv] = g[T.HWTFPGA_UDIV] = g[HwtOps.UDIV] = ComponentGeneratorDIVREM(p, np, "udiv", False, True, False)
    g[BinaryOps.SDiv] = g[T.HWTFPGA_SDIV] = g[HwtOps.SDIV] = ComponentGeneratorDIVREM(p, np, "sdiv", True, True, False)
    g[BinaryOps.URem] = g[T.HWTFPGA_UREM] = g[HwtOps.UREM] = ComponentGeneratorDIVREM(p, np, "urem", False, False, True)
    g[BinaryOps.SRem] = g[T.HWTFPGA_SREM] = g[HwtOps.SREM] = ComponentGeneratorDIVREM(p, np, "srem", True, False, True)
    g[T.HWTFPGA_UDIVREM] = g[OP_UDIVREM] = ComponentGeneratorDIVREM(p, np, "udivrem", False, True, True)
    g[T.HWTFPGA_SDIVREM] = g[OP_SDIVREM] = ComponentGeneratorDIVREM(p, np, "sdivrem", True, True, True)

    g[HwtHlsFpIntrisicName("hwtHls.fp.castToHFloatTmp.")] = ComponentGeneratorFCAST_hwtHlsFpIntrinsic_castToHFloatTmp(p, np, "fcast")
    g[HwtHlsFpIntrisicName("hwtHls.fp.castFromHFloatTmp.")] = ComponentGeneratorFCAST_hwtHlsFpIntrinsic_castFromHFloatTmp(p, np, "fcast")
    g[T.HWTFPGA_FP_CAST] = g[OP_CAST_HFLOATTMP_TO_HFLOATTMP] = ComponentGeneratorFCAST(p, np, "fcast")

    g[Instruction.UnaryOps.FNeg] = g[T.HWTFPGA_FP_FNEG] = g[OP_FNEG] = ComponentGeneratorFNEG(p, np, "fneg")
    g[HwtHlsFpIntrisicName("hwtHls.fp.fneg.")] = ComponentGeneratorFNEG_hwtHlsFpIntrinsic(p, np, "fneg")
    g[BinaryOps.FAdd] = g[T.HWTFPGA_FP_FADD] = g[OP_FADD] = ComponentGeneratorFADD(p, np, "fadd")
    g[HwtHlsFpIntrisicName("hwtHls.fp.fadd.")] = ComponentGeneratorFADD_hwtHlsFpIntrinsic(p, np, "fadd")
    g[BinaryOps.FSub] = g[T.HWTFPGA_FP_FSUB] = g[OP_FSUB] = ComponentGeneratorFSUB(p, np, "fsub")
    g[HwtHlsFpIntrisicName("hwtHls.fp.fsub.")] = ComponentGeneratorFSUB_hwtHlsFpIntrinsic(p, np, "fsub")
    g[T.HWTFPGA_FP_FABS] = g[OP_FABS] = ComponentGeneratorFABS(p, np, "fabs")
    g[HwtHlsFpIntrisicName("hwtHls.fp.fabs.")] = ComponentGeneratorFABS_hwtHlsFpIntrinsic(p, np, "fabs")
    g[BinaryOps.FMul] = g[T.HWTFPGA_FP_FMUL] = g[OP_FMUL] = ComponentGeneratorFMUL(p, np, "fmul")
    g[HwtHlsFpIntrisicName("hwtHls.fp.fmul.")] = ComponentGeneratorFMUL_hwtHlsFpIntrinsic(p, np, "fmul")
    g[BinaryOps.FDiv] = g[T.HWTFPGA_FP_FDIV] = g[OP_FDIV] = ComponentGeneratorFDIVREM(p, np, "fdiv", True, False, optThroughputVsArea=optThroughputVsArea)
    g[HwtHlsFpIntrisicName("hwtHls.fp.fdiv.")] = ComponentGeneratorFDIV_hwtHlsFpIntrinsic(p, np, "fdiv")
    g[T.HWTFPGA_FP_FREM] = g[OP_FREM] = ComponentGeneratorFDIVREM(p, np, "frem", False, True, optThroughputVsArea=optThroughputVsArea)
    g[HwtHlsFpIntrisicName("hwtHls.fp.frem.")] = ComponentGeneratorFREM_hwtHlsFpIntrinsic(p, np, "frem")
    # g[] = g[OP_FDIVREM] = ComponentGeneratorFDIVREM(p, True, True, np, "fdivrem", optThroughputVsArea=optThroughputVsArea)
    g[T.HWTFPGA_FP_SQRT] = g[OP_FSQRT] = ComponentGeneratorFSQRT(p, np, "fsqrt", optThroughputVsArea=optThroughputVsArea)
    g[HwtHlsFpIntrisicName("hwtHls.fp.sqrt.")] = ComponentGeneratorFSQRT_hwtHlsFpIntrinsic(p, np, "fsqrt")

    g[HwtHlsFpIntrisicName("hwtHls.fp.shl.")] = g[T.HWTFPGA_FP_SHL] = g[OP_FP_SHL] = ComponentGeneratorFP_SHL(p, np, "fpshl")
    g[HwtHlsFpIntrisicName("hwtHls.fp.unspecialized.shl.")] = ComponentGeneratorFP_SHL_UNSPECIALIZED(p, np, "fpshl")
    g[HwtHlsFpIntrisicName("hwtHls.fp.shr.")] = g[T.HWTFPGA_FP_SHR] = g[OP_FP_SHR] = ComponentGeneratorFP_SHR(p, np, "fpshr")
    g[HwtHlsFpIntrisicName("hwtHls.fp.unspecialized.shr.")] = ComponentGeneratorFP_SHR_UNSPECIALIZED(p, np, "fpshr")
    g[Instruction.OtherOps.FCmp] = g[T.HWTFPGA_FP_FCMP] = ComponentGeneratorFCMP_delegate(p, np, "fcmp")
    g[HwtHlsFpIntrisicName("hwtHls.fp.fcmp.")] = ComponentGeneratorFCMP_hwtHlsFpIntrinsic(p, np, "fcmp")
    P = CmpInst.Predicate
    g[(FCmpInst, P.FCMP_OEQ)] = g[(T.HWTFPGA_FP_FCMP, P.FCMP_OEQ)] = g[OP_FCMP_OEQ] = ComponentGeneratorFCMP(p, np, "fcmp_oeq", HwtOps.EQ, HwtOps.EQ)
    g[(FCmpInst, P.FCMP_OGT)] = g[(T.HWTFPGA_FP_FCMP, P.FCMP_OGT)] = g[OP_FCMP_OGT] = ComponentGeneratorFCMP(p, np, "fcmp_ogt", HwtOps.UGT, HwtOps.SGT)
    g[(FCmpInst, P.FCMP_OGE)] = g[(T.HWTFPGA_FP_FCMP, P.FCMP_OGE)] = g[OP_FCMP_OGE] = ComponentGeneratorFCMP(p, np, "fcmp_oge", HwtOps.UGE, HwtOps.SGE)
    g[(FCmpInst, P.FCMP_OLT)] = g[(T.HWTFPGA_FP_FCMP, P.FCMP_OLT)] = g[OP_FCMP_OLT] = ComponentGeneratorFCMP(p, np, "fcmp_olt", HwtOps.ULT, HwtOps.SLT)
    g[(FCmpInst, P.FCMP_OLE)] = g[(T.HWTFPGA_FP_FCMP, P.FCMP_OLE)] = g[OP_FCMP_OLE] = ComponentGeneratorFCMP(p, np, "fcmp_ole", HwtOps.ULE, HwtOps.SLE)
    g[(FCmpInst, P.FCMP_ONE)] = g[(T.HWTFPGA_FP_FCMP, P.FCMP_ONE)] = g[OP_FCMP_ONE] = ComponentGeneratorFCMP(p, np, "fcmp_one", HwtOps.NE, HwtOps.NE)

    g[T.HWTFPGA_FP_SIN] = g[OP_FSIN] = ComponentGeneratorFSINCOS(p, np, "fsin", False, True, optThroughputVsArea=optThroughputVsArea, optMaxStagesInLut=MAX_TABLE_ADDR_WIDTH)
    g[HwtHlsFpIntrisicName("hwtHls.fp.sin.")] = ComponentGeneratorFSIN_hwtHlsFpIntrinsic(p, np, "fsin")
    g[T.HWTFPGA_FP_COS] = g[OP_FCOS] = ComponentGeneratorFSINCOS(p, np, "fcos", True, False, optThroughputVsArea=optThroughputVsArea, optMaxStagesInLut=MAX_TABLE_ADDR_WIDTH)
    g[HwtHlsFpIntrisicName("hwtHls.fp.cos.")] = ComponentGeneratorFCOS_hwtHlsFpIntrinsic(p, np, "fcos")
    g[T.HWTFPGA_FP_TAN] = g[OP_FTAN] = ComponentGeneratorFTAN(p, np, "ftan")
    g[HwtHlsFpIntrisicName("hwtHls.fp.tan.")] = ComponentGeneratorFTAN_hwtHlsFpIntrinsic(p, np, "ftan")
    g[T.HWTFPGA_FP_TANPI] = g[OP_FTANPI] = ComponentGeneratorFTANPI(p, np, "ftanpi")
    g[HwtHlsFpIntrisicName("hwtHls.fp.tanpi.")] = ComponentGeneratorFTANPI_hwtHlsFpIntrinsic(p, np, "ftanpi")
    g[T.HWTFPGA_FP_SINPI] = g[OP_FSINPI] = ComponentGeneratorFSINCOS_PI(p, np, "fsinpi", False, True, optThroughputVsArea=optThroughputVsArea, optMaxStagesInLut=MAX_TABLE_ADDR_WIDTH)
    g[HwtHlsFpIntrisicName("hwtHls.fp.sinpi.")] = ComponentGeneratorFSINPI_hwtHlsFpIntrinsic(p, np, "fsinpi")
    g[T.HWTFPGA_FP_COSPI] = g[OP_FCOSPI] = ComponentGeneratorFSINCOS_PI(p, np, "fcospi", True, False, optThroughputVsArea=optThroughputVsArea, optMaxStagesInLut=MAX_TABLE_ADDR_WIDTH)
    g[HwtHlsFpIntrisicName("hwtHls.fp.cospi.")] = ComponentGeneratorFCOSPI_hwtHlsFpIntrinsic(p, np, "fcospi")
    g[T.HWTFPGA_FP_SINCOS] = g[OP_FSINCOS] = ComponentGeneratorFSINCOS(p, np, "fsincos", True, True, optThroughputVsArea=optThroughputVsArea, optMaxStagesInLut=MAX_TABLE_ADDR_WIDTH)
    g[T.HWTFPGA_FP_SINCOSPI] = g[OP_FSINCOSPI] = ComponentGeneratorFSINCOS_PI(p, np, "fsincospi", True, True, optThroughputVsArea=optThroughputVsArea, optMaxStagesInLut=MAX_TABLE_ADDR_WIDTH)
    g[Intrinsic.atan2] = ComponentGeneratorLlvmIntrinsicAtan2(p, np, "fatan2")
    g[T.HWTFPGA_FP_ATAN2] = g[OP_FATAN2] = ComponentGeneratorFATAN2HYPOT(p, np, "fatan2", True, False, optThroughputVsArea=optThroughputVsArea)
    g[HwtHlsFpIntrisicName("hwtHls.fp.atan2.")] = ComponentGeneratorFATAN2_hwtHlsFpIntrinsic(p, np, "fatan2")
    g[HwtHlsFpIntrisicName("hwtHls.fp.atan2pi.")] = ComponentGeneratorFATAN2_PI_hwtHlsFpIntrinsic(p, np, "fatan2pi")

    g[HwtHlsFpIntrisicName("hwtHls.fp.log.")] = ComponentGeneratorFLOG_hwtHlsFpIntrinsic(p, np, "flog")
    g[T.HWTFPGA_FP_LOG2] = g[OP_FLOG2] = ComponentGeneratorFLOG2(p, np, "flog2", MAX_TABLE_ADDR_WIDTH)
    g[HwtHlsFpIntrisicName("hwtHls.fp.log2.")] = ComponentGeneratorFLOG2_hwtHlsFpIntrinsic(p, np, "flog2")
    g[HwtHlsFpIntrisicName("hwtHls.fp.log10.")] = ComponentGeneratorFLOG10_hwtHlsFpIntrinsic(p, np, "flog10")
    g[T.HWTFPGA_FP_EXP] = g[OP_FEXP] = ComponentGeneratorFEXP(p, np, "fexp", MAX_TABLE_ADDR_WIDTH)
    g[HwtHlsFpIntrisicName("hwtHls.fp.exp.")] = ComponentGeneratorFEXP_hwtHlsFpIntrinsic(p, np, "fexp")
    g[T.HWTFPGA_FP_EXP2] = g[OP_FEXP2] = ComponentGeneratorFEXP2(p, np, "fexp2", MAX_TABLE_ADDR_WIDTH)
    g[HwtHlsFpIntrisicName("hwtHls.fp.exp2.")] = ComponentGeneratorFEXP2_hwtHlsFpIntrinsic(p, np, "fexp2")
    g[T.HWTFPGA_FP_EXP10] = g[OP_FEXP10] = ComponentGeneratorFEXP10(p, np, "fexp10", MAX_TABLE_ADDR_WIDTH)
    g[HwtHlsFpIntrisicName("hwtHls.fp.exp10.")] = ComponentGeneratorFEXP10_hwtHlsFpIntrinsic(p, np, "fexp10")
    g[Intrinsic.pow] = g[T.HWTFPGA_FP_FPOW] = g[OP_FPOW] = ComponentGeneratorFPOW(p, np, "fpow")
    g[HwtHlsFpIntrisicName("hwtHls.fp.fpow.")] = ComponentGeneratorFPOW_hwtHlsFpIntrinsic(p, np, "fpow")
    g[Intrinsic.powi] = g[T.HWTFPGA_FP_FPOWI] = g[OP_FPOWI] = ComponentGeneratorFPOWI(p, np, "fpowi")
    g[HwtHlsFpIntrisicName("hwtHls.fp.fpowi.")] = ComponentGeneratorFPOWI_hwtHlsFpIntrinsic(p, np, "fpowi")
