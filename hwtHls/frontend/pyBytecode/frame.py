from copy import copy
from dis import Instruction, _get_instructions_bytes, findlinestarts
import inspect
from types import FunctionType
from typing import Dict, Set, Tuple, List, Optional

from hwtHls.frontend.pyBytecode.blockLabel import BlockLabel
from hwtHls.frontend.pyBytecode.blockPredecessorTracker import BlockPredecessorTracker
from hwtHls.frontend.pyBytecode.bytecodeBlockAnalysis import extractBytecodeBlocks
from hwtHls.frontend.pyBytecode.loopMeta import PyBytecodeLoopInfo, \
    LoopExitJumpInfo
from hwtHls.frontend.pyBytecode.loopsDetect import PyBytecodeLoop
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.frontend.pyBytecode.instructions import NULL


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
    :ivar stack: a stack of Python interpret in preprocessor
    :ivar returnPoints: a list of tuples specifying the return from this function
    :note: record in returnPoints contains frame because due to HW evaluated conditions there may be multiple
        return points each with a different frame object
    """

    def __init__(self, fn: FunctionType, callSiteAddress: int,
                 instructions: Tuple[Instruction, ...],
                 bytecodeBlocks: Dict[int, List[Instruction]],
                 loops: Dict[int, List["PyBytecodeLoop"]],
                 localsplus: list,
                 stack: list):
        self.fn = fn
        self.callSiteAddress = callSiteAddress
        self.loopStack: List[PyBytecodeLoopInfo] = []
        self.preprocVars: Set[int] = set()
        self.instructions: Tuple[Instruction, ...] = instructions
        self.bytecodeBlocks = bytecodeBlocks
        self.blockTracker: Optional[BlockPredecessorTracker] = None
        self.loops = loops
        self.localsplus = localsplus
        self.stack = stack
        self.returnPoints: List[Tuple[PyBytecodeFrame, SsaBasicBlock, tuple]] = []

    def isJumpFromCurrentLoopBody(self, dstBlockOffset: int) -> bool:
        return self.loopStack and self.loopStack[-1].isJumpFromLoopBody(dstBlockOffset)

    def enterLoop(self, loop: PyBytecodeLoop):
        assert not self.isLoopReenter(loop), ("New iteration of same loop of already iterating loop in same function can not happen", loop)
        self.loopStack.append(PyBytecodeLoopInfo(loop))

    def exitLoop(self):
        self.loopStack.pop()

    def isLoopReenter(self, loop: PyBytecodeLoop) -> bool:
        """
        :return: True if this loop is already being iterated.
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
    def fromFunction(cls, fn: FunctionType, predecessorBlockLabel: BlockLabel, callSiteAddress: int,
                     fnArgs: tuple, fnKwargs: dict, callStack: List["PyBytecodeFrame"]):
        """
        :note: based on cpython/Python/ceval.c/_PyEvalFramePushAndInit
        """
        
        if isinstance(fn, staticmethod):
            fn = fn.__func__

        # https://docs.python.org/3/library/inspect.html
        co = fn.__code__
        # anyArgCnt = co.co_argcount + co.co_kwonlyargcount
        # trueLocalsCnt = anyArgCnt + co.co_nlocals
        argAndLocalVarCnt = len(co.co_varnames) # args and directly used locals
        plainCellVarCnt = sum(1 for n in co.co_cellvars if n not in co.co_varnames) # to child closures
        freeVarCnt = len(co.co_freevars) # from parent closure
        localsplus = [NULL for _ in range(argAndLocalVarCnt + plainCellVarCnt + freeVarCnt)]
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
                                               fn, len(fnArgs), co.co_argcount)
        if fnKwargs:
            for k, v in fnKwargs.items():
                fnArgs[co.co_varnames.index(k)] = v

        for i, argVal in enumerate(fnArgs):
            localsplus[i] = argVal

        linestarts = dict(findlinestarts(co))
        instructions = tuple(_get_instructions_bytes(co.co_code,
            varname_from_oparg=co._varname_from_oparg,
            names=co.co_names, co_consts=co.co_consts,
            linestarts=linestarts,
            co_positions=co.co_positions()))
        
        bytecodeBlocks, fnCfg = extractBytecodeBlocks(instructions)
        loops = PyBytecodeLoop.collectLoopsPerBlock(fnCfg)
        
        frame = PyBytecodeFrame(fn, callSiteAddress, instructions, bytecodeBlocks,
                               loops, localsplus, [])

        callStack.append(frame)
        frame.blockTracker = BlockPredecessorTracker(fnCfg, predecessorBlockLabel, callStack)

        return frame

    def __copy__(self):
        o = self.__class__(self.fn, self.callSiteAddress, self.instructions, self.bytecodeBlocks, self.loops,
                           copy(self.localsplus), copy(self.stack))
        o.loopStack = self.loopStack
        o.preprocVars = self.preprocVars
        o.bytecodeBlocks = self.bytecodeBlocks
        o.blockTracker = self.blockTracker
        o.returnPoints = self.returnPoints
        return o

