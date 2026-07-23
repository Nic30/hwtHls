
from typing import Optional

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.hardBlock import HardBlockHwModule
from hwtHls.llvm.llvmIr import Function, HwtHlsInstCombinePass
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from tests.math.addMaskedOp import OP_ADD_MASKED, OP_ADD_ONES_COMPLEMENT_MASKED
from tests.math.addTree import OP_ADD_TREE
from tests.math.addTreeGen import ComponentGeneratorAddTree
from tests.math.maskSegments import MaskSegmentsComponentGenerator
from tests.math.maskSegments import OP_MASK_SEGMENTS


class AddMaskedHardblock(HardBlockHwModule):
    """
    A module and a HLS compatible function for maked add.
    """

    def __init__(self,
            hwInputT: HBits,
            accumulatorT: HBits,
            maxInputsPerBalancedTree: Optional[int]=None,
            name:Optional[str]=None,
            operationRealizationMeta:Optional[OpRealizationMeta]=None):
        hwOutputT = accumulatorT
        _hwInputT = HStruct(
            (accumulatorT, "state"),
            (hwInputT, "data"),
            (BIT, "mask"),
        )
        self.maxInputsPerBalancedTree = maxInputsPerBalancedTree
        HardBlockHwModule.__init__(self, _hwInputT, hwOutputT=hwOutputT, defaultKwargs={"mask": b1}, name=name,
                                   operationRealizationMeta=operationRealizationMeta)

    @override
    def getFnName(self):
        dataWidth = self.hwInputT.field_by_name['data'].dtype.bit_length()
        stateWidth = self.hwInputT.field_by_name['state'].dtype.bit_length()

        return (f"hwtHls.pyObjectPlaceholder.{self.placeholderObjectId:d}.addMasked"
                f".i{stateWidth:d}.i{dataWidth}")

    @override
    def _translateExprHConstHardBlockFunctionDef(self, toLlvm: ToLlvmIrTranslator):
        F:Function = HardBlockHwModule._translateExprHConstHardBlockFunctionDef(self, toLlvm)
        # F.addFnAttr(Attribute.AttrKind.Speculatable)
        strCtx = toLlvm.strCtx
        F.setMetadata(strCtx.addStringRef(HwtHlsInstCombinePass.metadataName_mergableFunction_statePlusMaskedData),
                      toLlvm.mdGetTuple([], False))
        platform = toLlvm.parentHwModule._target_platform
        if OP_MASK_SEGMENTS not in platform._componentGenerators:
            platform._componentGenerators[OP_MASK_SEGMENTS] = MaskSegmentsComponentGenerator(platform, "gen", "maskSegments")

        if OP_ADD_TREE not in platform._componentGenerators:
            platform._componentGenerators[OP_ADD_TREE] = ComponentGeneratorAddTree(platform, "gen", "addTree")

        if OP_ADD_MASKED not in platform._componentGenerators:
            from tests.math.addMaskedGen import ComponentGeneratorAddMasked
            platform._componentGenerators[OP_ADD_MASKED] = ComponentGeneratorAddMasked(platform, "gen", "addMasked")

        return F

    def getComponentGeneratorKey(self):
        return OP_ADD_MASKED


class AddMaskedOnesComplementHardblock(AddMaskedHardblock):
    """
    Same as :class:`AddMaskedHardblock` but instead of "normal" addition it performs ones complement addition.
    Typicall usecase is TCP/UDP checksum.
    """

    @override
    def getFnName(self):
        dataWidth = self.hwInputT.field_by_name['data'].dtype.bit_length()
        stateWidth = self.hwInputT.field_by_name['state'].dtype.bit_length()

        return (f"hwtHls.pyObjectPlaceholder.{self.placeholderObjectId:d}.add1sComplMasked"
                f".i{stateWidth:d}.i{dataWidth}")

    def getComponentGeneratorKey(self):
        return OP_ADD_ONES_COMPLEMENT_MASKED
      
    @override
    def _translateExprHConstHardBlockFunctionDef(self, toLlvm: ToLlvmIrTranslator):
        F = super()._translateExprHConstHardBlockFunctionDef(toLlvm)
        
        platform = toLlvm.parentHwModule._target_platform
        if OP_ADD_ONES_COMPLEMENT_MASKED not in platform._componentGenerators:
            from tests.math.addMaskedGen import ComponentGeneratorAdd1sComplMasked
            platform._componentGenerators[OP_ADD_ONES_COMPLEMENT_MASKED] = ComponentGeneratorAdd1sComplMasked(platform, "gen", "add1sComplMasked")
        return  F
        
