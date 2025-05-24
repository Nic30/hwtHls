from typing import Optional

from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from tests.math.componentGenerators._div.divRestoring import DivRemHwModule


class ComponentGeneratorDIVREM(ComponentGenerator):
    """
    :ivar optThroughputVsArea: optimization target specification, 0 means max resource savings, 1.0 means max throughput
    """

    def __init__(self, platform:"DefaultHlsPlatform", isSigned:bool, hasDiv:bool, hasRem:bool,
                 genNamePrefix:str, moduleName:str, optThroughputVsArea=0.0, INT_DIV_HWMODULE_CLS=DivRemHwModule):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth -> scheduling
        self.schedulingCache: dict[tuple[float, int], tuple[OpRealizationMeta, int]] = {}
        self._isSigned = isSigned
        self._hasDiv = hasDiv
        self._hasRem = hasRem
        self.optThroughputVsArea = optThroughputVsArea
        self.INT_DIV_HWMODULE_CLS = INT_DIV_HWMODULE_CLS
        assert hasDiv or hasRem

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, DATA_WIDTH:int, UNROLL_FACTOR:int,
                               realization:Optional[OpRealizationMeta]):
        hwModule = self.INT_DIV_HWMODULE_CLS()
        hwModule.T = HBits(DATA_WIDTH, signed=self._isSigned)
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.UNROLL_FACTOR = UNROLL_FACTOR
        if realization:
            hwModule._setIoChannelTypes(realization)
        return hwModule

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> None:
        DATA_WIDTH = node.dependsOn[0]._dtype.bit_length()
        return self.resolveRealizationForHlsNetlist(node.netlist,
                                                    node.operatorSpecialization, DATA_WIDTH)

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx",
                                        operatorSpecialization, DATA_WIDTH: int) -> None:
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
        _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
            netlist.parentHwModule, intDivModule,
            netlist.dbgSubmoduleBuidTracer, cacheKey, (UNROLL_FACTOR,))
        return r

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList["HlsNetNode"]) -> bool:
        """
        Lower to independent HwModule and read/write pairs because
        division contains internal sync logic and can not be easily inlined.
        """
        DATA_WIDTH = node.dependsOn[0]._dtype.bit_length()
        realization, UNROLL_FACTOR = self.schedulingCache[(DATA_WIDTH, self.optThroughputVsArea)]
        hwModule = self._getConfiguredHwModule(node.netlist.realTimeClkPeriod, DATA_WIDTH, UNROLL_FACTOR, realization)
        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)
        return True

    @override
    def toRtlForNode(self, node:"HlsNetNode", allocator:"ArchElement") -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperator", node, node._isMarkedRemoved)
