
import math
from typing import Optional

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpretInt import _makeDecodeOpcodeFunction_BinaryOperator
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.componentGenerators._genericHwModules import _FpAlu2HwModule
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat
from tests.math.componentGenerators.divrem import ComponentGeneratorDIVREM
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp.fixpdivrem import FixpDivRemHwModule
from tests.math.fp.fpdiv import IEEE754FpDiv, _IEEE754FpDiv_getInternDivTy
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.hFloatTmp.hFloatTmpOps import OP_FDIV, OP_FREM
from tests.math.hFloatTmp.hFloatTmpUtils import HFloatTmpConfigToHType
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps


class ComponentGeneratorFDIV_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat):

    @override
    @staticmethod
    def evalFn(a: float, b: float) -> float:
        return a / b


class ComponentGeneratorFREM_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat):

    @override
    @staticmethod
    def evalFn(a: float, b: float) -> float:
        return math.remainder(a, b)


@serializeParamsUniq
class FpDivHwModule(_FpAlu2HwModule):
    CHECK_UNROLL_FACTOR = False
    FN = staticmethod(IEEE754FpDiv)

    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True, inputArgsAreStructMembers=True)
    def model(a: float, b: float) -> float:
        return a / b

    def _getMaxIterationCount(self):
        return self._getMaxIterationCountForTy(self.T)

    @classmethod
    def _getMaxIterationCountForTy(self, ty: IEEE754Fp):
        mantisaFixPTy = _IEEE754FpDiv_getInternDivTy(ty)
        return FixpDivRemHwModule._getMaxIterationCountForTy(mantisaFixPTy)


class ComponentGeneratorFDIVREM(ComponentGeneratorFp):
    INPUT_CNT = 2
    FIXP_HWMODULE_CLS = FixpDivRemHwModule
    FP_HWMODULE_CLS = FpDivHwModule

    def __init__(self, platform:DefaultHlsPlatform,
                 genNamePrefix:str, moduleName:str,
                 hasDiv:bool, hasRem:bool,
                 optThroughputVsArea=0.0):
        ComponentGeneratorFp.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth (optThroughputVsArea, HFloatTmpConfig) -> scheduling (OpRealizationMeta, UNROLL_FACTOR)
        self._hasDiv = hasDiv
        self._hasRem = hasRem
        self.optThroughputVsArea = optThroughputVsArea

        if hasDiv and hasRem:
            raise NotImplementedError()
        elif hasDiv:
            op = OP_FDIV
            # evalFn = truediv
        elif hasRem:
            op = OP_FREM
            # evalFn = math.remainder
        else:
            raise AssertionError()

        self.opDef = op
        self.llvmIrInterpretDecode = _makeDecodeOpcodeFunction_BinaryOperator(op._evalFn)

    @override
    def llvmMirToHlsNetlist(self, *args) -> Optional[HlsNetNodeOutAny]:
        IN_NAMES, OUT_NAMES = ComponentGeneratorDIVREM.getHlsNetlistInOutNames(self)
        return super().llvmMirToHlsNetlist(*args, IN_NAMES, OUT_NAMES)

    def _getConfiguredFixpHwModule(self, realTimeClkPeriod:float, ty:HFixedPointQ, UNROLL_FACTOR:int, realization:OpRealizationMeta):
        hwModule = self.FIXP_HWMODULE_CLS()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.UNROLL_FACTOR = UNROLL_FACTOR
        hwModule.HAS_DIV = self._hasDiv
        hwModule.HAS_REM = self._hasRem
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    def _getConfiguredFpHwModule(self, realTimeClkPeriod:float, ty:HFixedPointQ, UNROLL_FACTOR:int, realization:OpRealizationMeta):
        if self._hasRem:
            raise NotImplementedError()
        if not self._hasDiv:
            raise NotImplementedError()

        hwModule = FpDivHwModule()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.UNROLL_FACTOR = UNROLL_FACTOR
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    @override
    def resolveRealizationForHlsNetlist(self, netlist: HlsNetlistCtx, cfg: HFloatTmpConfig) -> None:
        cacheKey = (cfg, self.optThroughputVsArea)
        try:
            return self.schedulingCache[cacheKey][1]
        except KeyError:
            pass

        ty = HFloatTmpConfigToHType(cfg)
        if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
            raise NotImplementedError()

        if self.optThroughputVsArea == 0:
            UNROLL_FACTOR = 1
        elif self.optThroughputVsArea == 1.0:
            if cfg.isInQFormat:
                UNROLL_FACTOR = self.FIXP_HWMODULE_CLS._getMaxIterationCountForTy(ty)
            else:
                UNROLL_FACTOR = self.FP_HWMODULE_CLS._getMaxIterationCountForTy(ty)

        else:
            raise NotImplementedError(self, self.optThroughputVsArea)

        # run compilation of HwModule to resolve scheduling properties
        if cfg.isInQFormat:
            hwModule = self._getConfiguredFixpHwModule(netlist.realTimeClkPeriod, ty, UNROLL_FACTOR, None)
        else:
            hwModule = self._getConfiguredFpHwModule(netlist.realTimeClkPeriod, ty, UNROLL_FACTOR, None)

        _, _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
            netlist.parentHwModule, hwModule,
            netlist.dbgSubmoduleBuidTracer, cacheKey, (UNROLL_FACTOR,))
        return r

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:HlsNetNode, worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization
        realization, _, UNROLL_FACTOR = self.schedulingCache[(cfg, self.optThroughputVsArea)]
        if self._hasDiv and self._hasRem:
            outputsBitMap = None
        elif self._hasDiv:
            outputsBitMap = None  # quotient starts at the bit 0
        elif self._hasRem:
            if not cfg.isInQFormat:
                raise NotImplementedError()

            outputsBitMap = (cfg.getBitWidth(),)  # remainder starts after quotient
        else:
            raise AssertionError("divrem component must be configured as a div or rem (or both)")

        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            # dividend = builder.buildZExt(_dividend, w * 2)
            # if cfg.rounding == HFloatTmpRounding.ROUND_HALF_EVEN:
            #    # c default rounding
            #    # if (a.getMsb() == b.getMsb()) {
            #    #     temp += b >> 1;
            #    # } else {
            #    #     temp -= b >> 1;
            #    # }
            #    divisorDiv2 = builder.buildConcat(builder.buildIndexConstSlice(HBits(w - 1), divisor, w - 1, 0))
            #    divisorDiv2Zext = builder.buildZExt(divisorDiv2, 2 * w)
            #    signEq = builder.buildEq(builder.buildGetMsb(_dividend),
            #                             builder.buildGetMsb(divisor))
            #    dividend = builder.buildMux(dividend._dtype,
            #                                (builder.buildAdd(dividend, divisorDiv2Zext),
            #                                 signEq,
            #                                 builder.buildSub(dividend, divisorDiv2Zext)),
            #    )
            # elif cfg.rounding == HFloatTmpRounding.ROUND_FLOOR or (cfg.rounding == HFloatTmpRounding.ROUND_DOWN and not cfg.hasSign):
            #    # just truncat
            #    pass
            # else:
            #    raise NotImplementedError()
            #
            # op = HwtOps.SDIV if cfg.hasSign else HwtOps.UDIV
            # gen = p._componentGenerators.get(op)
            # if gen is not None:
            #    gen: ComponentGenerator
            #    raise NotImplementedError()
            # else:
            #    raise NotImplementedError()
            #
            # newO = builder.buildIndexConstSlice(node._outputs[0]._dtype, divRes, w, 0, name=node.name)
            # replaceHlsNetNodeWithExpression(node, newO, None, self._assertIsConcatAnyShiftOrIndex)
            hwModule = self._getConfiguredFixpHwModule(freq, HFixedPointQ.fromHFloatTmpConfig(cfg), UNROLL_FACTOR, realization)
        else:
            hwModule = self._getConfiguredFpHwModule(freq, IEEE754Fp.fromHFloatTmpConfig(cfg), UNROLL_FACTOR, realization)

        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist, outputsBitMap=outputsBitMap)

        return True

    @override
    def toRtlForNode(self, node:"HlsNetNode", allocator:ArchElement) -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)
