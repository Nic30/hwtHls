from typing import  Tuple, Union, List, Optional, Literal, Callable

from hwt.hdl.const import HConst
from hwt.mainBases import RtlSignalBase
from hwtHls.frontend.pyBytecode.loopsDetect import PyBytecodeLoop
from hwtHls.llvm.llvmIr import Value, BasicBlock, Constant, ValueToConstantInt, \
    InstructionToBranchInst, ConstantInt, APInt


class BranchTargetPlaceholder():
    """
    An object which is put into :class:`SsaInstrBranch` as a jump target placeholder until the jump target block is constructed.
    """

    def __init__(self, block: BasicBlock, jumpPlaceholderBlock: BasicBlock):
        self.block = block
        self.jumpPlaceholderBlock = jumpPlaceholderBlock
        self._isReplaced = False

    def replace(self, dstBlock: BasicBlock):
        assert not self._isReplaced, self
        self.jumpPlaceholderBlock.replaceAllUsesWith(dstBlock)
        self.jumpPlaceholderBlock.eraseFromParent()
        self._isReplaced = True

    @staticmethod
    def appendSuccessor(toLlvm: "ToLlvmIrTranslator", curBlock: BasicBlock, cond: Optional[Value], sucBlock: BasicBlock) -> Optional[Value]:
        # if this is a jump out of current loop
        if isinstance(cond, HConst):
            assert cond, (
                "If this was not True the jump should not be evaluated at the first place",
                curBlock, "->", sucBlock)
            cond = None  # always jump, but we need this value to know that this will be unconditional jump only in HW
        elif isinstance(cond, Constant):
            cond = ValueToConstantInt(cond)
            assert int(cond.getValue().getZExtValue()), (
                "If this was not True the jump should not be evaluated at the first place",
                curBlock, "->", sucBlock)
            cond = None

        ter = curBlock.getTerminator()
        if ter is None:
            b = toLlvm.b
            b.SetInsertPoint(curBlock)
            if cond is None:
                b.CreateBr(sucBlock)
            else:
                w = cond.getType().getIntegerBitWidth()
                if w != 1:
                    cond = b.CreateICmpNE(cond, ConstantInt.get(cond.getType(), APInt.getZero(w)), toLlvm.strCtx.addTwine(""))
                b.CreateCondBr(cond, sucBlock, sucBlock, None)
        else:
            br = InstructionToBranchInst(ter)
            assert br, ter
            assert br.isConditional()
            assert cond is None, cond
            assert br.getSuccessor(0) == br.getSuccessor(1), br
            br.setSuccessor(1, sucBlock)

        return cond

    @classmethod
    def create(cls, toLlvm: "ToLlvmIrTranslator", block: BasicBlock, cond: Optional[Value]) -> "BranchTargetPlaceholder":
        placeholderBlock = BasicBlock.Create(toLlvm.ctx, toLlvm.strCtx.addTwine("placeholder"), toLlvm.llvm.main, None)
        ph = cls(block, placeholderBlock)
        cls.appendSuccessor(toLlvm, block, cond, placeholderBlock)
        return ph

    def __repr__(self):
        return f"<{self.__class__.__name__} from {self.block.label:s} {self.index:d}>"


class PyBytecodeLoopInfo():
    """
    A container of informations about actually evaluated loop.
    This object is used to mark the nodes in the loop and pause code evaluation on loop exit/reenter.
    Once we know all exit jumps after preprocessor evaluation we can then decide if loop iteration scheme
    is controlled by some HW evaluated condition or if it just preprocessor loop.
    
    :ivar jumpsFromLoopBody: a list of loop body exit jumps and conditions in format of tuple (condition, srcBlock, dstBlockOffset)
    :note: multiple exits can be generated only if there is some HW evaluated branching.
    :ivar pragma: list of pragma instances collected for this loop
    """

    def __init__(self, loop: PyBytecodeLoop):
        self.loop = loop
        self.iteraionI = 0
        self.mustBeEvaluatedInPreproc = False
        self.jumpsFromLoopBody: List[LoopExitJumpInfo] = []
        self.pragma: List["_PyBytecodeLoopPragma"] = []
        self.additionalLatchBlock: Optional[BasicBlock] = None
        self.onAdditionalLatchBlockPredecessorsAdded: Optional[Callable[["PyBytecodeFrame", BasicBlock]]] = None

    def isJumpFromLoopBody(self, dstBlockOffset: int) -> bool:
        return dstBlockOffset not in self.loop.allBlocks or dstBlockOffset == self.loop.entryPoint

    def markJumpFromBodyOfLoop(self, exitInfo: "LoopExitJumpInfo"):
        self.jumpsFromLoopBody.append(exitInfo)

    def markNewIteration(self) -> List[Tuple[Union[None, Value, HConst], BasicBlock, int]]:
        self.iteraionI += 1
        jumpsFromLoopBody = self.jumpsFromLoopBody
        self.jumpsFromLoopBody = []
        return jumpsFromLoopBody

    def mustBeEvaluatedInHw(self) -> bool:
        """
        if there are multiple src blocks or the jump depends on hw evaluated condition this loop must be evaluated in HW
        """
        if self.mustBeEvaluatedInPreproc:
            return False
        if len(set((j.srcBlock, j.dstBlockOffset) for j in self.jumpsFromLoopBody)) > 1:
            return True
        if any(isinstance(j.cond, HConst) or isinstance(j.cond, Value) for j in self.jumpsFromLoopBody):
            # condition is of hardware type
            return True
        return False

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.loop.label:s} i{self.iteraionI:d}>"


class LoopExitJumpInfo():
    """
    Temporary container for a jump from the loop where preprocessor should continue once all jumps from loop are resolved.
    
    :ivar cond: A condition value which is triggering this CFG transition. None means always triggered. False means never triggered.
        Otherwise Value can be used to specify any other condition.
    """

    def __init__(self, dstBlockIsNew: Optional[bool],
                 srcBlock: BasicBlock,
                 cond: Union[Value, None, Literal[False]],
                 dstBlock: Optional[BasicBlock],
                 dstBlockOffset:int,
                 dstBlockLoops: Optional[List[PyBytecodeLoopInfo]],
                 isExplicitLoopReenter: Optional[bool],
                 branchPlaceholder: Optional[BranchTargetPlaceholder],
                 frame: "PyBytecodeFrame"):
        self.dstBlockIsNew = dstBlockIsNew
        self.srcBlock = srcBlock
        self.cond = cond
        self.dstBlock = dstBlock
        self.dstBlockOffset = dstBlockOffset
        self.dstBlockLoops = dstBlockLoops
        self.isExplicitLoopReenter = isExplicitLoopReenter
        self.branchPlaceholder = branchPlaceholder
        self.frame = frame

    def __repr__(self):
        if self.dstBlock is None:
            dst = self.dstBlockOffset
        else:
            dst = self.dstBlockOffset

        return f"<{self.__class__.__name__} {self.srcBlock.getName().str():s} -> {dst}, c={self.cond}>"


class LoopExitRegistry():
    """
    :ivar exitPoints: list of points where CFG leaves the loop body in format: condition, srcBlock, dstBlockOffset
    
    :note: The loop is HW loop if there are multiple jump destination locations from the body of the loop after pre-processing.
        There may be multiple jump destinations in general and this still can be just preprocessor loop but if there
        are multiple jump destinations after pre-processing it means that the loop iteration scheme is driven by HW condition.

    """

    def __init__(self):
        self.exitPoints: List[Tuple[Union[Value, HConst, RtlSignalBase, None], BasicBlock, int]] = []

    def isHwLoop(self):
        return len(set(dstOffset for _, _, dstOffset in self.exitPoints))
