from typing import Optional

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.llvm.llvmIr import HFloatTmpConfig, HFloatTmpSaturation
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fp.fpadd import IEEE754FpAdd
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.componentGenerators.genericHwModules import _FpBinOpAluHwModule
from tests.math.hFloatTmp.hFloatTmpCast import OP_CAST_HFLOATTMP_TO_HFLOATTMP


class ComponentGeneratorFADD(ComponentGenerator):
    """
    A generator for OP_FADD (fixed point or floating point adder)
    """
    HWT_OPERATOR = HwtOps.ADD
    FP_OPERATOR_FN = staticmethod(IEEE754FpAdd)

    def __init__(self, platform:"DefaultHlsPlatform",
                 genNamePrefix:str, moduleName:str,
                 optThroughputVsArea=0.0,
                 FP_HWMODULE_CLS=_FpBinOpAluHwModule):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth (optThroughputVsArea, HFloatTmpConfig) -> scheduling (OpRealizationMeta, UNROLL_FACTOR)
        self.schedulingCache: dict[tuple[float, HFloatTmpConfig], tuple[OpRealizationMeta, int]]
        self.optThroughputVsArea = optThroughputVsArea
        self.FP_HWMODULE_CLS = FP_HWMODULE_CLS

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
            builder = node.getHlsNetlistBuilder()
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

    def _scaleUnrollFactor(self, cfg: HFloatTmpConfig):
        if cfg.isInQFormat:
            ty = HFixedPointQ.fromHFloatTmpConfig(cfg)
        else:
            ty = IEEE754Fp.fromHFloatTmpConfig(cfg)

        if self.optThroughputVsArea == 0:
            UNROLL_FACTOR = 1
        elif self.optThroughputVsArea == 1.0:
            if cfg.isInQFormat:
                HWMODULE_CLS = self.FIXP_HWMODULE_CLS
            else:
                HWMODULE_CLS = self.FP_HWMODULE_CLS

            UNROLL_FACTOR = HWMODULE_CLS._getMaxIterationCountForTy(ty)
        else:
            raise NotImplementedError()
        return UNROLL_FACTOR

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, ty:IEEE754Fp, UNROLL_FACTOR:int, realization: Optional[OpRealizationMeta]):
        hwModule = self.FP_HWMODULE_CLS()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.UNROLL_FACTOR = UNROLL_FACTOR
        hwModule.FN = self.FP_OPERATOR_FN
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) == 2, node
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            raise AssertionError("This should have been lowered by toHwtCompatibleOperatorBeforeScheduling()", node)

        cacheKey = (self.optThroughputVsArea, cfg)
        try:
            return self.schedulingCache[cacheKey][0]
        except KeyError:
            pass

        UNROLL_FACTOR = self._scaleUnrollFactor(cfg)
        netlist = node.netlist
        # run compilation of IntDiv HwModule to resolve scheduling properties
        hwModule = self._getConfiguredHwModule(netlist.realTimeClkPeriod, IEEE754Fp.fromHFloatTmpConfig(cfg), UNROLL_FACTOR, None)
        _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
            netlist.parentHwModule, hwModule,
            netlist.dbgSubmoduleBuidTracer, cacheKey, (UNROLL_FACTOR,))
        return r

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            raise AssertionError("This should have been lowered by toHwtCompatibleOperatorBeforeScheduling()", node)

        realization, UNROLL_FACTOR = self.schedulingCache[(self.optThroughputVsArea, cfg)]
        hwModule = self._getConfiguredHwModule(freq, IEEE754Fp.fromHFloatTmpConfig(cfg), UNROLL_FACTOR, realization)
        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)

        if realization.fitsIntoSingleClockWindow():
            assert hwModule.hlsOpRealizationMeta.fitsIntoSingleClockWindow(), (hwModule, realization, hwModule.hlsOpRealizationMeta)
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

