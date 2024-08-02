from dis import Instruction
from pathlib import Path
import sys
from typing import Optional, Dict, List, Union, Literal

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.const import HConst
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.errors import HlsSyntaxError
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode.blockLabel import BlockLabel
from hwtHls.frontend.pyBytecode.blockPredecessorTracker import SsaBlockGroup
from hwtHls.frontend.pyBytecode.errorUtils import createInstructionException
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame, \
    PyBytecodeLoopInfo
from hwtHls.frontend.pyBytecode.fromPythonLowLevelOpcodes import PyBytecodeToSsaLowLevelOpcodes
from hwtHls.frontend.pyBytecode.fromPythonPragma import _applyLoopPragma
from hwtHls.frontend.pyBytecode.instructions import FOR_ITER, JUMP_OPS, \
    RETURN_VALUE, RETURN_CONST
from hwtHls.frontend.pyBytecode.loopMeta import BranchTargetPlaceholder, \
    LoopExitJumpInfo
from hwtHls.frontend.pyBytecode.loopsDetect import PreprocLoopScope
from hwtHls.frontend.pyBytecode.utils import blockHasBranchPlaceholder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.scope import HlsScope
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue

JumpCondition = Union[None, HConst, RtlSignal, SsaValue, Literal[False]]


class PyBytecodeToSsaLowLevel(PyBytecodeToSsaLowLevelOpcodes):

    def __init__(self, hls: HlsScope, dbgTracer: DebugTracer, label: str, namePrefix:str):
        super(PyBytecodeToSsaLowLevel, self).__init__()
        assert sys.version_info >= (3, 11, 0), ("Python3.11 is minimum requirement", sys.version_info)
        self.hls = hls
        self.label = label
        self.namePrefix = namePrefix
        self.toSsa: Optional[HlsAstToSsa] = None
        self.blockToLabel: Dict[SsaBasicBlock, BlockLabel] = {}
        self.labelToBlock: Dict[BlockLabel, SsaBlockGroup] = {}
        self.callStack: List[PyBytecodeFrame] = []
        self.dbgTracer = dbgTracer
        self.debugDirectory = None
        self.debugBytecode = False
        self.debugCfgBegin = False
        self.debugCfgGen = False
        self.debugCfgFinal = False
        self.debugGraphCntr = 0

    def _debugDump(self, frame: PyBytecodeFrame, label=None):
        assert self.debugDirectory is not None, self
        d = Path(self.debugDirectory) / self.toSsa.label
        d.mkdir(exist_ok=True)
        with open(d / f"00.cfg.{self.debugGraphCntr:d}{'.' if label else ''}{label if label else ''}.dot", "w") as f:
            sealedBlocks = set(self.blockToLabel[b] for b in self.toSsa.m_ssa_u.sealedBlocks)
            frame.blockTracker.dumpCfgToDot(f, sealedBlocks, self.labelToBlock)
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
        self.dbgTracer.log(("_onBlockGenerated", label))
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
        self.dbgTracer.log(("_addNotGeneratedJump", srcBlockLabel, "->", dstBlockLabel))
        for bl in frame.blockTracker.addNotGenerated(srcBlockLabel, dstBlockLabel):
            # sealing begin should be sufficient because all block behind begin in this
            # group should already have all predecessors known
            # :attention: The header of hardware loop can be sealed only after all body blocks were generated
            #             Otherwise some PHI arguments can be lost

            self._onAllPredecsKnown(frame, self.labelToBlock[bl].begin)

    def _onBlockNotGenerated(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, blockOffset: int):
        for loopScope in reversed(frame.loopStack):
            loopScope: PyBytecodeLoopInfo
            if loopScope.loop.entryPoint == blockOffset:
                # is backedge in preproc loop, edge of this type was not generated in the first place
                return

        srcBlockLabel = self.blockToLabel[curBlock]
        dstBlockLabel = frame.blockTracker._getBlockLabel(blockOffset)
        self._addNotGeneratedJump(frame, srcBlockLabel, dstBlockLabel)

    def _onAllPredecsKnown(self, frame: PyBytecodeFrame, block: SsaBasicBlock):
        label = self.blockToLabel[block]
        self.dbgTracer.log(("_onAllPredecsKnown", label))

        loop = frame.loops.get(label[-1], None)
        self.toSsa._onAllPredecsKnown(block)
        if loop is not None:
            # if the value of PHI have branch in loop body where it is not modified it results in the case
            # where PHI would be its own argument, this is illegal and we fix it by adding block between loop body end and loop header
            # However we have to also transplant some other PHIs or create a new PHIs and move some args as we are modifying the predecessors
            predecCnt = len(block.predecessors)
            if any(len(phi.operands) != predecCnt for phi in block.phis):
                raise NotImplementedError(loop)

    def _translateBytecodeBlockInstruction(self,
            frame: PyBytecodeFrame,
            curBlock: SsaBasicBlock,
            instr: Instruction) -> SsaBasicBlock:

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
            raise createInstructionException(e, frame, instr) from e.__cause__

    def _getOrCreateSsaBasicBlockAndJumpRecursively(self,
            frame: PyBytecodeFrame,
            curBlock: SsaBasicBlock,
            sucBlockOffset: int,
            cond: JumpCondition,
            branchPlaceholder: Optional[BranchTargetPlaceholder],
            allowJumpToNextLoopIteration=False):
        """
        Get existing or new block, prepare jump to this block and translate body of blocks recursively.
        If the loop exit is detected the meta information is saved to loop for later use when all loop exits are resolved.
        """
        self.dbgTracer.log(("jmp", curBlock.label, "->", sucBlockOffset, cond))
        res = self._prepareSsaBlockBeforeTranslation(frame,
            curBlock, sucBlockOffset, cond, branchPlaceholder, allowJumpToNextLoopIteration)

        if curBlock is self.toSsa.start:
            # entry point, there are not other branches and entry block needs to be marked
            # as generated in advance so all other blocks can see that they are reachable from generated block
            self._onBlockGenerated(frame, self.blockToLabel[curBlock])
            # self._onAllPredecsKnown(frame, curBlock)

        if res is not None and res.dstBlockIsNew:
            assert res.branchPlaceholder is None, (curBlock.label, "->", sucBlockOffset, cond)
            self._translateBlockBody(frame, res.isExplicitLoopReenter, res.dstBlockLoops, res.dstBlockOffset, res.dstBlock)

    def _prepareSsaBlockBeforeTranslation(self,
            frame: PyBytecodeFrame,
            curBlock: SsaBasicBlock,
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
                branchPlaceholder = BranchTargetPlaceholder.create(curBlock)
            lei = LoopExitJumpInfo(None, curBlock, cond, None, sucBlockOffset, None, None, branchPlaceholder, frame)
            frame.markJumpFromBodyOfCurrentLoop(lei)
            return None

        blockTracker = frame.blockTracker
        if isinstance(cond, bool):
            assert cond == False, (cond, "Only bool value False is used to mark not generated block.")
            curBlockLabel = self.blockToLabel[curBlock]
            dstBlockLabel = blockTracker._getBlockLabel(sucBlockOffset)
            self._addNotGeneratedJump(frame, curBlockLabel, dstBlockLabel)
            return None

        # if this is a jump out of current loop
        if isinstance(cond, HConst):
            assert cond, (cond, "If this was not True the jump should not be evaluated at the first place")
            cond = None  # always jump, but we need this value to know that this will be unconditional jump only in HW

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
                        for bl in blockTracker.cfgAddPrefixToLoopBlocks(sucLoop, newPrefix):
                            bl: BlockLabel
                            self._onBlockGenerated(frame, bl)

                    if self.debugCfgGen:
                        self._debugDump(frame, f"_afterPrefix_{newPrefix}")

        # if this is a jump just in linear code or inside body of the loop
        sucBlockLabel = blockTracker._getBlockLabel(sucBlockOffset)
        sucBlock, sucBlockIsNew = self._getOrCreateSsaBasicBlock(sucBlockLabel)
        if branchPlaceholder is None:
            curBlock.successors.addTarget(cond, sucBlock)
        else:
            branchPlaceholder.replace(cond, sucBlock)

        return LoopExitJumpInfo(sucBlockIsNew, curBlock, cond,
                                sucBlock, sucBlockOffset, sucLoops, isExplicitLoopReenter, None, frame)

    def _translateBlockBody(self,
            frame: PyBytecodeFrame,
            isExplicitLoopReenter: bool,
            loops: Optional[PyBytecodeLoopInfo],
            blockOffset: int,
            block: SsaBasicBlock):
        """
        Call :meth:`~._translateBytecodeBlock` and check if we finished translation of some loop body.
        """
        self.dbgTracer.log(("_translateBlockBody", blockOffset, block.label))

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
                blockTracker = frame.blockTracker
                headerLabel = self.blockToLabel[block]
                frame.exitLoop()
                if headerLabel not in blockTracker.generated:
                    self._onBlockGenerated(frame, headerLabel)

            elif loopInfo.mustBeEvaluatedInHw():
                self._finalizeJumpsFromHwLoopBody(frame, block, blockOffset, loopInfo,
                                                  latchBlock=loopInfo.additionalLatchBlock,
                                                  onAdditionalLatchBlockPredecessorsAdded=loopInfo.onAdditionalLatchBlockPredecessorsAdded)
                if loopInfo.pragma:
                    _applyLoopPragma(block, loopInfo)

            else:
                assert loopInfo.additionalLatchBlock is None, block
                assert loopInfo.onAdditionalLatchBlockPredecessorsAdded is None, block
                self._runPreprocessorLoop(frame, loopInfo)
                if loopInfo.pragma:
                    raise NotImplementedError("_runPreprocessorLoop + pragma", loopInfo.pragma)

    def _getFalltroughOffset(self, frame: PyBytecodeFrame, block: SsaBasicBlock) -> int:
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
            curBlock: SsaBasicBlock):
        """
        Evaluate instruction list and translate to SSA all which is using HW types and which can not be evaluated compile time.
        Follow jumps recursively unless the jump is out of current loop body. If it is the case just stagg it for later.
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
                    self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, self._getFalltroughOffset(frame, curBlock), None, None)
                    if not blockHasBranchPlaceholder(curBlock):
                        self._onBlockGenerated(frame, self.blockToLabel[curBlock])
