from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from tests.math.componentGenerators._genericHwModules import _FpAlu2HwModule
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat
from tests.math.componentGenerators.fadd import ComponentGeneratorFADD
from tests.math.fp.fpmul import IEEE754FpMul
from tests.math.hFloatTmp.hFloatTmpOps import OP_FMUL
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps


class ComponentGeneratorFMUL_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat):

    @override
    @staticmethod
    def evalFn(a: float, b: float) -> float:
        return a * b


@serializeParamsUniq
class FpMulHwModule(_FpAlu2HwModule):
    FN = staticmethod(IEEE754FpMul)

    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True, inputArgsAreStructMembers=True)
    def model(a: float, b: float) -> float:
        return a * b


# https://surf-vhdl.com/how-to-implement-pipeline-multiplier-vhdl/
class ComponentGeneratorFMUL(ComponentGeneratorFADD):
    HWT_OPERATOR = HwtOps.MUL
    opDef = OP_FMUL
    FP_HWMODULE_CLS = FpMulHwModule

    @override
    def toHwtCompatibleOperatorBeforeScheduling_Q_getTmpCfg(self, cfg: HFloatTmpConfig) -> tuple[HFloatTmpConfig, HFloatTmpConfig]:
        cfgIn:HFloatTmpConfig = cfg.copy()
        cfgIn.exponentOrIntWidth *= 2
        cfgIn.exponentOrIntWidth += cfg.mantissaOrFracWidth
        cfgOut:HFloatTmpConfig = cfg.copy()
        cfgOut.exponentOrIntWidth *= 2
        cfgOut.mantissaOrFracWidth *= 2
        return cfgIn, cfgOut

    # @override
    # def toRtlForNode(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
    #    assert not node._isMarkedRemoved, node
    #    assert not node._isRtlAllocated, node
    #    _i0, _i1 = self._toRtlForNode_getInputDeps(node, allocator)
    #    cfg: HFloatTmpConfig = node.operatorSpecialization
    #    if cfg.isInQFormat:
    #        if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
    #            raise NotImplementedError(node, cfg)
    #        width = _i0.data._dtype.bit_length()
    #        ext = sext if cfg.hasSign else zext
    #        outSig = self.HWT_OPERATOR._evalFn(ext(_i0.data, width * 2), ext(_i1.data, width * 2))
    #        assert outSig._dtype.bit_length() == 2 * width, (outSig._dtype, width, node, cfg)
    #        outSig = outSig[cfg.exponentOrIntWidth + 2 * cfg.mantissaOrFracWidth:cfg.mantissaOrFracWidth]
    #    else:
    #        # netlist = node.netlist
    #        raise NotImplementedError()
    #
    #    return self._toRtlForNode_registerOutput(node, allocator, outSig)
    #
