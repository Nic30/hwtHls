from typing import  Tuple, Union, List, Optional

from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.frontend.pyBytecode.blockLabel import BlockLabel
from hwtHls.frontend.pyBytecode.loopsDetect import PyBytecodeLoop
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue


class BranchTargetPlaceholder():
    """
    An object which is put into :class:`SsaInstrBranch` as a jump target placeholder until the jump target block is constructed.
    """

    def __init__(self, block: SsaBasicBlock, index: int):
        self.block = block
        self.index = index
        self._isReplaced = False

    def replace(self, cond: Optional[SsaValue], dstBlock: SsaBasicBlock):
        assert not self._isReplaced, self
        assert cond is None or isinstance(cond, SsaValue), cond
        targets = self.block.successors.targets
        assert targets[self.index] is self, (targets[self.index], self)
        targets[self.index] = (cond, dstBlock)
        src = self.block
        assert src not in dstBlock.predecessors, (src, dstBlock, dstBlock.predecessors)
        dstBlock.predecessors.append(src)
        if cond is not None:
            cond.users.append(self.block.successors)
        else:
            assert len(targets) == self.index + 1
        self._isReplaced = True

    def replaceInput(self, orig_expr: SsaValue, new_expr: Union[SsaValue, HValue]):
        assert isinstance(new_expr, (SsaValue, HValue)), (self, orig_expr, new_expr)
        assert self in orig_expr.users
        self.targets = [
            (new_expr if o is orig_expr else o, t)
            for o, t in self.targets
        ]
        orig_expr.users.remove(self)
        if isinstance(new_expr, SsaValue):
            new_expr.users.append(self)

    @classmethod
    def create(cls, block: SsaBasicBlock) -> "BranchTargetPlaceholder":
        ph = cls(block, len(block.successors.targets))
        block.successors.targets.append(ph)
        return ph

    def __repr__(self):
        return f"<{self.__class__.__name__} from {self.block.label:s} {self.index:d}>"


class PyBytecodeLoopInfo():
    """
    A container of informations about actually evaluated loop.
    This object is used to mark the nodes in the loop and pause code evaluation on loop exit/reenter.
    Once we know all exit jumps after preprocessor evaluation we can then decide if loop iteration scheme
    is controlled by some HW evaluated condition or if it just preprocessor loop.
    
    :ivar loopHeader: offset of a block which is the entry point to the loop
    :ivar loopMembers: a set of offset of blocks in this loop
    :ivar jumpsFromLoopBody: a list of loop body exit jumps and conditions in format of tuple (condition, srcBlock, dstBlockOffset)
    :note: multiple exits can be generated only if there is some HW evaluated branching.
    """

    def __init__(self, loop: PyBytecodeLoop):
        self.loop = loop
        self.iteraionI = 0
        self.mustBeEvaluatedInPreproc = False
        self.jumpsFromLoopBody: List[LoopExitJumpInfo] = []
        self.notGeneratedExits: List[BlockLabel, BlockLabel] = []

    def isJumpFromLoopBody(self, dstBlockOffset: int) -> bool:
        return (dstBlockOffset,) not in self.loop.allBlocks or (dstBlockOffset,) == self.loop.entryPoint
    
    def markJumpFromBodyOfLoop(self, exitInfo: "LoopExitJumpInfo"):
        self.jumpsFromLoopBody.append(exitInfo)

    def markNewIteration(self) -> List[Tuple[Union[None, SsaValue, HValue], SsaBasicBlock, int]]:
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
        if any(isinstance(j.cond, HValue) or isinstance(j.cond, SsaValue) for j in self.jumpsFromLoopBody):
            return True
        return False

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.loop.label:s} i{self.iteraionI:d}>"

    
class LoopExitJumpInfo():
    """
    Temporary container for a jump from the loop where preprocessor should continue once all jumps from loop are resolved.
    """

    def __init__(self, dstBlockIsNew: Optional[bool],
                 srcBlock: SsaBasicBlock,
                 cond: Optional[SsaValue],
                 dstBlock: Optional[SsaBasicBlock],
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
        return f"<{self.__class__.__name__} {self.srcBlock.label:s} -> {dst}, c={self.cond}>"

   
class LoopExitRegistry():
    """
    :ivar exitPoints: list of points where CFG leaves the loop body in format: condition, srcBlock, dstBlockOffset
    
    :note: The loop is HW loop if there are multiple jump destination locations from the body of the loop after pre-processing.
        There may be multiple jump destinations in general and this still can be just preprocessor loop but if there
        are multiple jump destinations after pre-processing it means that the loop iteration scheme is driven by HW condition.

    """

    def __init__(self):
        self.exitPoints: List[Tuple[Union[SsaValue, HValue, RtlSignalBase, None], SsaBasicBlock, int]] = []

    def isHwLoop(self):
        return len(set(dstOffset for _, _, dstOffset in self.exitPoints))
