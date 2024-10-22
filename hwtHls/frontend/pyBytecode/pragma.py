from dis import Instruction
from typing import Union, Optional, Tuple

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.array import HArray
from hwt.hdl.types.function import HFunctionConst, HFunction
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hwIO import HwIO
from hwt.mainBases import RtlSignalBase
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.frontend.pyBytecode.loopMeta import PyBytecodeLoopInfo
from hwtHls.llvm.llvmIr import BranchInst, Value, IRBuilder
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr


class _PyBytecodePragma():

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        raise NotImplementedError()


class _PyBytecodeIntrinsic(HFunctionConst):
    """
    :cvar __hlsIsLowLevelFn: a constant flag which tells pybytecode frontend that this object call will translate this object
    :cvar _dtype: constant attribute holding type of HFunction
    :ivar val: name used for user to better identify object in LLVM and netlist
    :ivar hwInputT: type of hardware inputs
    :ivar hwOutputT: type of hardware outputs
    :ivar vld_mask: constant 1 to complete  HFunctionConst attributes
    """
    __hlsIsLowLevelFn = True
    _dtype = HFunction()

    def __init__(self,
                 hwInputT: HdlType,
                 hwOutputT: Union[HdlType, NOT_SPECIFIED]=NOT_SPECIFIED,
                 name: Optional[str]=None,
                 operationRealizationMeta: Optional[OpRealizationMeta]=None):
        if name is None:
            name = self.__class__.__name__
        assert isinstance(hwInputT, HdlType), hwInputT
        if hwOutputT is NOT_SPECIFIED:
            hwOutputT = hwInputT
        else:
            assert isinstance(hwOutputT, HdlType), hwOutputT
        self.hwInputT = hwInputT
        self.hwOutputT = hwOutputT
        self.hasManyInputs = isinstance(hwInputT, (HStruct, HArray))
        self.hasManyOutputs = isinstance(hwOutputT, (HStruct, HArray))
        # there is a single instance of this const and we can not use self as a val because it would result
        # in infinite cycle during cmp
        self.val = name
        self.vld_mask = 1
        self.operationRealizationMeta = operationRealizationMeta

    def __call__(self, *args, **kwargs):
        """
        Construct the HWT call expression for later translation to LLVM
        """
        if self.hasManyInputs:
            raise NotImplementedError()
        else:
            assert not kwargs, kwargs
            assert len(args) <= 1, args

        if self.hasManyOutputs:
            raise NotImplementedError()
        else:
            return HOperatorNode.withRes(HwtOps.CALL, [self, *args], self.hwOutputT)

    def translateToLlvm(self, b: IRBuilder, args: Tuple[Value]):
        raise NotImplementedError("Implement this method in child class")


class _PyBytecodeInstructionPragma(_PyBytecodePragma):

    def __init__(self, variable: Union["SsaInstr", RtlSignalBase, HwIO]):
        _PyBytecodePragma.__init__(self)
        if isinstance(variable, HwIO):
            try:
                variable = variable._sig
            except:
                raise AssertionError(self.__class__, "expected flat HwIO, RtlSignal or SsaInstr", variable)
        self.varTmp = variable

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        # add self to metadata of reference variable
        v = pyToSsa.toSsa.m_ssa_u.readVariable(self.varTmp, curBlock)
        assert isinstance(v, SsaInstr), v
        if v.metadata is None:
            v.metadata = [self, ]
        else:
            v.metadata.append(self)

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", origInstr: SsaInstr, v: Value):
        raise NotImplementedError("This is abstract class override this method")


class _PyBytecodeLoopPragma(_PyBytecodePragma):
    """
    A type of pragma which is applied to a loop.
    """

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        assert frame.loopStack, "This pragma needs to be placed in the loop"
        loop: PyBytecodeLoopInfo = frame.loopStack[-1]
        loop.pragma.append(self)

    def getLlvmLoopMetadataItems(self, irTranslator: "ToLlvmIrTranslator"):
        raise NotImplementedError("This is abstract class override this method")

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", brInst: BranchInst):
        items = self.getLlvmLoopMetadataItems(irTranslator)
        getTuple = irTranslator.mdGetTuple
        llvmLoopMdStr = irTranslator.strCtx.addStringRef("llvm.loop")

        llvmLoopMd = brInst.getMetadata(llvmLoopMdStr)
        assert llvmLoopMd is None, (
            "There can be only one llvm.loop per loop,"
            " multiple loop metadata should be added trough llvm.loop.*.followup*")

        llvmLoopMd = getTuple(items, True)
        brInst.setMetadata(llvmLoopMdStr, llvmLoopMd)


class _PyBytecodeFunctionPragma(_PyBytecodePragma):

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        frame.pragma.append(self)

