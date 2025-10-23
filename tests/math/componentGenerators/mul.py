from typing import Optional

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import replaceHlsNetNodeOperatorWithHwModule
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.componentGenerators._mul.mulUtils import PipelinedMultiplier


class ComponentGeneratorMUL(ComponentGenerator):
    """
    Generate pipelined multiplier if normal multiplier is not fast enough.
    
    :note: location of inputs and outpus are marked to be inside DSP or fabric locations
        If node allocated by this generator is not top the value is likely need to be routed to dsp or to fabric from dsp.
        Note also the fact that there are multiple locations inside of the DSP block, some algorithms
        for multiplication may use final adder etc.

    Pipelinining strategy:
    * if < OPT_THRESHOLD_DSP_MIN_WIDTH_RATIO* min(DSP_WIDTH) use target native mul in LUT 
    * if <= min(DSP_WIDTH) mul use 1 DSP 
    * if <= max(DSP_WIDTH) mul use PipelinedMultiplierChained
    * if LHS/RHS width is inbalanced
       * if one operand width is <= min(DSP_WIDTH) use PipelinedMultiplierChained
       * if operand width ratio is roughly 3:2 use PipelinedMultiplierToom2_5
    * if >= 3*min(DSP_WIDTH) use PipelinedMultiplierToom2
    * else PipelinedMultiplierChained
    """
    OPT_THRESHOLD_DSP_MIN_WIDTH_RATIO = 0.5

    def __init__(self, platform:"DefaultHlsPlatform", genNamePrefix:str, moduleName:str):
        super().__init__(platform)
        self.genNamePrefix = genNamePrefix
        self.moduleName = moduleName

    def _getConfiguredFixpHwModule(self, realTimeClkPeriod:float, ty:HFixedPointQ, realization: Optional[OpRealizationMeta]):
        hwModule = PipelinedMultiplier()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.MAX_TABLE_ADDR_WIDTH = self.MAX_TABLE_ADDR_WIDTH
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) == 2, node
        return self.resolveRealizationForHlsNetlist(node.netlist, node.operatorSpecialization)

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx", width: int) -> None:
        cacheKey = width
        try:
            return self.schedulingCache[cacheKey][1]
        except KeyError:
            pass

        freq = netlist.realTimeClkPeriod
        # run compilation of IntDiv HwModule to resolve scheduling properties
        maxMulWidth, rSeenFromIn, rSeenFromOut = PipelinedMultiplier.resolveOpRealization(self.platform, freq, width)
        self.schedulingCache[cacheKey] = (rSeenFromIn, rSeenFromOut, maxMulWidth)
        return rSeenFromOut

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        width = node._outputs[0]._dtype.bit_length()
        realization, _ = self.schedulingCache[width]
        hwModule = self._getConfiguredFixpHwModule(freq, width, realization)
        compBuilder = AbstractComponentBuilder(node.netlist.parentHwModule, None, f"{self._genNamePrefix}_{self._moduleName}")

        replaceHlsNetNodeOperatorWithHwModule(
            compBuilder, node, hwModule,
            worklist,
            inputsConcatenated=True,
            outputsConcatenated=True,
        )
        return True

    @override
    def toRtlForNode(self, node:"HlsNetNode", allocator:"ArchElement") -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)
