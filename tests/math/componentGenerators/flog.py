import math
from typing import Optional

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.llvm.llvmIr import HFloatTmpConfig, CallInst, Instruction
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp.fixplog import FixpLog2TabularizedHwModule
from tests.math.hFloatTmp.hFloatTmp import HFloatTmpConfigHdlType, HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import OP_FLOG2
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from pyDigitalWaveTools.vcd.writer import VcdWriter
from hwt.hdl.const import HConst


class ComponentGeneratorLlvmIntrinsicLog(ComponentGeneratorFp):
    INPUT_CNT = 1

    @override
    @staticmethod
    def evalFn(y:float) -> float:
        return math.log(y)


class ComponentGeneratorLlvmIntrinsicLog2(ComponentGeneratorFp):
    INPUT_CNT = 1

    @override
    @staticmethod
    def evalFn(y:float) -> float:
        return math.log2(y)


class ComponentGeneratorLlvmIntrinsicLog10(ComponentGeneratorFp):
    INPUT_CNT = 1

    @override
    @staticmethod
    def evalFn(y:float) -> float:
        return math.log10(y)


class ComponentGeneratorFLOG_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    evalFn = staticmethod(ComponentGeneratorLlvmIntrinsicLog.evalFn)


class ComponentGeneratorFLOG2_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    evalFn = staticmethod(ComponentGeneratorLlvmIntrinsicLog2.evalFn)


class ComponentGeneratorFLOG10_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):
    evalFn = staticmethod(ComponentGeneratorLlvmIntrinsicLog10.evalFn)


class ComponentGeneratorFLOG2(ComponentGeneratorFp):
    FIXP_HWMODULE_CLS = FixpLog2TabularizedHwModule
    opDef = OP_FLOG2

    def __init__(self, platform: DefaultHlsPlatform,
                 genNamePrefix:str, moduleName:str,
                 MAX_TABLE_ADDR_WIDTH:int):
        assert MAX_TABLE_ADDR_WIDTH >= 0, MAX_TABLE_ADDR_WIDTH
        ComponentGeneratorFp.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth -> scheduling
        self.schedulingCache: dict[tuple[int, HFloatTmpConfigHdlType], tuple[ComponentRealizationMeta, ComponentRealizationMeta]]
        self.MAX_TABLE_ADDR_WIDTH = MAX_TABLE_ADDR_WIDTH

    def _getConfiguredFixpHwModule(self, realTimeClkPeriod:float, ty:HFixedPointQ, realization: Optional[ComponentRealizationMeta]):
        hwModule = self.FIXP_HWMODULE_CLS()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.MAX_TABLE_ADDR_WIDTH = self.MAX_TABLE_ADDR_WIDTH
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    def resolveRealizationForHlsNetlist(self, netlist: HlsNetlistCtx, cfg: HFloatTmpConfig) -> None:
        cacheKey = (cfg, self.MAX_TABLE_ADDR_WIDTH)
        try:
            return self.schedulingCache[cacheKey][1]
        except KeyError:
            pass

        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            ty = HFixedPointQ.fromHFloatTmpConfig(cfg)

            # run compilation of IntDiv HwModule to resolve scheduling properties
            hwModule = self._getConfiguredFixpHwModule(netlist.realTimeClkPeriod, ty, None)
            _, _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
                netlist.parentHwModule, hwModule,
                netlist.dbgSubmoduleBuidTracer, cacheKey)
            return r
        else:
            raise NotImplementedError()

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:HlsNetNode, worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            realization, _ = self.schedulingCache[(cfg, self.MAX_TABLE_ADDR_WIDTH)]
            hwModule = self._getConfiguredFixpHwModule(freq, HFixedPointQ.fromHFloatTmpConfig(cfg), realization)
            ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)

            return True

        else:
            raise NotImplementedError()

        return True

    @override
    def toRtlForNode(self, node:HlsNetNode, allocator:ArchElement) -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)
