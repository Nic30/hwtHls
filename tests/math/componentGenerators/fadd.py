from typing import Optional

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.llvm.llvmIr import HFloatTmpConfig, HFloatTmpSaturation
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from hwtHls.platform.opRealizationMeta import OpRealizationMeta, \
    ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpretInt import _makeDecodeOpcodeFunction_BinaryOperator
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.componentGenerators._genericHwModules import _FpBinOpAluHwModule
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat
from tests.math.fp.fpadd import IEEE754FpAdd
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.hFloatTmp.hFloatTmpCast import OP_CAST_HFLOATTMP_TO_HFLOATTMP
from tests.math.hFloatTmp.hFloatTmpOps import OP_FADD


class ComponentGeneratorFADD_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat):

    @override
    @staticmethod
    def evalFn(a: float, b: float) -> float:
        return a + b


class ComponentGeneratorFADD(ComponentGeneratorFp):
    """
    A generator for OP_FADD (fixed point or floating point adder)
    """
    INPUT_CNT = 2
    HWT_OPERATOR = HwtOps.ADD
    FP_OPERATOR_FN = staticmethod(IEEE754FpAdd)
    opDef = OP_FADD

    def __init__(self, platform:DefaultHlsPlatform,
                 genNamePrefix:str, moduleName:str,
                 optThroughputVsArea=0.0,
                 FP_HWMODULE_CLS=_FpBinOpAluHwModule):
        ComponentGeneratorFp.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth (optThroughputVsArea, HFloatTmpConfig) -> scheduling (OpRealizationMeta, UNROLL_FACTOR)
        self.schedulingCache: dict[tuple[float, HFloatTmpConfig], tuple[ComponentRealizationMeta, ComponentRealizationMeta, int]]
        self.optThroughputVsArea = optThroughputVsArea
        self.FP_HWMODULE_CLS = FP_HWMODULE_CLS
        self.llvmIrInterpretDecode = _makeDecodeOpcodeFunction_BinaryOperator(self.HWT_OPERATOR._evalFn)

    def toHwtCompatibleOperatorBeforeScheduling_Q_getTmpCfg(self, cfg: HFloatTmpConfig) -> tuple[HFloatTmpConfig, HFloatTmpConfig]:
        """
        :return: the config for input operands, the config for output operands
        """
        cfg2:HFloatTmpConfig = cfg.copy()
        if cfg.saturation != HFloatTmpSaturation.SATURATE_NONE:
            cfg2.exponentOrIntWidth += 1
            assert cfg != cfg2
        return cfg2, cfg2

    def toHwtCompatibleOperatorBeforeScheduling(self, node:HlsNetNodeOperator, worklist:SetList["HlsNetNode"]):
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            # perform add on +1b and then round it back to result width
            builder = HlsNetlistBuilderWithWorklist(node.getHlsNetlistBuilder(), worklist)
            cfgIn, cfgOut = self.toHwtCompatibleOperatorBeforeScheduling_Q_getTmpCfg(cfg)
            t2 = HBits(cfgIn.getBitWidth())
            op0, op1 = node.dependsOn
            if cfgIn != cfg:
                op0 = builder.buildOp(OP_CAST_HFLOATTMP_TO_HFLOATTMP, (cfg, cfgIn), t2, op0)
                op1 = builder.buildOp(OP_CAST_HFLOATTMP_TO_HFLOATTMP, (cfg, cfgIn), t2, op1)

            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            res = builder.buildOp(self.HWT_OPERATOR, None, t2, op0, op1)
            if cfgOut != cfg:
                res = builder.buildOp(OP_CAST_HFLOATTMP_TO_HFLOATTMP, (cfgOut, cfg), node._outputs[0]._dtype, res)
            debugTracer = node.netlist.dbgSubmoduleBuidTracer
            with debugTracer.scoped(self, node):
                debugTracer.log(("replacing with", res))
                replaceOperatorNodeWith(node, res, worklist)
            return True

        return False

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, ty:IEEE754Fp, UNROLL_FACTOR:int, realization: Optional[OpRealizationMeta]):
        hwModule = self.FP_HWMODULE_CLS()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.UNROLL_FACTOR = UNROLL_FACTOR
        hwModule.FN = self.FP_OPERATOR_FN
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    @override
    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            raise AssertionError("This should have been lowered by toHwtCompatibleOperatorBeforeScheduling()", node)
        return ComponentGeneratorFp.resolveRealizationOfNode(self, node)

    @override
    def resolveRealizationForHlsNetlist(self, netlist: HlsNetlistCtx,
                                        cfg: HFloatTmpConfig) -> ComponentRealizationMeta:
        cacheKey = (self.optThroughputVsArea, cfg)

        try:
            return self.schedulingCache[cacheKey][1]
        except KeyError:
            pass

        UNROLL_FACTOR = self._scaleUnrollFactor(cfg)
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError(cfg)
            cfgIn, cfgOut = self.toHwtCompatibleOperatorBeforeScheduling_Q_getTmpCfg(cfg)
            w = max(cfgIn.getBitWidth(), cfgOut.getBitWidth())
            r = self.platform.get_op_realization(self.HWT_OPERATOR, None, w, 2, netlist.realTimeClkPeriod)
            r = ComponentRealizationMeta.fromOpRealization(r)

            netlist.dbgSubmoduleBuidTracer.log(("resolved realization", self, cfg, r,))
            self.schedulingCache[cacheKey] = (r, r, UNROLL_FACTOR)
        else:
            # run compilation of HwModule to resolve scheduling properties
            hwModule = self._getConfiguredHwModule(netlist.realTimeClkPeriod, IEEE754Fp.fromHFloatTmpConfig(cfg), UNROLL_FACTOR, None)
            _, _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
                netlist.parentHwModule, hwModule,
                netlist.dbgSubmoduleBuidTracer, cacheKey, (UNROLL_FACTOR,))
        return r

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            raise AssertionError("This should have been lowered by toHwtCompatibleOperatorBeforeScheduling()", node)

        realizationSeenFromIn, realizationSeenFromOut, UNROLL_FACTOR = self.schedulingCache[(self.optThroughputVsArea, cfg)]
        hwModule = self._getConfiguredHwModule(freq, IEEE754Fp.fromHFloatTmpConfig(cfg), UNROLL_FACTOR, realizationSeenFromIn)
        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)

        if realizationSeenFromOut.fitsIntoSingleClockWindow():
            assert hwModule.getHlsOpRealizationMeta()[1].fitsIntoSingleClockWindow(), (
                hwModule, realizationSeenFromOut, hwModule.getHlsOpRealizationMeta())
        return True

    #
    # @override
    # def toRtlForNode(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
    #    assert not node._isMarkedRemoved, node
    #    assert not node._isRtlAllocated, node
    #    _i0, _i1 = self._toRtlForNode_getInputDeps(node, allocator)
    #    cfg: HFloatTmpConfig = node.operatorSpecialization
    #    if cfg.isInQFormat:
    #        raise AssertionError("This should have been lowered by toHwtCompatibleOperatorBeforeScheduling()")
    #        # outSig = self.HWT_OPERATOR._evalFn(_i0.data, _i1.data)
    #    else:
    #        # netlist = node.netlist
    #        raise NotImplementedError()
    #
    #    return self._toRtlForNode_registerOutput(node, allocator, outSig)

