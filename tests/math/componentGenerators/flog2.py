from typing import Optional

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
from tests.math.fixp.fixplog import FixpLog2TabularizedHwModule
from tests.math.hFloatTmp.hFloatTmp import HFloatTmpConfigHdlType


class ComponentGeneratorFLOG2(ComponentGenerator):
    FIXP_HWMODULE_CLS = FixpLog2TabularizedHwModule

    def __init__(self, platform:"DefaultHlsPlatform",
                 genNamePrefix:str, moduleName:str,
                 MAX_TABLE_ADDR_WIDTH:int):
        assert MAX_TABLE_ADDR_WIDTH >= 0, MAX_TABLE_ADDR_WIDTH
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth -> scheduling
        self.schedulingCache: dict[tuple[int, HFloatTmpConfigHdlType], OpRealizationMeta]
        self.MAX_TABLE_ADDR_WIDTH = MAX_TABLE_ADDR_WIDTH

    def _getConfiguredFixpHwModule(self, realTimeClkPeriod:float, ty:HFixedPointQ, realization: Optional[OpRealizationMeta]):
        hwModule = self.FIXP_HWMODULE_CLS()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.MAX_TABLE_ADDR_WIDTH = self.MAX_TABLE_ADDR_WIDTH
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) == 1, node
        return self.resolveRealizationForHlsNetlist(node.netlist, node.operatorSpecialization)

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx", cfg: HFloatTmpConfig) -> None:
        cacheKey = (cfg, self.MAX_TABLE_ADDR_WIDTH)
        try:
            return self.schedulingCache[cacheKey]
        except KeyError:
            pass

        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            ty = HFixedPointQ.fromHFloatTmpConfig(cfg)

            # run compilation of IntDiv HwModule to resolve scheduling properties
            hwModule = self._getConfiguredFixpHwModule(netlist.realTimeClkPeriod, ty, None)
            _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
                netlist.parentHwModule, hwModule,
                netlist.dbgSubmoduleBuidTracer, cacheKey)
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

            realization = self.schedulingCache[(cfg, self.MAX_TABLE_ADDR_WIDTH)]
            hwModule = self._getConfiguredFixpHwModule(freq, HFixedPointQ.fromHFloatTmpConfig(cfg), realization)
            ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)

            return True

        else:
            raise NotImplementedError()

        return True

    @override
    def toRtlForNode(self, node:"HlsNetNode", allocator:"ArchElement") -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)
