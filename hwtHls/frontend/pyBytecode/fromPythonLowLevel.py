from copy import copy
from dis import Instruction
import sys
from typing import Optional, Dict, List, Union, Literal

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.const import HConst
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.errors import HlsSyntaxError
from hwtHls.frontend.pyBytecode.blockLabel import BlockLabel
from hwtHls.frontend.pyBytecode.blockPredecessorTracker import SsaBlockGroup
from hwtHls.frontend.pyBytecode.errorUtils import createInstructionException
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame, \
    PyBytecodeLoopInfo
from hwtHls.frontend.pyBytecode.fromPythonLowLevelOpcodes import PyBytecodeToSsaLowLevelOpcodes
from hwtHls.frontend.pyBytecode.instructions import FOR_ITER, JUMP_OPS, \
    RETURN_VALUE, RETURN_CONST
from hwtHls.frontend.pyBytecode.loopMeta import BranchTargetPlaceholder, \
    LoopExitJumpInfo
from hwtHls.frontend.pyBytecode.loopsDetect import PreprocLoopScope
from hwtHls.llvm.llvmIr import Value, BasicBlock
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.scope import HlsScope
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


JumpCondition = Union[None, HConst, RtlSignal, Value, Literal[False]]


class PyBytecodeToSsaLowLevel(PyBytecodeToSsaLowLevelOpcodes):
    """
    :note: for meaning of debug* options see :class:`HlsDebugBundle`
    """
    def __init__(self, hls: HlsScope, toLlvm: ToLlvmIrTranslator, dbgTracer: DebugTracer, label: str, namePrefix:str):
        super(PyBytecodeToSsaLowLevel, self).__init__()
        assert sys.version_info >= (3, 12, 0), ("Python3.12 is minimum requirement", sys.version_info)
        self.hls = hls
        self.label = label
        self.namePrefix = namePrefix
        self.toLlvm = toLlvm
        self.blockToLabel: Dict[BasicBlock, BlockLabel] = {}
        self.labelToBlock: Dict[BlockLabel, SsaBlockGroup] = {}
        self.callStack: List[PyBytecodeFrame] = []
        self.dbgTracer = dbgTracer
        self.debugBytecode = False
        self.debugCfgBegin = False
        self.debugCfgGen = False
        self.debugCfgFinal = False
        self.debugGraphCntr = 0

    def _debugDump(self, frame: PyBytecodeFrame, label=None):
        assert self.toLlvm._dbgRootDir is not None, self
        assert self.toLlvm._dbgSubDir is not None, self
        d = self.toLlvm._dbgRootDir / self.toLlvm._dbgSubDir
        d.mkdir(exist_ok=True)
        with open(d / f"00.cfg.{self.debugGraphCntr:d}{'.' if label else ''}{label if label else ''}.dot", "w") as f:
            frame.blockTracker.dumpCfgToDot(f, set(), self.labelToBlock)
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

    def _getOrCreateBasicBlock(self, dstLabel: BlockLabel):
        block = self.labelToBlock.get(dstLabel, None)
        if block is None:
            nameParts = []
            for item in dstLabel:
                nameParts.append(self._strFormaBlockLabelItem(item))
                toLlvm = self.toLlvm

            block = BasicBlock.Create(toLlvm.ctx, toLlvm.strCtx.addTwine(str(f"block{'_'.join(nameParts)}")), toLlvm.llvm.main, None)
            self.labelToBlock[dstLabel] = SsaBlockGroup(block)
            self.blockToLabel[block] = dstLabel
            return block, True

        return block.begin, False

    def _translateBytecodeBlockInstruction(self,
            frame: PyBytecodeFrame,
            curBlock: BasicBlock,
            instr: Instruction) -> BasicBlock:

        try:
            op = self.opcodeDispatch.get(instr.opcode, None)
            if op is None:
                raise NotImplementedError(instr)
            else:
                return op(frame, curBlock, instr)

        except HlsSyntaxError:
            raise  # already decorated exception, just propagate

        except Exception as e:
            # a new exception generated directly from user code
            raise createInstructionException(e, self.callStack, frame, instr) from e.__cause__

    def _getOrCreateBasicBlockAndJumpRecursively(self,
            frame: PyBytecodeFrame,
            curBlock: BasicBlock,
            sucBlockOffset: int,
            cond: JumpCondition,
            branchPlaceholder: Optional[BranchTargetPlaceholder],
            allowJumpToNextLoopIteration=False):
        """
        Get existing or new block, prepare jump to this block and translate body of blocks recursively.
        If the loop exit is detected the meta information is saved to loop for later use when all loop exits are resolved.
        """
        if self.dbgTracer._out is not None:
            self.dbgTracer.log(("jmp", curBlock.getName().str(), "->", sucBlockOffset, cond))
        res = self._prepareSsaBlockBeforeTranslation(frame,
            curBlock, sucBlockOffset, cond, branchPlaceholder, allowJumpToNextLoopIteration)

        if res is not None and res.dstBlockIsNew:
            assert res.branchPlaceholder is None, (curBlock.label, "->", sucBlockOffset, cond)
            self._translateBlockBody(frame, res.isExplicitLoopReenter, res.dstBlockLoops, res.dstBlockOffset, res.dstBlock)

    def _prepareSsaBlockBeforeTranslation(self,
            frame: PyBytecodeFrame,
            curBlock: BasicBlock,
            sucBlockOffset: int,
            cond: JumpCondition,
            branchPlaceholder: Optional[BranchTargetPlaceholder],
            allowJumpToNextLoopIteration=False) -> Optional[LoopExitJumpInfo]:
        """
        Prepare the jump and block to jump or create placeholder if this is the jump from the loop.
        """
        isJumpFromCurrentLoopBody = frame.isJumpFromCurrentLoopBody(sucBlockOffset)
        if not allowJumpToNextLoopIteration and isJumpFromCurrentLoopBody:
            # this is the case where we can not generate jump target because we do not know for sure if this
            # will be some existing block or we will have to generate new one because of loop expansion
            if branchPlaceholder is None:
                branchPlaceholder = BranchTargetPlaceholder.create(self.toLlvm, curBlock, cond)
            lei = LoopExitJumpInfo(None, curBlock, cond, None, sucBlockOffset, None, None, branchPlaceholder, copy(frame))
            frame.markJumpFromBodyOfCurrentLoop(lei)
            return None

        blockTracker = frame.blockTracker
        if isinstance(cond, bool):
            assert cond == False, (cond, "Only bool value False is used to mark not generated block.")
            return None

        sucLoops = frame.loops.get(sucBlockOffset, None)
        isExplicitLoopReenter = False
        if sucLoops:
            # if entering some loop we need to add prefix to block labels or copy blocks for new iteration
            # if this is a preprocessor loop
            isExplicitLoopReenter = frame.isLoopReenter(sucLoops[-1])  # [fixme]
            if not isExplicitLoopReenter:
                # rename every loop members to have name scope to this loop
                for sucLoop in sucLoops:
                    frame.enterLoop(sucLoop)
                    newPrefix = BlockLabel(*blockTracker._getBlockLabelPrefix(sucBlockOffset))

                    with self.dbgTracer.scoped("cfgAddPrefixToLoopBlocks", sucLoop):
                        self.dbgTracer.log(("newPrefix", newPrefix))
                        for _ in blockTracker.cfgAddPrefixToLoopBlocks(sucLoop, newPrefix):
                            pass
                    if self.debugCfgGen:
                        self._debugDump(frame, f"_afterPrefix_{newPrefix}")

        # if this is a jump just in linear code or inside body of the loop
        sucBlockLabel = blockTracker._getBlockLabel(sucBlockOffset)
        sucBlock, sucBlockIsNew = self._getOrCreateBasicBlock(sucBlockLabel)
        if branchPlaceholder is None:
            cond = BranchTargetPlaceholder.appendSuccessor(self.toLlvm, curBlock, cond, sucBlock)
        else:
            cond = branchPlaceholder.replace(sucBlock)

        return LoopExitJumpInfo(sucBlockIsNew, curBlock, cond,
                                sucBlock, sucBlockOffset, sucLoops, isExplicitLoopReenter, None, copy(frame))

    def _translateBlockBody(self,
            frame: PyBytecodeFrame,
            isExplicitLoopReenter: bool,
            loops: Optional[PyBytecodeLoopInfo],
            blockOffset: int,
            block: BasicBlock):
        """
        Call :meth:`~._translateBytecodeBlock` and check if we finished translation of some loop body.
        """
        if self.dbgTracer._out is not None:
            self.dbgTracer.log(("_translateBlockBody", blockOffset, block.getName().str()))

        self.toLlvm._setInsertPointBeforeTerminator(block)
        self._translateBytecodeBlock(frame, frame.bytecodeBlocks[blockOffset], block)

        if not isExplicitLoopReenter and loops:
            # now header block of loop was already translated by previous _translateBytecodeBlock()
            assert frame.loopStack, block
            loopInfo: PyBytecodeLoopInfo = frame.loopStack[-1]
            assert loopInfo.loop is loops[-1]
            if not loopInfo.jumpsFromLoopBody:
                # if there are no jumps from loop body this is group of blocks is
                assert loopInfo.additionalLatchBlock is None, block
                assert loopInfo.onAdditionalLatchBlockPredecessorsAdded is None, block
                frame.exitLoop()

            elif loopInfo.mustBeEvaluatedInHw():
                self._finalizeJumpsFromHwLoopBody(
                    frame, block, blockOffset, loopInfo,
                    latchBlock=loopInfo.additionalLatchBlock,
                    onAdditionalLatchBlockPredecessorsAdded=loopInfo.onAdditionalLatchBlockPredecessorsAdded)
                if loopInfo.pragma:
                    self.toLlvm._lateLoopPragmaToApply.append((block, loopInfo.pragma))

            else:
                assert loopInfo.additionalLatchBlock is None, block
                assert loopInfo.onAdditionalLatchBlockPredecessorsAdded is None, block
                self._runPreprocessorLoop(frame, loopInfo)
                if loopInfo.pragma:
                    raise NotImplementedError("_runPreprocessorLoop + pragma", loopInfo.pragma)

    def _getFalltroughOffset(self, frame: PyBytecodeFrame, block: BasicBlock) -> int:
        curBlockOff = self.blockToLabel[block][-1]
        fOff = None
        for off in frame.blockTracker.originalCfg.successors(curBlockOff):
            if off > curBlockOff:
                if fOff is None:
                    fOff = off
                else:
                    fOff = min(fOff, off)
        assert fOff is not None, block
        return fOff

    def _translateBytecodeBlock(self,
            frame: PyBytecodeFrame,
            instructions: List[Instruction],
            curBlock: BasicBlock):
        """
        Evaluate instruction list and translate to SSA all which is using HW types and which can not be evaluated compile time.
        Follow jumps recursively unless the jump is out of current loop body. If it is the case just stag it for later.
        """
        for last, instr in iter_with_last(instructions):
            opcode = instr.opcode
            if opcode in JUMP_OPS or opcode in (RETURN_VALUE, RETURN_CONST, FOR_ITER):
                assert last, instr
                self._translateInstructionJumpHw(frame, curBlock, instr)
            else:
                curBlock = self._translateBytecodeBlockInstruction(frame, curBlock, instr)
                assert curBlock is not None, instr
                if last:
                    # jump to next block, there was no explicit jump because this is regular code flow, but the next instruction
                    # is jump target
                    self._getOrCreateBasicBlockAndJumpRecursively(
                        frame, curBlock,
                        self._getFalltroughOffset(frame, curBlock), None, None)
