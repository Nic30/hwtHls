from copy import copy
from dis import Instruction, _get_instructions_bytes, findlinestarts
import inspect
from networkx.classes.digraph import DiGraph
from types import FunctionType
from typing import Dict, Set, Tuple, List, Optional

from hwtHls.frontend.pyBytecode.blockPredecessorTracker import BlockPredecessorTracker
from hwtHls.frontend.pyBytecode.bytecodeBlockAnalysis import extractBytecodeBlocks
from hwtHls.frontend.pyBytecode.loopMeta import PyBytecodeLoopInfo, \
    LoopExitJumpInfo
from hwtHls.frontend.pyBytecode.loopsDetect import PyBytecodeLoop
from hwtHls.ssa.basicBlock import SsaBasicBlock


class _PyBytecodeUnitialized():

    def __init__(self):
        raise AssertionError("This class should be used as a constant")


class PyBytecodeFrame():
    """
    This object is a container of data for currently evaluated Python function. 

    :ivar fn: function which is this frame for
    :ivar loopStack: stack of currently executed loops which are currently executed in preprocessor,
        used when generating unique labels for blocks in preprocessor loop
    :ivar preprocVars: set of indexes of variables which are marked as a preprocessor variable
    :ivar instructions: instructions parsed from bytecode of a function
    :ivar bytecodeBlocks: instructions formated to a basic blocks
    :ivar blockTracker: an object to keep track of predecessor blocks in the function
        used in SSA construction to detect that we know all predecessors of some block so we can seal it 
    :ivar loops: a dictionary mapping header block offset to a loop list
    :ivar locals: list where local variables are stored
    :ivar cellVarI: a dictionary mapping a index of cell variable to index in locals list
    :ivar stack: a stack of Python interpret in preprocessor
    :ivar returnPoints: a list of tuples specifying the return from this function
    :note: record in returnPoints contains frame because due to HW evaluated conditions there may be multiple
        return points each with a different frame object
    """

    def __init__(self, fn: FunctionType,
                 instructions: Tuple[Instruction, ...],
                 bytecodeBlocks: Dict[int, List[Instruction]],
                 loops: Dict[int, List["PyBytecodeLoop"]],
                 cellVarI: Dict[int, int],
                 locals_: list,
                 stack: list):
        self.fn = fn
        self.loopStack: List[PyBytecodeLoopInfo] = []
        self.preprocVars: Set[int] = set()
        self.instructions: Tuple[Instruction, ...] = instructions
        self.bytecodeBlocks = bytecodeBlocks
        self.blockTracker: Optional[BlockPredecessorTracker] = None
        self.loops = loops
        self.locals = locals_
        self.cellVarI = cellVarI
        self.stack = stack
        self.returnPoints: List[Tuple[PyBytecodeFrame, SsaBasicBlock, tuple]] = []
 
    def constructBlockTracker(self, cfg: DiGraph, callStack: List["PyBytecodeFrame"]):
        self.blockTracker = BlockPredecessorTracker(cfg, callStack)

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

    # @classmethod
    # def fromCallSite(cls, parentFrame: "PyBytecodeFrame", fn: FunctionType, fnArgs: tuple, fnKwargs: dict):
    #    pass
    @classmethod
    def fromFunction(cls, fn: FunctionType, fnArgs: tuple, fnKwargs: dict, callStack: List["PyBytecodeFrame"]):
        co = fn.__code__
        localVars = [_PyBytecodeUnitialized for _ in range(fn.__code__.co_nlocals)]
        if inspect.ismethod(fn):
            fnArgs = tuple((fn.__self__, *fnArgs))

        assert len(fnArgs) == co.co_argcount, ("Function call must have the correct number of arguments",
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

        cell_names = co.co_cellvars + co.co_freevars
        linestarts = dict(findlinestarts(co))
        instructions = tuple(_get_instructions_bytes(
            co.co_code, co.co_varnames, co.co_names,
            co.co_consts, cell_names, linestarts))
        bytecodeBlocks, cfg = extractBytecodeBlocks(instructions)
        loops = PyBytecodeLoop.collectLoopsPerBlock(cfg)
        frame = PyBytecodeFrame(fn, instructions, bytecodeBlocks,
                               loops, cellVarI, localVars, [])

        callStack.append(frame)
        frame.constructBlockTracker(cfg, callStack)
        return frame

    def __copy__(self):
        o = self.__class__(self.fn, self.instructions, self.bytecodeBlocks,
                           self.loops, self.cellVarI,
                           copy(self.locals), copy(self.stack))
        o.loopStack = self.loopStack
        o.preprocVars = self.preprocVars
        o.bytecodeBlocks = self.bytecodeBlocks
        o.blockTracker = self.blockTracker
        o.returnPoints = self.returnPoints
        return o

