
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp.fixpdivrem import FixpDivRemHwModule


class ComponentGeneratorFDIVREM(ComponentGenerator):

    def __init__(self, platform:"DefaultHlsPlatform", hasDiv:bool, hasRem:bool,
                 genNamePrefix:str, moduleName:str,
                 optThroughputVsArea=0.0,
                 FIXP_HWMODULE_CLS=FixpDivRemHwModule):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth (optThroughputVsArea, HFloatTmpConfig) -> scheduling (OpRealizationMeta, UNROLL_FACTOR)
        self._hasDiv = hasDiv
        self._hasRem = hasRem
        self.optThroughputVsArea = optThroughputVsArea
        self.FIXP_HWMODULE_CLS = FIXP_HWMODULE_CLS
        assert hasDiv or hasRem

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

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) == 2, node
        return self.resolveRealizationForHlsNetlist(node.netlist, node.operatorSpecialization)

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx", cfg: HFloatTmpConfig) -> None:
        cacheKey = (cfg, self.optThroughputVsArea)
        try:
            return self.schedulingCache[cacheKey][0]
        except KeyError:
            pass

        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            ty = HFixedPointQ.fromHFloatTmpConfig(cfg)
            if self.optThroughputVsArea == 0:
                UNROLL_FACTOR = 1
            elif self.optThroughputVsArea == 1.0:
                UNROLL_FACTOR = self.FIXP_HWMODULE_CLS._getMaxIterationCountForTy(ty)
            else:
                raise NotImplementedError()

            # run compilation of IntDiv HwModule to resolve scheduling properties
            hwModule = self._getConfiguredFixpHwModule(netlist.realTimeClkPeriod, ty, UNROLL_FACTOR, None)
            _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
                netlist.parentHwModule, hwModule,
                netlist.dbgSubmoduleBuidTracer, cacheKey, (UNROLL_FACTOR,))
            return r
        else:
            raise NotImplementedError()

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization
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

            realization, UNROLL_FACTOR = self.schedulingCache[(cfg, self.optThroughputVsArea)]
            hwModule = self._getConfiguredFixpHwModule(freq, HFixedPointQ.fromHFloatTmpConfig(cfg), UNROLL_FACTOR, realization)
            if self._hasDiv and self._hasRem:
                outputsBitMap = None
            elif self._hasDiv:
                outputsBitMap = None  # quotient starts at the bit 0
            elif self._hasRem:
                outputsBitMap = (cfg.getBitWidth(),)  # remainder starts after quotient
            else:
                raise AssertionError("divrem component must be configured as a div or rem (or both)")
            ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist, outputsBitMap=outputsBitMap)
            return True

        else:
            raise NotImplementedError()
        return True

    @override
    def toRtlForNode(self, node:"HlsNetNode", allocator:"ArchElement") -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)
