from dis import Instruction, dis
import sys
from types import FunctionType
from typing import Optional, Dict, List

from hwtHls.errors import HlsSyntaxError
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode.blockLabel import BlockLabel
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame, \
    PyBytecodeLoopInfo
from hwtHls.frontend.pyBytecode.fromPythonLowLevelOpcodes import PyBytecodeToSsaLowLevelOpcodes
from hwtHls.frontend.pyBytecode.loopsDetect import PreprocLoopScope
from hwtHls.scope import HlsScope
from hwtHls.ssa.basicBlock import SsaBasicBlock


# from types import CellType
class SsaBlockGroup():
    """
    Represents a set of block for a specific block label.
    """

    def __init__(self, begin: SsaBasicBlock):
        self.begin = begin
        self.end = begin


class PyBytecodeToSsaLowLevel(PyBytecodeToSsaLowLevelOpcodes):

    def __init__(self, hls: HlsScope, label: str):
        super(PyBytecodeToSsaLowLevel, self).__init__()
        assert sys.version_info >= (3, 10, 0), ("Python3.10 is minimum requirement", sys.version_info)
        self.hls = hls
        self.label = label
        self.toSsa: Optional[HlsAstToSsa] = None
        self.blockToLabel: Dict[SsaBasicBlock, BlockLabel] = {}
        self.labelToBlock: Dict[BlockLabel, SsaBlockGroup] = {}
        self.callStack: List[PyBytecodeFrame] = []
        self.debug = False
        self.debugGraphCntr = 0

    # https://www.synopsys.com/blogs/software-security/understanding-python-bytecode/
    def translateFunction(self, fn: FunctionType, *fnArgs, **fnKwargs):
        """
        Translate bytecode of a Python function to :mod:`hwtHls.ssa`

        The input function may have features which should be evaluated during compile time
        and the rest should be translate to SSA for hardware compilation.
        We can not simply run preprocessor on a function because we know that instruction should be
        evaluated compile time only after we resolve its arguments.
        However in order to resolve all arguments we have to translate whole code.
        Because of this we must run preprocessor while translating the code and because of
        that a single basic block from Python can generate multiple basic blocks in SSA.
        And because of this the jump addresses may change.

        :ivar fn: function to translate
        :ivar fnArgs: positional arguments for function fn
        :ivar fnKwargs: keyword arguments for function fn
        """
        if self.debug:
            with open(f"tmp/{self.label:s}_cfg_bytecode.txt", "w") as f:
                dis(fn, file=f)

        frame = PyBytecodeFrame.fromFunction(fn, -1, fnArgs, fnKwargs, self.callStack)
        self.toSsa = HlsAstToSsa(self.hls.ssaCtx, getattr(fn, "__qualname__", fn.__name__), None)
        self._debugDump(frame, "_begin")

        entryBlock = self.toSsa.start
        entryBlockLabel = self.blockToLabel[entryBlock] = frame.blockTracker._getBlockLabel(-1)
        self.labelToBlock[entryBlockLabel] = SsaBlockGroup(entryBlock)

        try:
            self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, entryBlock, 0, None, None, True)
            # self._onBlockGenerated(frame, entryBlockLabel)
            assert not frame.loopStack, ("All loops must be exited", frame.loopStack)
        finally:
            self._debugDump(frame, "_final")

        assert len(self.callStack) == 1 and self.callStack[0] is frame, self.callStack
        self.toSsa.finalize()

    def _debugDump(self, frame: PyBytecodeFrame, label=None):
        if self.debug:
            with open(f"tmp/{self.label:s}_cfg_{self.debugGraphCntr:d}{label if label else ''}.dot", "w") as f:
                sealedBlocks = set(self.blockToLabel[b] for b in self.toSsa.m_ssa_u.sealedBlocks)
                frame.blockTracker.dumpCfgToDot(f, sealedBlocks)
                self.debugGraphCntr += 1

    @classmethod
    def _strFormaBlockLabelItem(cls, item):
        if isinstance(item, PreprocLoopScope):
            name = str(item)
        elif isinstance(item, tuple):
            return f"({', '.join(cls._strFormaBlockLabelItem(o) for o in item)})"
        else:
            name = getattr(item, "__qualname__", None)
            if name is None:
                name = getattr(item, "__name__", None)
                if name is None:
                    name = str(item)
        return name

    def _getOrCreateSsaBasicBlock(self, dstLabel: BlockLabel):
        block = self.labelToBlock.get(dstLabel, None)
        if block is None:
            nameParts = []
            for item in dstLabel:
                nameParts.append(self._strFormaBlockLabelItem(item))
            block = SsaBasicBlock(
                self.toSsa.ssaCtx, f"block{'_'.join(nameParts)}")
            self.labelToBlock[dstLabel] = SsaBlockGroup(block)
            self.blockToLabel[block] = dstLabel
            return block, True

        return block.begin, False

    def _onBlockGenerated(self, frame: PyBytecodeFrame, label: BlockLabel):
        """
        Called once all successors were added in SSA.
        """
        for bl in frame.blockTracker.addGenerated(label):
            # we can seal the block only after body was generated
            # :attention: The header of hardware loop can be sealed only after all body blocks were generated
            #             Otherwise some PHI arguments can be lost
            self._onAllPredecsKnown(frame, self.labelToBlock[bl].begin)

    def _addNotGeneratedJump(self, frame: PyBytecodeFrame, srcBlockLabel: BlockLabel, dstBlockLabel: BlockLabel):
        """
        Marks edge in CFG as not generated. If subgraph behind the edge becomes unreachable, mark recursively.
        If some block will get all edges know mark it recursively.
        """
        for bl in frame.blockTracker.addNotGenerated(srcBlockLabel, dstBlockLabel):
            # sealing begin should be sufficient because all block behind begin in this
            # group should already have all predecessors known
            # :attention: The header of hardware loop can be sealed only after all body blocks were generated
            #             Otherwise some PHI arguments can be lost

            self._onAllPredecsKnown(frame, self.labelToBlock[bl].begin)

    def _onBlockNotGenerated(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, blockOffset: int):
        for loopScope in reversed(frame.loopStack):
            loopScope: PyBytecodeLoopInfo
            if loopScope.loop.entryPoint[-1] == blockOffset:
                # is backedge in preproc loop, edge of this type was not generated in the first place
                return

        srcBlockLabel = self.blockToLabel[curBlock]
        dstBlockLabel = frame.blockTracker._getBlockLabel(blockOffset)
        self._addNotGeneratedJump(frame, srcBlockLabel, dstBlockLabel)

    def _onAllPredecsKnown(self, frame: PyBytecodeFrame, block: SsaBasicBlock):
        label = self.blockToLabel[block]
        loop = frame.loops.get(label[-1], None)
        self.toSsa._onAllPredecsKnown(block)
        if loop is not None:
            # if the value of PHI have branch in loop body where it is not modified it results in the case
            # where PHI would be its own argument, this is illegal and we fix it by adding block between loop body end and loop header
            # However we have to also transplant some other PHIs or create a new PHIs and move some args as we are modifying the predecessors
            predecCnt = len(block.predecessors)
            if any(len(phi.operands) != predecCnt for phi in block.phis):
                raise NotImplementedError(loop)

    def _createInstructionException(self, frame: PyBytecodeFrame, instr: Instruction):
        if instr.starts_line is not None:
            instrLine = instr.starts_line
        else:
            instrLine = -1
            for i in reversed(frame.instructions[:frame.instructions.index(instr)]):
                if i.starts_line is not None:
                    instrLine = i.starts_line
                    break

        fn = frame.fn
        return HlsSyntaxError(f"  File \"%s\", line %d, in %s\n    %r" % (
            fn.__globals__['__file__'], instrLine, fn.__name__, instr))

    def _translateBytecodeBlockInstruction(self,
            frame: PyBytecodeFrame,
            curBlock: SsaBasicBlock,
            instr: Instruction) -> SsaBasicBlock:

        try:
            # Python assigns each name in a scope to exactly one category:
            #  local, enclosing, or global/builtin.
            # CPython, implements that rule by using:
            #  FAST locals, DEREF closure cells, and NAME or GLOBAL lookups.
            # https://github.com/python/cpython/blob/main/Python/ceval.c
            op = self.opcodeDispatch.get(instr.opcode, None)
            if op is None:
                raise NotImplementedError(instr)
            else:
                return op(frame, curBlock, instr)

        except HlsSyntaxError:
            raise  # already decorated exception, just propagate

        except Exception:
            # a new exception generated directly from user code
            raise self._createInstructionException(frame, instr)
