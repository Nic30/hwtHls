from copy import copy
import inspect
from types import FunctionType
from typing import Dict, Set, Tuple, Union, List, Optional

from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.frontend.pyBytecode.blockLabel import BlockLabel
from hwtHls.frontend.pyBytecode.loopsDetect import PyBytecodeLoop
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue


class BranchTargetPlaceholder():

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
            cond.users.append(self)
        else:
            assert len(targets) == self.index + 1
        self._isReplaced = True
        
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


class PyBytecodeFrame():
    """
    This object is a container of data for currently evaluated Python function. 
    """

    def __init__(self, locals_: list, cellVarI: Dict[int, int], stack: list):
        self.locals = locals_
        self.stack = stack
        self.cellVarI = cellVarI
        self.loopStack: List[PyBytecodeLoopInfo] = []
        self.preprocVars: Set[int] = set() 

    def isJumpFromCurrentLoopBody(self, dstBlockOffset: int) -> bool:
        return self.loopStack and self.loopStack[-1].isJumpFromLoopBody(dstBlockOffset)
    
    def enterLoop(self, loop: PyBytecodeLoop):
        assert not self.isLoopReenter(loop), ("New iteration of same loop of already iterating loop in same function can not happen", loop)
        self.loopStack.append(PyBytecodeLoopInfo(loop))

    def exitLoop(self):
        self.loopStack.pop()

    def isLoopReenter(self, loop: PyBytecodeLoop) -> bool:
        """
        :returns: True if this loop is already being iterated.
        """
        for li in self.loopStack:
            li: PyBytecodeLoopInfo
            if li.loop is loop:
                return True
        return False
        
    def markJumpFromBodyOfCurrentLoop(self, loopExitJumpInfo: LoopExitJumpInfo):
        """
        :note: The jump can still be jump also from some parent loop, we need to copy it later to parent loop info. 
        """
        assert isinstance(loopExitJumpInfo, LoopExitJumpInfo)
        self.loopStack[-1].markJumpFromBodyOfLoop(loopExitJumpInfo)

    def __copy__(self):
        o = self.__class__(copy(self.locals), self.cellVarI, copy(self.stack))
        o.loopStack = self.loopStack
        o.preprocVars = self.preprocVars
        return o

    @classmethod
    def fromFunction(cls, fn: FunctionType, fnArgs: tuple, fnKwargs: dict):
        co = fn.__code__
        localVars = [None for _ in range(fn.__code__.co_nlocals)]
        if inspect.ismethod(fn):
            fnArgs = tuple((fn.__self__, *fnArgs))

        assert len(fnArgs) == co.co_argcount, ("Must have the correct number of arguments",
                                               len(fnArgs), co.co_argcount)
        for i, v in enumerate(fnArgs):
            localVars[i] = v
        if fnKwargs:
            raise NotImplementedError()

        varNameToI = {n: i for i, n in enumerate(fn.__code__.co_varnames)}
        cellVarI = {}
        # cellvars:  names of local variables that are referenced by nested functions
        for i, name in enumerate(fn.__code__.co_cellvars):
            # variables accessed using LOAD_DEREF/STORE_DEREF LOAD_CLOSURE/STORE_CLOSURE
            index = varNameToI.get(name, None)
            if index is None:
                # cell var which is not local, we allocate extra space in locals 
                index = len(localVars)
                localVars.append(None)

            cellVarI[i] = index

        return PyBytecodeFrame(localVars, cellVarI, [])

