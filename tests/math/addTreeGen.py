from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from tests.math.addTree import AddTreeHwModule


class ComponentGeneratorAddTree(ComponentGenerator):
    """
    A generator for OP_ADD_TREE
    """
    _operatorModuleCls = AddTreeHwModule

    def __init__(self, platform: "VirtualHlsPlatform", genNamePrefix:str, moduleName:str):
        super().__init__(platform, genNamePrefix, moduleName)
        self.schedulingCache: dict[int, tuple[ComponentRealizationMeta,  # seen from inside
                                              ComponentRealizationMeta  # seen from outside
                                              ]] = {}

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, IN_CNT: int, T_IN: HBits, T_OUT: HBits, realization:ComponentRealizationMeta):
        hwModule = self._operatorModuleCls()
        hwModule.INPUT_CNT = IN_CNT
        hwModule.DATA_WIDTH_IN = T_IN.bit_length()
        hwModule.DATA_WIDTH_OUT = T_OUT.bit_length()
        
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> None:
        return self.resolveRealizationForHlsNetlist(node.netlist, len(node._inputs), node.dependsOn[0]._dtype, node._outputs[0]._dtype)

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx", IN_CNT: int, T_IN: HBits, T_OUT: HBits) -> None:
        cacheKey = (IN_CNT, T_IN.bit_length(), T_OUT.bit_length())
        try:
            return self.schedulingCache[cacheKey][1]
        except KeyError:
            pass

        # run compilation of HwModule to resolve scheduling properties
        hwModule = self._getConfiguredHwModule(netlist.realTimeClkPeriod, IN_CNT, T_IN, T_OUT, None)
        _, _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
            netlist.parentHwModule, hwModule,
            netlist.dbgSubmoduleBuidTracer, cacheKey)
        return r

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        IN_CNT = len(node._inputs)
        T_IN = node.dependsOn[0]._dtype
        T_OUT = node._outputs[0]._dtype
        cacheKey = (IN_CNT, T_IN.bit_length(), T_OUT.bit_length())
        
        realizationSeenFromIn, realizationSeenFromOut = self.schedulingCache[cacheKey]
        hwModule = self._getConfiguredHwModule(freq, IN_CNT, T_IN, T_OUT, realizationSeenFromIn)
        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)
        if realizationSeenFromOut.fitsIntoSingleClockWindow():
            assert hwModule.getHlsOpRealizationMeta()[1].fitsIntoSingleClockWindow(), (hwModule, realizationSeenFromOut, hwModule.hlsOpRealizationMeta)
        return True

    @override
    def toRtlForNode(self, node:"HlsNetNode", allocator:"ArchElement") -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)
