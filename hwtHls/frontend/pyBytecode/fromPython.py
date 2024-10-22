from copy import copy
from dis import Instruction, dis
from pathlib import Path
from types import FunctionType
from typing import Optional, List, Tuple, Callable

from hwt.hdl.const import HConst
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import BIT
from hwt.hwIO import HwIO
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.errors import HlsSyntaxError
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode.blockLabel import BlockLabelTmp
from hwtHls.frontend.pyBytecode.blockPredecessorTracker import BlockLabel, \
    BlockPredecessorTracker
from hwtHls.frontend.pyBytecode.errorUtils import createInstructionException
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.frontend.pyBytecode.fromPythonLowLevel import PyBytecodeToSsaLowLevel, \
    SsaBlockGroup, JumpCondition
from hwtHls.frontend.pyBytecode.hwIterator import HwIterator
from hwtHls.frontend.pyBytecode.indexExpansion import expandBeforeUse
from hwtHls.frontend.pyBytecode.instructions import JUMP_FORWARD, JUMP_BACKWARD, \
    RETURN_VALUE, RAISE_VARARGS, RERAISE, \
    JUMP_BACKWARD_NO_INTERRUPT, JUMP_OPS, FOR_ITER, POP_JUMP_IF_FALSE, \
    POP_JUMP_IF_NOT_NONE, POP_JUMP_IF_NONE, RETURN_CONST, NULL
from hwtHls.frontend.pyBytecode.loopMeta import PyBytecodeLoopInfo, \
    BranchTargetPlaceholder, LoopExitJumpInfo
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodePreprocDivergence, \
    PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode.utils import isLastJumpFromBlock, blockHasBranchPlaceholder
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue


# [TODO] support for debugger
#    _PyMonitoring_RegisterCallback, PY_MONITORING_SYS_TRACE_ID, sys.settrace is used by pydev and others
#    https://github.com/JetBrains/intellij-community/blob/master/python/helpers/pydev/pydevd_tracing.py#L155
#    https://stackoverflow.com/questions/32486204/debugging-python-bytecode-when-source-is-not-available
#    https://github.com/Kuree/hgdb
#    https://github.com/bet4it/gdbserver
#    https://sourceware.org/gdb/current/onlinedocs/gdb
#    https://github.com/mborgerson/gdbstub
#    https://github.com/nomtats/gdbserver-stub https://medium.com/@tatsuo.nomura/implement-gdb-remote-debug-protocol-stub-from-scratch-1-a6ab2015bfc5
class PyBytecodeToSsa(PyBytecodeToSsaLowLevel):
    """
    This class translates Python bytecode to :mod:`hwtHls.ssa`. The preprocessor tries to evaluate as much as possible
    and only things which do depend on hardware evaluated values are in output SSA code.

    Methods in this class specifically are responsible for translation of loops and jumps, the rest is in the base class.

    Description of Python bytecode:
        * https://docs.python.org/3/library/dis.html
        * https://towardsdatascience.com/understanding-python-bytecode-e7edaae8734d
        * https://github.com/google/pytype/blob/main/pytype/vm.py

    :note: SSA construction algorithm requires detection of an event when basic block have all predecessors known.
      This is complicated in this case as blocks are dynamically generated during evaluation of bytecode.
      :see: :class:`hwtHls.frontend.pyBytecode.blockPredecessorTracker.BlockPredecessorTracker`


    :note: Python assigns each name in a scope to exactly one category:
             local, enclosing, or global/builtin.
    :note: CPython, implements that rule by using:
            FAST locals, DEREF closure cells, and NAME or GLOBAL lookups.
            https://github.com/python/cpython/blob/main/Python/ceval.c
    """

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
        fnName = getattr(fn, "__qualname__", fn.__name__)
        if self.debugBytecode:
            d = Path(self.debugDirectory) / fnName
            d.mkdir(exist_ok=True)
            with open(d / f"00.bytecode.{fnName}.txt", "w") as f:
                dis(fn, file=f)
        with self.dbgTracer.scoped("translateFunction", fnName):
            platform = self.hls.parentHwModule._target_platform
            self.toSsa = HlsAstToSsa(self.hls.ssaCtx, fnName, self.namePrefix, None, platform.getPassManagerDebugLogFile())

            entryBlock = self.toSsa.start
            entryBlockLabel = self.blockToLabel[entryBlock] = BlockLabel(-1)
            self.labelToBlock[entryBlockLabel] = SsaBlockGroup(entryBlock)
            frame = PyBytecodeFrame.fromFunction(fn, entryBlockLabel, -1, fnArgs, fnKwargs, self.callStack)
            if self.debugCfgBegin:
                self._debugDump(frame, "_begin")

            try:
                self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, entryBlock, 0, None, None, True)
                # self._onBlockGenerated(frame, entryBlockLabel)
                assert not frame.loopStack, ("All loops must be exited", frame.loopStack)
                firstReturn = True
                finalRetVal = None
                for (_frame, retBlock, retVal) in frame.returnPoints:
                    if firstReturn:
                        finalRetVal = False
                    elif finalRetVal is not retVal:
                        raise NotImplementedError("Currently function can return only a sigle instance.", frame.returnPoints)
                    finalRetVal = retVal
                    retBlockLabel = self.blockToLabel[retBlock]
                    assert retBlockLabel in frame.blockTracker.generated, ("Must have all successor know if it is return from top function", retBlockLabel)
                self.dbgTracer.log(("return", finalRetVal))
            finally:
                if self.debugCfgFinal:
                    self._debugDump(frame, "_final")

            self.toSsa.pragma.extend(frame.pragma)
            assert len(self.callStack) == 1 and self.callStack[0] is frame, self.callStack
            self.toSsa.finalize()
            return finalRetVal

    def _runPreprocessorLoop(self, frame: PyBytecodeFrame, loopInfo: PyBytecodeLoopInfo):
        """
        Continue evaluation of the loop in preprocessor.

        This function is called once we evaluate a single loop body and we can decide that this loop
        has compatible iteration scheme and can be evaluated in preprocessor.

        If there are multiple exit edges from loop body it means that the loop control somehow depends on
        HW evaluated conditions.
        If loop exit using break on HW evaluated condition we must visit all successor blocks with every stack/locals variant.
        This may require duplication of all successor blocks until we reach exit or boundary of parent hardware evaluated loop.

        .. code-block:: Python3

            # bb.0
            res = uint8_t.from_py(0)
            for i in range(4): # bb.1
                if hw_cond[i]: # bb.2
                    # bb.3
                    res = i
                    break
            # bb.4

        In this example the block bb.3 is not part of the loop.
        And it has live-in local variable (i) generated in preprocessor.

        .. code-block:: text

           bb.0
            v
           bb.1 --+-> bb.3
           ^  ^   |    v
           ----   --> bb.4

        We can not just generate PHIs for this variable in generated code because this is potentially a Python object without
        hardware representation. Because of this we need to duplicate all blocks which are using such variables.
        The use of variable may be in any successor block and may be transitively propagated and the variable itself may be nested
        in object hierarchy and accessed in non-trivial way. Because of this the copy is only safe method of translation.

        However duplication would in many cases result in duplication of whole program with irreparable unwanted consequences.
        Because of this we need to limit the scope of what is duplicated, ideally to just AST of the loop as we see it.
        Accessing AST is not doable because of how bytecode is build. Instead we give user ability to limit the scope manually.
        Scope of such a duplication can be limited by encapsulation to a function.
        """
        with self.dbgTracer.scoped("_runPreprocessorLoop", loopInfo):
            blockTracker = frame.blockTracker
            assert loopInfo.jumpsFromLoopBody, ("Preproc loop must have exit point", loopInfo.loop, frame.loopStack)
            loopExitsToTranslate: List[LoopExitJumpInfo] = []
            headerBlockLabels = []

            # [FIXME] the CFG does contain exit jumps from previous iteration jumps which were not marked with notGenerated
            #        but LoopExitJumpInfo should be present
            while loopInfo.jumpsFromLoopBody:
                # print("preprocessing loop", loopInfo.loop, loopInfo.jumpsFromLoopBody)
                assert frame.loopStack[-1] is loopInfo, (loopInfo, frame.loopStack)

                # try to delegate jumps from this loop to parent loop
                jumpsFromLoopBody = loopInfo.jumpsFromLoopBody
                _jumpsFromLoopBody: List[Tuple[bool, LoopExitJumpInfo]] = []
                for j in jumpsFromLoopBody:
                    j: LoopExitJumpInfo

                    isLoopReenter = loopInfo.loop.entryPoint == j.dstBlockOffset
                    if not isLoopReenter and len(frame.loopStack) > 1:
                        parentLoop: PyBytecodeLoopInfo = frame.loopStack[-2]
                        if parentLoop.isJumpFromLoopBody(j.dstBlockOffset):
                            # if this jump is also jump from parent loop delegate it to parent loop
                            parentLoop.jumpsFromLoopBody.append(j)
                            continue

                    _jumpsFromLoopBody.append((isLoopReenter, j))

                if not _jumpsFromLoopBody:
                    # everything was delegeted to parent and it should solve block sealing
                    break

                _jumpsFromLoopBody.sort(key=lambda x: not x[0])

                headerBlockLabel = blockTracker._getBlockLabel(loopInfo.loop.entryPoint)
                headerBlockLabels.append(headerBlockLabel)

                loopInfo.markNewIteration()

                successorsToTranslate: List[Tuple[bool, LoopExitJumpInfo]] = []
                for i, (isLoopReenter, j) in enumerate(_jumpsFromLoopBody):
                    srcBlockLabel = self.blockToLabel[j.srcBlock]
                    assert isinstance(srcBlockLabel, BlockLabel), srcBlockLabel
                    dstBlockLabel = blockTracker._getBlockLabel(j.dstBlockOffset)

                    # update CFG after we resolved reenter or loop exit
                    if isLoopReenter:
                        blockTracker.cfg.add_edge(srcBlockLabel, dstBlockLabel)
                        # a case where next block is current block which is a loop header
                        assert frame.loopStack[-1].loop is loopInfo.loop
                        newPrefix = BlockLabel(*blockTracker._getBlockLabelPrefix(j.dstBlockOffset))
                        with self.dbgTracer.scoped("cfgCopyLoopBlocks", loopInfo.loop):
                            self.dbgTracer.log(("newPrefix", newPrefix))
                            for bl in blockTracker.cfgCopyLoopBlocks(loopInfo.loop, newPrefix):
                                bl: BlockLabel
                                self._onBlockGenerated(j.frame, bl)
                        # self._onBlockGenerated(frame, dstBlockLabel)
                    if self.debugCfgGen:
                        self._debugDump(frame)

                    # translate only jump without actual translation of the blocks behind
                    sucInfo = self._translateJumpFromCurrentLoop(j.frame, False,
                           j.srcBlock, j.cond, j.dstBlockOffset, False, j.branchPlaceholder,
                           allowJumpToNextLoopIteration=True)

                    assert frame.loopStack[-1] is loopInfo, (loopInfo, frame.loopStack)
                    if sucInfo is not None and sucInfo.dstBlockIsNew:
                        # if sucInfo is None or is not dstBlockIsNew it means that the jump was already translated
                        # and additional action is required
                        successorsToTranslate.append((isLoopReenter, sucInfo))

                    # print(srcBlockLabel, "->", dstBlockLabel, " header:", headerBlockLabel)
                    if (srcBlockLabel != headerBlockLabel and
                            isLastJumpFromBlock([j for  (_, j) in _jumpsFromLoopBody], j.srcBlock, i) and
                            srcBlockLabel not in blockTracker.generated
                            ):
                        # because we we can not jump to a block from anywhere but loop header (because of structural programming)
                        self._onBlockGenerated(frame, srcBlockLabel)

                # process the jumps to next iteration and mark jumps from the loop for later processing
                if len(successorsToTranslate) > 1:
                    assert len(set(id(j[1].frame) for j in successorsToTranslate)) == len(successorsToTranslate), (
                        "Each jump must have own version of frame because multiple jumps could be only generated for HW evaluated jumps which do require copy of frame"
                        )
                for isLoopReenter, sucInfo in successorsToTranslate:
                    sucInfo: LoopExitJumpInfo

                    if isLoopReenter:
                        assert sucInfo.branchPlaceholder is None, sucInfo
                        self._translateBlockBody(sucInfo.frame, sucInfo.isExplicitLoopReenter, sucInfo.dstBlockLoops,
                                                 sucInfo.dstBlockOffset, sucInfo.dstBlock)
                        assert sucInfo.frame.loopStack[-1] is loopInfo, (loopInfo, sucInfo.frame.loopStack)
                    else:
                        loopExitsToTranslate.append(sucInfo)

            for headerBlockLabel in headerBlockLabels:
                # we must do this after loop is fully expanded
                # because we must not seal block where something in loop may be predecessor when the loop body does not exist yet
                if headerBlockLabel not in blockTracker.generated:
                    self._onBlockGenerated(frame, headerBlockLabel)

            if len(loopExitsToTranslate) > 1:
                assert len(set(id(j.frame) for j in loopExitsToTranslate)) == len(loopExitsToTranslate), (
                    "Each jump must have own version of frame because multiple jumps could be only generated for HW evaluated jumps which do require copy of frame"
                    )

            frame.exitLoop()
            for sucInfo in loopExitsToTranslate:
                sucInfo: LoopExitJumpInfo
                # Finalize the jumps from this loop and continue translation where we left
                assert sucInfo.branchPlaceholder is None, sucInfo
                self._translateBlockBody(sucInfo.frame, sucInfo.isExplicitLoopReenter, sucInfo.dstBlockLoops,
                                         sucInfo.dstBlockOffset, sucInfo.dstBlock)
            if self.debugCfgGen:
                self._debugDump(frame, f"_afterLoopExit{loopInfo.loop.entryPoint}")

    def _getNextIterationBlockLabel(self, blockTracker: BlockPredecessorTracker, loopInfo: PyBytecodeLoopInfo, blockOffset: int):
        loopInfo.iteraionI += 1
        nextIterationLoopHeaderLabel = blockTracker._getBlockLabel(blockOffset)
        loopInfo.iteraionI -= 1
        return nextIterationLoopHeaderLabel

    def _finalizeJumpsFromHwLoopBody(self, frame: PyBytecodeFrame,
                                     headerBlock: SsaBasicBlock,
                                     headerOffset: int,
                                     loopInfo: PyBytecodeLoopInfo,
                                     latchBlock:Optional[SsaBasicBlock]=None,
                                     onAdditionalLatchBlockPredecessorsAdded: Optional[Callable[[], SsaBasicBlock]]=None):
        """
        connect the loop header re-entry to a current loop header and continue execution on loop exit points

        :param latchBlock: optional block where all re-entry branches in loop should jump and it will get
            an unconditional branch to header
        """
        with self.dbgTracer.scoped("_finalizeJumpsFromHwLoopBody", (headerOffset, headerBlock.label)):
            blockTracker = frame.blockTracker
            headerLabel = self.blockToLabel[headerBlock]
            jumpsFromLoopBody = loopInfo.jumpsFromLoopBody
            if latchBlock is None or latchBlock is headerBlock:
                if latchBlock is None:
                    assert onAdditionalLatchBlockPredecessorsAdded is None
                latchBlock = headerBlock
                latchBlockLabel = headerLabel
            else:
                latchBlockLabel = self.blockToLabel[latchBlock]
                blockTracker.cfg.add_edge(latchBlockLabel, headerLabel)

            # delete next iteration block header because this loop will not be unrolled in preprocessor
            # :attention: must be done before processing of jumps from the loop because it works in DFS and
            #             we may step on this block before we remove it
            # we will not copy the loop body but instead create a regular loop
            exitSuccessorsToTranslate: List[Tuple[BlockLabel, LoopExitJumpInfo, Optional[BlockLabel]]] = []
            for j in jumpsFromLoopBody:
                j: LoopExitJumpInfo
                isJumpToHeader = j.dstBlockOffset == headerOffset
                srcBlockLabel = self.blockToLabel[j.srcBlock]
                # fill back the original backedge (srcBlock -> header) in the loop CFG
                c = j.cond

                if isJumpToHeader:
                    blockTracker.cfg.add_edge(srcBlockLabel, latchBlockLabel)
                    # else the edge should be already present
                    if isinstance(c, bool):
                        assert not c
                        assert j.branchPlaceholder is None, j
                        dstBlockLabel = self.blockToLabel[j.dstBlock]
                        self._addNotGeneratedJump(j.frame, srcBlockLabel, dstBlockLabel)
                        continue

                    elif isinstance(c, HConst):
                        assert int(c) == 1, c
                        c = None

                    j.branchPlaceholder.replace(c, latchBlock)

                    # make "temporary next iteration header block" as not generated
                    nextIterationLoopHeaderLabel = self._getNextIterationBlockLabel(blockTracker, loopInfo, j.dstBlockOffset)
                    self._addNotGeneratedJump(j.frame, srcBlockLabel, nextIterationLoopHeaderLabel)

                    if not blockHasBranchPlaceholder(j.srcBlock):
                        self._onBlockGenerated(j.frame, srcBlockLabel)

                else:
                    if isinstance(c, bool):
                        assert not c
                        assert j.branchPlaceholder is None, j
                        exitSuccessorsToTranslate.append((srcBlockLabel, j, frame.blockTracker._getBlockLabel(j.dstBlockOffset)))

                    else:
                        sucInfo = self._translateJumpFromCurrentLoop(j.frame, False,
                               j.srcBlock, j.cond, j.dstBlockOffset, False, j.branchPlaceholder)

                        if sucInfo is not None and sucInfo.dstBlockIsNew:
                            exitSuccessorsToTranslate.append((srcBlockLabel, sucInfo, None))

                        elif not blockHasBranchPlaceholder(j.srcBlock) and j.srcBlock is not headerBlock:
                            self._onBlockGenerated(j.frame, srcBlockLabel)

            if latchBlock is not headerBlock:
                self._onBlockGenerated(frame, latchBlockLabel)
                if onAdditionalLatchBlockPredecessorsAdded is not None:
                    latchBlock = onAdditionalLatchBlockPredecessorsAdded(frame, latchBlock)
                latchBlock.successors.addTarget(None, headerBlock)

            # [todo] do not mark if this header if it is shared with parent loop
            frame.exitLoop()
            for srcBlockLabel, sucInfo, dstBlockLabel in exitSuccessorsToTranslate:
                sucInfo: LoopExitJumpInfo
                srcBlockLabel: BlockLabel
                dstBlockLabel: BlockLabel
                assert sucInfo.branchPlaceholder is None, sucInfo
                if isinstance(sucInfo.cond, bool):
                    assert not sucInfo.cond
                    self._addNotGeneratedJump(sucInfo.frame, srcBlockLabel, dstBlockLabel)
                else:
                    self._translateBlockBody(sucInfo.frame, sucInfo.isExplicitLoopReenter, sucInfo.dstBlockLoops,
                                             sucInfo.dstBlockOffset, sucInfo.dstBlock)
                    # because the block was in the loop and we see its last successor we know that this block was completely generated
                    if not blockHasBranchPlaceholder(sucInfo.srcBlock) and sucInfo.srcBlock is not headerBlock:
                        self._onBlockGenerated(sucInfo.frame, srcBlockLabel)

            if headerLabel not in blockTracker.generated:
                self._onBlockGenerated(frame, headerLabel)

    def _translateJumpFromCurrentLoop(self, frame: PyBytecodeFrame,
                                      isLastJumpFromSrc: bool,
                                      srcBlock: SsaBasicBlock,
                                      cond: JumpCondition,
                                      dstBlockOffset: int,
                                      translateImmediately: bool,
                                      branchPlaceholder: Optional[BranchTargetPlaceholder],
                                      allowJumpToNextLoopIteration=False) -> Optional[LoopExitJumpInfo]:
        """
        Prepare dst block and create jump between src and dst block.
        """
        if len(frame.loopStack) > 1:
            parentLoop: PyBytecodeLoopInfo = frame.loopStack[-2]
            if dstBlockOffset not in parentLoop.loop.allBlocks or parentLoop.loop.entryPoint == dstBlockOffset:
                # if it is jump also from parent block forward handling to parent loop
                lei = LoopExitJumpInfo(None, srcBlock, cond, None, dstBlockOffset, None, None, branchPlaceholder, frame)
                parentLoop.markJumpFromBodyOfLoop(lei)
                return None

        if not allowJumpToNextLoopIteration:
            li = frame.loopStack.pop()

        if translateImmediately:
            self._getOrCreateSsaBasicBlockAndJumpRecursively(frame,
                srcBlock, dstBlockOffset, cond, branchPlaceholder,
                allowJumpToNextLoopIteration=allowJumpToNextLoopIteration)
            res = None

        else:
            res = self._prepareSsaBlockBeforeTranslation(frame,
                srcBlock, dstBlockOffset, cond, branchPlaceholder,
                allowJumpToNextLoopIteration=allowJumpToNextLoopIteration)

        if not allowJumpToNextLoopIteration:
            frame.loopStack.append(li)

        return res

    def _onBlockNotGeneratedPotentiallyOutOfLoop(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, sucBlockOffset: int):
        isJumpFromCurrentLoopBody = frame.isJumpFromCurrentLoopBody(sucBlockOffset)
        if isJumpFromCurrentLoopBody:
            # this is the case where we can not generate jump target because we do not know for sure if this
            # will be some existing block or we will have to generate new one because of loop expansion
            lei = LoopExitJumpInfo(None, curBlock, False, None, sucBlockOffset, None, None, None, frame)
            frame.markJumpFromBodyOfCurrentLoop(lei)
        else:
            self._onBlockNotGenerated(frame, curBlock, sucBlockOffset)

    def _insertLatchForLoop(self, frame: PyBytecodeFrame, headerBlockLabel: BlockLabel):
        latchBlockLabel = BlockLabel(*headerBlockLabel, BlockLabelTmp("latch"))
        latchBlock, isNew = self._getOrCreateSsaBasicBlock(latchBlockLabel)
        assert isNew, latchBlock
        cfg = frame.blockTracker.cfg
        assert len(headerBlockLabel) >= 2, headerBlockLabel
        loopLabelPrefix = headerBlockLabel[:-1]
        loopLablePrefixLen = len(loopLabelPrefix)
        for headerPred in tuple(frame.blockTracker.cfg.predecessors(headerBlockLabel)):
            # make all re-enter edges to use new latch block
            if len(headerPred) > loopLablePrefixLen and headerPred[:loopLablePrefixLen] == loopLabelPrefix:
                cfg.remove_edge(headerPred, headerBlockLabel)
                cfg.add_edge(headerPred, latchBlockLabel)
        cfg.add_edge(latchBlockLabel, headerBlockLabel)

        # self._onBlockGenerated(frame, latchBlockLabel)
        return latchBlock

    def _translateInctuctionJumpFOR_ITER(self, frame: PyBytecodeFrame,
                                    curBlock: SsaBasicBlock,
                                    forIter: Instruction):
        """
        STACK[-1] is an iterator. Call its __next__() method. If this yields a new value,
        push it on the stack (leaving the iterator below it). If the iterator indicates it
        is exhausted then the byte code counter is incremented by delta.
        Changed in version 3.12: Up until 3.11 the iterator was popped when it was exhausted.
        """
        curLoopInfo: PyBytecodeLoopInfo = frame.loopStack[-1]
        curBlockLabel = self.blockToLabel[curBlock]
        # curLoop = curLoopInfo.loop
        assert curLoopInfo.loop.entryPoint == curBlockLabel[-1], (curLoopInfo, curBlock)
        a = frame.stack[-1]
        exitBlockOffset = forIter.argval
        off = forIter.offset
        if off not in frame.blockTracker.originalCfg:
            off -= 2 # case of EXTENDED_ARG 
        forIterOrigCfgSuccessors = frame.blockTracker.originalCfg[off]
        bodyBlockOffset = [
            o
            for o in forIterOrigCfgSuccessors.keys()
            if o != exitBlockOffset
        ]
        assert len(bodyBlockOffset) == 1
        bodyBlockOffset = bodyBlockOffset[0]
        if isinstance(a, HwIterator):
            curLoopInfo.mustBeEvaluatedInPreproc = False
            # if curLoopInfo.iteraionI == 0:
            #    self.dbgTracer.log(("for loop hw iterator", curBlockLabel))
            #    curBlock = a.hwInit(self, frame, curBlock)

            c, curCondBlock = a.hwCondition(self, frame, curBlock)
            assert isinstance(c, (SsaValue, HBitsConst)), c
            assert c._dtype.bit_length() == 1, (c, "Iterator continue condition must be 1b type")
            v = a.hwIterStepValue()
            frame.stack.append(PyBytecodeInPreproc(v))
            #
            #  cond:
            #  if (c)
            #    goto body;
            #  body:
            #    ...
            #    goto step;
            #  step:
            #    ...
            #    goto cond;
            #
            # create a step block
            # jump into loop body
            self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curCondBlock, bodyBlockOffset, c, None)
            latchBlock = self._insertLatchForLoop(frame, curBlockLabel)
            assert curLoopInfo.additionalLatchBlock  is None
            curLoopInfo.additionalLatchBlock = latchBlock
            curLoopInfo.onAdditionalLatchBlockPredecessorsAdded = lambda frame, bb: a.hwStep(self, frame, bb)
            curBlock = curCondBlock
            addExitJump = True
            cancelJumpToNextIterationOnExit = False
        else:
            if curLoopInfo.iteraionI == 0:
                self.dbgTracer.log(("for loop preproc", curBlockLabel))

            # preproc eval for loop
            curLoopInfo.mustBeEvaluatedInPreproc = True
            cancelJumpToNextIterationOnExit = True

            try:
                v = next(a)
                addExitJump = False
                # continue iteration, jump to next body
            except StopIteration:
                addExitJump = True
                # break iteration, jump outside of loop

        if addExitJump:
            # assert curLoop.entryPoint == forIter.offset
            # create only branch placeholder to delegate processing of this jump from the loop to a _translateBlockBody on a loop header

            # :attention: there may be issue with python3.12 doc, FOR_ITER is actually skipping END_FOR
            # There we can not skip instruction because it would be impossible to lookup block by offset.
            # Instead we add dummy NULL value on stack.
            frame.stack.append(NULL)
            self.dbgTracer.log(("for loop exit", curBlockLabel))
            branchPlaceholder = BranchTargetPlaceholder.create(curBlock)
            lei = LoopExitJumpInfo(None, curBlock, None, None, exitBlockOffset, None, None, branchPlaceholder, frame)
            frame.markJumpFromBodyOfCurrentLoop(lei)

            if cancelJumpToNextIterationOnExit:
                currentHeaderBlockLabel = frame.blockTracker._getBlockLabel(curLoopInfo.loop.entryPoint)
                currentBodyEntryBlockLabel = frame.blockTracker._getBlockLabel(bodyBlockOffset)
                # nextIterationBodyLabel = self._getNextIterationBlockLabel(frame.blockTracker, curLoopInfo, bodyBlockOffset)
                self._addNotGeneratedJump(frame, currentHeaderBlockLabel, currentBodyEntryBlockLabel)
        else:
            # jump to next body

            # :attention: Jump to exit block can not be marked as notGenerate immediately
            #   It must be done after last iteration because we need to keep exit block alive until the loop is completely resolved.
            frame.stack.append(PyBytecodeInPreproc(v))

            # mark jump from loop in header as not performed
            exitBlockLabel = frame.blockTracker._getBlockLabel(exitBlockOffset)
            exitInfo = LoopExitJumpInfo(False, curBlock, False, None, exitBlockLabel, None, None, None, frame)
            curLoopInfo.markJumpFromBodyOfLoop(exitInfo)
            # jump into loop body
            self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, bodyBlockOffset, None, None)

    def _translateInstructionJumpHw(self,
                                    frame: PyBytecodeFrame,
                                    curBlock: SsaBasicBlock,
                                    instr: Instruction):
        try:
            assert curBlock
            opcode = instr.opcode

            if opcode in (RETURN_VALUE, RETURN_CONST, RAISE_VARARGS, RERAISE):
                if opcode == RETURN_CONST:
                    retVal = instr.argval
                else:
                    retVal = frame.stack.pop()
                frame.returnPoints.append((frame, curBlock, retVal))
                self._onBlockGenerated(frame, self.blockToLabel[curBlock])
                return

            elif opcode in (JUMP_BACKWARD, JUMP_FORWARD, JUMP_BACKWARD_NO_INTERRUPT):
                self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, instr.argval, None, None)

                if not blockHasBranchPlaceholder(curBlock):
                    self._onBlockGenerated(frame, self.blockToLabel[curBlock])
            elif opcode == FOR_ITER:
                self._translateInctuctionJumpFOR_ITER(frame, curBlock, instr)
            else:
                condJumpCond = JUMP_OPS.get(opcode, None)
                if condJumpCond is not None:
                    cond = frame.stack.pop()
                    cond, curBlock = expandBeforeUse(self, instr.offset, frame, cond, curBlock)
                    if isinstance(cond, PyBytecodePreprocDivergence):
                        duplicateCodeUntilConvergencePoint = True
                        cond = cond.cond
                    else:
                        duplicateCodeUntilConvergencePoint = False
                    cond, curBlock = expandBeforeUse(self, instr.offset, frame, cond, curBlock)
                    if isinstance(cond, HwIO):
                        cond = cond._sig

                    compileTimeResolved = not isinstance(cond, (RtlSignal, HConst, SsaValue))
                    if not compileTimeResolved:
                        curBlock, cond = self.toSsa.visit_expr(curBlock, cond)

                    ifFalseOffset = self._getFalltroughOffset(frame, curBlock)
                    ifTrueOffset = instr.argval
                    if opcode == POP_JUMP_IF_FALSE:
                        # swap targets because condition is negated
                        ifTrueOffset, ifFalseOffset = ifFalseOffset, ifTrueOffset
                    elif opcode == POP_JUMP_IF_NOT_NONE:
                        assert compileTimeResolved, ("Can not check if HW value is not None, supports only non HW object", cond)
                        cond = cond is not None
                    elif opcode == POP_JUMP_IF_NONE:
                        assert compileTimeResolved, ("Can not check if HW value is None, supports only non HW object", cond)
                        cond = cond is None

                    if compileTimeResolved:
                        assert not duplicateCodeUntilConvergencePoint
                        if cond:
                            self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, ifTrueOffset, None, None)
                            self._onBlockNotGeneratedPotentiallyOutOfLoop(frame, curBlock, ifFalseOffset)
                        else:
                            self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, ifFalseOffset, None, None)
                            self._onBlockNotGeneratedPotentiallyOutOfLoop(frame, curBlock, ifTrueOffset)
                    else:
                        if isinstance(cond, HConst):
                            assert not duplicateCodeUntilConvergencePoint
                            if cond:
                                self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, ifTrueOffset, cond, None)
                                self._onBlockNotGeneratedPotentiallyOutOfLoop(frame, curBlock, ifFalseOffset)

                            else:
                                self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, ifFalseOffset, ~cond, None)
                                self._onBlockNotGeneratedPotentiallyOutOfLoop(frame, curBlock, ifTrueOffset)

                        else:
                            if duplicateCodeUntilConvergencePoint:
                                raise NotImplementedError()
                            secondBranchFrame = copy(frame)
                            self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, ifTrueOffset, cond, None)
                            # cond = 1 because we did check in ifTrue branch and this is "else branch"
                            firstBranchFrame = self.callStack[-1]
                            self.callStack[-1] = secondBranchFrame
                            self._getOrCreateSsaBasicBlockAndJumpRecursively(secondBranchFrame, curBlock, ifFalseOffset, BIT.from_py(1), None)
                            self.callStack[-1] = firstBranchFrame

                    if not blockHasBranchPlaceholder(curBlock):
                        self._onBlockGenerated(frame, self.blockToLabel[curBlock])

                else:
                    raise NotImplementedError(instr)

        except HlsSyntaxError:
            raise  # do not decorate already decorated exceptions

        except Exception as e:
            # create decorated exception
            raise createInstructionException(e, frame, instr) from e.__cause__

