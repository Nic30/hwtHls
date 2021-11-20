
# from hwtHls.llvm.toLlvm import initializeModule
from typing import List, Tuple, Dict, Union

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.value import HValue
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.llvm.toLlvm import LLVMContext, Module, IRBuilder, LLVMStringContext, IntegerType, \
    Type, FunctionType, Function, VectorOfTypePtr, BasicBlock
from hwtHls.ssa.value import SsaValue


class LlvmIrBundle():
    """
    A container class which contains all necessary objects for LLVM.
    It can also translate between hwtHls SSA and LLVM SSA (in bouth directions).

    While converting there are several issues:
    1. LLVM does not have multi level logic type like vhdl STD_LOGIC_VECTOR or verilog wire/logic.
      * all x/z/u are replaced with 0
    2. LLVM does not have bit slicing and concatenation operators.
      * all replaced by shifting and masking
    3. LLVM does not have equivalent of HlsRead/HlsWrite
      * all read/write expressions are replaced with a function unique for each interface.
    """

    def __init__(self, name):
        self.ctx = LLVMContext()
        self.strCtx = LLVMStringContext()
        self.mod = Module(self.strCtx.addStringRef(name), self.ctx)
        self.b = IRBuilder(self.ctx)

    def _initOperatorConstructorMap(self):
        self._opConstructorMap = {
            AllOps.AND: self.b.CreateAnd,
            AllOps.OR: self.b.CreateOr,
            AllOps.XOR: self.b.CreateXor,

            AllOps.ADD: self.b.CreateXdd,
            AllOps.SUB: self.b.CreateSub,
            AllOps.MUL: self.b.CreateMul,
        }

    def createFunctionPrototype(self, name: str, args:List[Tuple[Type, str]], returnType: Type):
        strCtx = self.strCtx
        _argTypes = VectorOfTypePtr()
        for t, _ in args:
            _argTypes.push_back(t)

        FT = FunctionType.get(returnType, _argTypes, False)
        F = Function.Create(FT, Function.ExternalLinkage, strCtx.addTwine(name), self.mod)

        for a, (_, aName) in zip(F.args(), args):
            a.setName(strCtx.addTwine(aName))

        return F

    def _translateToLlvmExpr(self, v: Union[SsaValue, HValue]):
        if isinstance(v, HValue):
            pass
        raise NotImplementedError()

    def _translateToLlvmInstr(self, instr: SsaInstr):
        constructor_fn = self._opConstructorMap[instr.src[0]]
        args = (self._translateToLlvmExpr(a) for a in instr.src[1])
        constructor_fn(*args, self.strCtx.addTwine(instr._name), False, False)

    def _translateToLlvm(self, fn: Function, bb: SsaBasicBlock, seen_blocks: Dict[SsaBasicBlock, BasicBlock]):
        llvm_bb = BasicBlock.Create(self.ctx, self.strCtx.addTwine(bb.label), fn, None)
        prev = seen_blocks.setdefault(bb, llvm_bb)
        assert prev is llvm_bb, (bb, "was already converted before", prev, llvm_bb)
        self.b.SetInsertPoint(llvm_bb)

        for phi in bb.phis:
            raise NotImplementedError(phi)

        for instr in bb.body:
            self._translateInstr(instr)

        for suc in bb.successors.iter_blocks():
            if suc not in seen_blocks:
                self._translateToLlvm(fn, suc, seen_blocks)

    def translateToLlvm(self, start_bb: SsaBasicBlock):
        # create a function where we place the code
        main = self.createFunctionPrototype("main", [], [], Type.getVoidTy(self.ctx))
        seen_blocks = {}
        self._translateToLlvm(main, start_bb, seen_blocks)
        return self

# print(ctx, mod, b, i1, i8)

# b = SsaBasicBlock("top")
# b.body.append(SsaInstr(HlsTmpVariable("v0", None), [AllOps.ADD, [uint32_t.from_py(1), uint32_t.from_py(2)]]))
#
# initializeModule(b)
