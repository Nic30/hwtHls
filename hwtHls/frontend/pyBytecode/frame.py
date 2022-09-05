from copy import copy
from dis import Instruction, _get_instructions_bytes, findlinestarts
import inspect
from networkx.classes.digraph import DiGraph
from types import FunctionType, CellType
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

    def __init__(self, fn: FunctionType, callSiteAddress: int,
                 instructions: Tuple[Instruction, ...],
                 bytecodeBlocks: Dict[int, List[Instruction]],
                 loops: Dict[int, List["PyBytecodeLoop"]],
                 locals_: list,
                 freevars: List[CellType],
                 stack: list):
        self.fn = fn
        self.callSiteAddress = callSiteAddress
        self.loopStack: List[PyBytecodeLoopInfo] = []
        self.preprocVars: Set[int] = set()
        self.instructions: Tuple[Instruction, ...] = instructions
        self.bytecodeBlocks = bytecodeBlocks
        self.blockTracker: Optional[BlockPredecessorTracker] = None
        self.loops = loops
        self.locals = locals_
        self.freevars = freevars
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

    @classmethod
    def fromFunction(cls, fn: FunctionType, callSiteAddress: int, fnArgs: tuple, fnKwargs: dict, callStack: List["PyBytecodeFrame"]):
        """
        :note: based on cpython/Python/ceval.c/_PyEval_MakeFrameVector
        """
        if isinstance(fn, staticmethod):
            fn = fn.__func__
        co = fn.__code__
        localVars = [_PyBytecodeUnitialized for _ in range(fn.__code__.co_nlocals)]
        if inspect.ismethod(fn):
            fnArgs = list((fn.__self__, *fnArgs))
            defaults = [fn.__func__.__defaults__, fn.__func__.__kwdefaults__]
        else:
            fnArgs = list(fnArgs)
            defaults = [fn.__defaults__, fn.__kwdefaults__]

        for defs in defaults:
            if defs:
                fnArgs.extend(defs)
        assert len(fnArgs) == co.co_argcount, ("Function call must have the correct number of arguments",
                                               len(fnArgs), co.co_argcount)
        if fnKwargs:
            for k, v in fnKwargs.items():
                fnArgs[co.co_varnames.index(k)] = v

        for i, argVal in enumerate(fnArgs):
            localVars[i] = argVal 

        freevars = []
        if co.co_cellvars:
            argToI = {argName: i for i, argName in enumerate(co.co_varnames[:co.co_argcount])}
            # cellvars:  names of local variables that are referenced by nested functions
            # freevars: all non local variables, the cellvars are prefix of freevars 
            # Allocate and initialize storage for cell vars, and copy free vars into frame.
            for cellVarName in co.co_cellvars:
                # Possibly account for the cell variable being an argument.
                argI = argToI.get(cellVarName, None)
                if argI is not None:
                    cellVarVal = localVars[argI]
                    # Clear the local copy.
                    localVars[argI] = _PyBytecodeUnitialized
                else:
                    cellVarVal = _PyBytecodeUnitialized
                freevars.append(CellType(cellVarVal))
        
        # Copy closure variables to free variables
        if fn.__closure__:
            freevars.extend(fn.__closure__)

        cell_names = co.co_cellvars + co.co_freevars
        linestarts = dict(findlinestarts(co))
        instructions = tuple(_get_instructions_bytes(
            co.co_code, co.co_varnames, co.co_names,
            co.co_consts, cell_names, linestarts))
        bytecodeBlocks, cfg = extractBytecodeBlocks(instructions)
        cfg: DiGraph
        if callSiteAddress ==-1:
            # connect to entry point block
            cfg.add_edge((-1, ), (0, ))
        loops = PyBytecodeLoop.collectLoopsPerBlock(cfg)
        frame = PyBytecodeFrame(fn, callSiteAddress, instructions, bytecodeBlocks,
                               loops, localVars, freevars, [])

        callStack.append(frame)
        frame.constructBlockTracker(cfg, callStack)
        return frame

    def __copy__(self):
        o = self.__class__(self.fn, self.callSiteAddress, self.instructions, self.bytecodeBlocks, self.loops,
                           copy(self.locals), self.freevars, copy(self.stack))
        o.loopStack = self.loopStack
        o.preprocVars = self.preprocVars
        o.bytecodeBlocks = self.bytecodeBlocks
        o.blockTracker = self.blockTracker
        o.returnPoints = self.returnPoints
        return o

