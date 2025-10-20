from typing import Union, Optional

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.function import HFunction
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStructField
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pragma import _PyBytecodeIntrinsic
from hwtHls.llvm.llvmIr import CallInst, AddDefaultFunctionAttributes, Value, \
    IRBuilder, FunctionCallee, VectorOfTypePtr, FunctionType, Function, Type, \
    Instruction, MachineInstr, Register, MachineRegisterInfo
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, HlsNetNodeOut
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MirToHlsNetlistTranslatedInstrOpsT
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwt.hdl.types.bits import HBits


class HardBlockHwModule(_PyBytecodeIntrinsic):
    """
    A container for part of the circuit inlined later during compilation.
    :note: this class inherits from HFunctionConst because the object represents a constant function pointer
    
    There are multiple ways how to inline function in hwtHls:
       * call normal python function which produces expression/ast and analyze this expression.
       * call hlsBytecode with PyBytecodeInline which inlines function in frontend
       * use :class:`HardBlockHwModule` + :class:`ComponentGenerator` to inline on various places during
         HlsNetlist to optimization and lowering to RTL
    
    :ivar placeholderObjectId: index of this in :attr:`ToLlvmIrTranslator.placeholderObjectSlots` list
    """

    __hlsIsLowLevelFn = True
    _dtype = HFunction()

    def __init__(self,
                 hwInputT: HdlType,
                 hwOutputT: Union[HdlType, NOT_SPECIFIED]=NOT_SPECIFIED,
                 name: Optional[str]=None,
                 defaultKwargs={},
                 operationRealizationMeta: Optional[OpRealizationMeta]=None):
        super().__init__(hwInputT, hwOutputT=hwOutputT, defaultKwargs=defaultKwargs, name=name, operationRealizationMeta=operationRealizationMeta)
        self.placeholderObjectId: Optional[int] = None
        self._llvmFunction:Optional[Function] = None

    def getFnName(self):
        return f"hwtHls.pyObjectPlaceholder.{self.placeholderObjectId:d}.{self.__class__.__name__:s}.i{self.hwInputT.bit_length():d}"

    def _translateExprHConstHardBlockFunctionDef(self, toLlvm: ToLlvmIrTranslator):
        strCtx = toLlvm.strCtx
        _argTypes = VectorOfTypePtr()
        _argTypes.append(Type.getIntNTy(toLlvm.ctx, 32))
        if self.hasManyInputs:
            for field in self.hwInputT.fields:
                field: HStructField
                t = toLlvm._translateType(field.dtype)
                _argTypes.append(t)
        else:
            t = toLlvm._translateType(self.hwInputT)
            _argTypes.append(t)

        returnType = toLlvm._translateType(self.hwOutputT)
        FT = FunctionType.get(returnType, _argTypes, False)
        name = strCtx.addTwine(self.getFnName())
        F = Function.Create(FT, Function.LinkageTypes.ExternalLinkage, name, toLlvm.module)
        if self.hasManyInputs:
            for field, a in zip(self.hwInputT.fields, F.args()):
                field: HStructField
                assert field.name, self.hwInputT
                a.setName(strCtx.addTwine(field.name))

        return F

    @override
    def translateToLlvm(self, toLlvm: "ToLlvmIrTranslator", b: IRBuilder, args: tuple[Value]) -> CallInst:
        # F = self._llvmFunction
        # if F is None:
        #    F = self.F = self._createLlvmFunctionDef(toLlvm)
        _, F = toLlvm.placeholderObjectSlots[self.placeholderObjectId]
        _args = [toLlvm._translateExprInt(self.placeholderObjectId, Type.getIntNTy(toLlvm.ctx, 32))]
        _args.extend(args)
        calle = FunctionCallee(F)
        res: CallInst = b.CreateCall(calle, _args)
        fn = res.getCalledFunction()
        AddDefaultFunctionAttributes(fn)
        # res.setOnlyAccessesArgMemory()
        res.setDoesNotAccessMemory()
        return res

    @staticmethod
    def _llvmMirToHlsNetlist_cutOfIdAndWidthFromOps(ops: tuple):
        # ops are in foramt $objId id, $resultWidth, inputs,  inputWidths, enCond
        # extract inputs and enCond
        return ops[1 + 1:2 + (len(ops) - 2) // 2], ops[-1]


class ComponentGeneratorForHardBlock(ComponentGenerator):

    @override
    def llvmIrInterpretDecode(self, interpret: LlvmIrInterpret, instr: Instruction,
                          pyObjectPlaceholder: HardBlockHwModule) -> LlvmIrInstrFunction:
        ":note: same as :meth:`ComponentGenerator.llvmIrInterpretDecode` just pyObjectPlaceholder added"
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)

    @override
    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI: MachineRegisterInfo, instr: MachineInstr,
                   pyObjectPlaceholder: HardBlockHwModule) -> LlvmMirInstrFunction:
        ":note: same as :meth:`ComponentGenerator.llvmMirInterpretDecode` just pyObjectPlaceholder added"
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)

    @override
    def _llvmMirToHlsNetlistBuildNode(self,
                                   mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                                   instr: MachineInstr,
                                   ops: MirToHlsNetlistTranslatedInstrOpsT,
                                   pyObjectPlaceholder: HardBlockHwModule,
                                   builder: HlsNetlistBuilder,
                                   resTy: HBits,
                                   inputs: list[HlsNetNodeOutAny]
                                   ):
        op = pyObjectPlaceholder.getComponentGeneratorKey()
        assert isinstance(op, HOperatorDef), (pyObjectPlaceholder, op)
        res = builder.buildOp(op, self.getOperationSpecialization(mirToNetlist, instr, ops, pyObjectPlaceholder), resTy, *inputs)
        return res

    @override
    def llvmMirToHlsNetlist(self,
                            mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                            builder: "HlsNetlistBuilder",
                            mbMeta: "MachineBasicBlockMeta",
                            allBlockingLoadAck: Optional[HlsNetNodeOutAny],
                            name: Optional[str],
                            instr: MachineInstr,
                            dst: Union[Register, tuple[Register]],
                            ops: MirToHlsNetlistTranslatedInstrOpsT,
                            pyObjectPlaceholder: HardBlockHwModule) -> Optional[HlsNetNodeOutAny]:
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        inputs, cond = HardBlockHwModule._llvmMirToHlsNetlist_cutOfIdAndWidthFromOps(ops)
        argCnt = len(inputs)
        if pyObjectPlaceholder.hasManyInputs:
            assert argCnt == len(pyObjectPlaceholder.hwInputT.fields), (inputs, pyObjectPlaceholder.hwInputT)
        else:
            assert argCnt == 1, inputs

        if pyObjectPlaceholder.hasManyOutputs:
            raise NotImplementedError()

        resTy = HBits(mirToNetlist.MRI.getType(dst).getScalarSizeInBits())
        res = self._llvmMirToHlsNetlistBuildNode(mirToNetlist, instr, ops, pyObjectPlaceholder, builder, resTy, inputs)

        res.name = name
        opRealizationMeta = pyObjectPlaceholder.operationRealizationMeta
        if opRealizationMeta:
            res.obj.assignRealization(opRealizationMeta)

        valCache.add(mbMeta.block, dst, res, True)

        return allBlockingLoadAck
