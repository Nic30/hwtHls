from typing import Optional

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import replaceHlsNetNodeOperatorWithHwModule
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta, \
    ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from tests.math.componentGenerators._mul.mulUtils import PipelinedMultiplier
from tests.math.fixp.fixpTypes import HFixedPointQ


MUL_HL_opSpecializationTuple = tuple[bool, int, bool, int, int]  # isSigned0, width0, isSigned1, width1, resultWidth


class ComponentGeneratorMUL_HL(ComponentGenerator):
    """
    Generate pipelined multiplier with arbitrary size and sign lhs, rhs and result.
    """

    def __init__(self, platform:DefaultHlsPlatform, genNamePrefix:str, moduleName:str):
        super().__init__(platform)
        self.genNamePrefix = genNamePrefix
        self.moduleName = moduleName
        self.schedulingCache: dict[MUL_HL_opSpecializationTuple, tuple[ComponentRealizationMeta, ComponentRealizationMeta]] = {}

    def _getConfiguredFixpHwModule(self, realTimeClkPeriod:float, ty:HFixedPointQ,
                                   realization: Optional[OpRealizationMeta]):
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

    def resolveRealizationForHlsNetlist(self, netlist: HlsNetlistCtx, specialization: MUL_HL_opSpecializationTuple) -> None:
        cacheKey = specialization
        try:
            return self.schedulingCache[cacheKey][1]
        except KeyError:
            pass

        isSigned0: int
        width0: int
        isSigned1: int
        width1: int
        resultWidth: int
        isSigned0, width0, isSigned1, width1, resultWidth = specialization
        rtclkPeriod = netlist.realTimeClkPeriod
        clkPeriod = netlist.normalizedClkPeriod
        p = self.platform
        ffStoreTime = p.get_ff_store_time(rtclkPeriod, netlist.scheduler.resolution)
        maxMulWidth = max(width0, width1)
        r = p.get_op_realization(HwtOps.MUL, None, maxMulWidth, 2, rtclkPeriod)
        if r.inputWireDelay <= clkPeriod - ffStoreTime and r.outputWireDelay <= clkPeriod - ffStoreTime:
            # use mul as it is
            pass
        else:
            raise NotImplementedError("[todo] use custom multiplier")

        self.schedulingCache[cacheKey] = (r, r, maxMulWidth)
        return r

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode], debugTracer: DebugTracer) -> bool:
        freq = node.netlist.realTimeClkPeriod
        realization, _, maxMulWidth = self.schedulingCache[node.operatorSpecialization]
        isSigned0: int
        width0: int
        isSigned1: int
        width1: int
        resultWidth: int
        isSigned0, width0, isSigned1, width1, resultWidth = node.operatorSpecialization
        if maxMulWidth <= max(width0, width1):
            return False  # this will be normal * operator, no need for special instances

        raise NotImplementedError()
        hwModule = self._getConfiguredFixpHwModule(freq, width, realization)
        compBuilder = AbstractComponentBuilder(node.netlist.parentHwModule, None, f"{self._genNamePrefix}_{self._moduleName}")

        replaceHlsNetNodeOperatorWithHwModule(
            compBuilder, node, hwModule,
            worklist, debugTracer,
            inputsConcatenated=True,
            outputsConcatenated=True,
        )
        return True

    @override
    def toRtlForNode(self, node:HlsNetNode, allocator:ArchElement) -> None:
        isSigned0: int
        width0: int
        isSigned1: int
        width1: int
        resultWidth: int
        isSigned0, width0, isSigned1, width1, resultWidth = node.operatorSpecialization
        if self.schedulingCache[node.operatorSpecialization][2] > min(width0, width1):
            raise AssertionError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)

        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        assert len(node.dependsOn) == 2
        ops: list[TimeIndependentRtlResourceItem] = [
            allocator.rtlAllocHlsNetNodeOutInTime(dep, depT)
            for dep, depT in zip(node.dependsOn, node.scheduledIn)
        ]

        ops = [
            (sext if isSigned else zext)(o.data, resultWidth)._cast_sign(isSigned)
             for isSigned, o in zip((isSigned0, isSigned1), ops)
        ]

        res = ops[0] * ops[1]
        res = res[resultWidth:]
        assert len(node._outputs) == 1
        res = allocator.rtlRegisterOutputRtlSignal(
            node._outputs[0], res, False, False, False)

        node._isRtlAllocated = True
        return res

