from copy import copy
from dis import Instruction, dis
from pathlib import Path
from types import FunctionType
from typing import Optional, List, Tuple

from hwt.hdl.types.defs import BIT
from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.errors import HlsSyntaxError
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode.blockPredecessorTracker import BlockLabel
from hwtHls.frontend.pyBytecode.errorUtils import createInstructionException
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.frontend.pyBytecode.fromPythonLowLevel import PyBytecodeToSsaLowLevel, \
    SsaBlockGroup, JumpCondition
from hwtHls.frontend.pyBytecode.indexExpansion import expandBeforeUse
from hwtHls.frontend.pyBytecode.instructions import JUMP_FORWARD, JUMP_BACKWARD, \
    JUMP_IF_FALSE_OR_POP, JUMP_IF_TRUE_OR_POP, RETURN_VALUE, RAISE_VARARGS, RERAISE, \
    JUMP_BACKWARD_NO_INTERRUPT, JUMP_OPS, POP_JUMP_FORWARD_IF_FALSE, \
    POP_JUMP_BACKWARD_IF_FALSE, POP_JUMP_BACKWARD_IF_NOT_NONE, \
    POP_JUMP_BACKWARD_IF_NONE, POP_JUMP_FORWARD_IF_NOT_NONE,\
    POP_JUMP_FORWARD_IF_NONE
from hwtHls.frontend.pyBytecode.loopMeta import PyBytecodeLoopInfo, \
    BranchTargetPlaceholder, LoopExitJumpInfo
from hwtHls.frontend.pyBytecode.markers import PyBytecodePreprocDivergence
from hwtHls.frontend.pyBytecode.utils import isLastJumpFromBlock, blockHasBranchPlaceholder
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue


# [TODO] support for debugger
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
                
        self.toSsa = HlsAstToSsa(self.hls.ssaCtx, fnName, None)

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
        finally:
            if self.debugCfgFinal:
                self._debugDump(frame, "_final")

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
                    # print("cfgCopyLoopBlocks", loopInfo.loop, newPrefix)
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

    def _finalizeJumpsFromHwLoopBody(self, frame: PyBytecodeFrame,
                                     headerBlock: SsaBasicBlock,
                                     headerOffset: int,
                                     loopInfo: PyBytecodeLoopInfo):
        """
        connect the loop header re-entry to a current loop header and continue execution on loop exit points
        """
        blockTracker = frame.blockTracker
        headerLabel = self.blockToLabel[headerBlock]
        jumpsFromLoopBody = loopInfo.jumpsFromLoopBody

        # delete next iteration block header because this loop will not be unrolled in preprocessor
        # :attention: must be done before processing of jumps from the loop because it works in DFS and
        #             we may step on this block before we remove it
        # we will not copy the loop body but instead create a regular loop
        successorsToTranslate: List[Tuple[BlockLabel, LoopExitJumpInfo, Optional[BlockLabel]]] = []
        for j in jumpsFromLoopBody:
            j: LoopExitJumpInfo
            isJumpToHeader = j.dstBlockOffset == headerOffset
            srcBlockLabel = self.blockToLabel[j.srcBlock]
            # fill back the original backedge (srcBlock -> header) in the loop CFG
            c = j.cond

            if isJumpToHeader:
                blockTracker.cfg.add_edge(srcBlockLabel, headerLabel)
                # else the edge should be already present
                if isinstance(c, bool):
                    assert not c
                    assert j.branchPlaceholder is None, j
                    dstBlockLabel = self.blockToLabel[j.dstBlock]
                    self._addNotGeneratedJump(j.frame, srcBlockLabel, dstBlockLabel)
                    continue

                elif isinstance(c, HValue):
                    assert int(c) == 1, c
                    c = None

                j.branchPlaceholder.replace(c, headerBlock)

                # make next iteration header block as not generated
                loopInfo.iteraionI += 1
                nextIterationLoopHeaderLabel = blockTracker._getBlockLabel(j.dstBlockOffset)
                loopInfo.iteraionI -= 1
                self._addNotGeneratedJump(j.frame, srcBlockLabel, nextIterationLoopHeaderLabel)

                if not blockHasBranchPlaceholder(j.srcBlock):
                    self._onBlockGenerated(j.frame, srcBlockLabel)

            else:
                if isinstance(c, bool):
                    assert not c
                    assert j.branchPlaceholder is None, j
                    successorsToTranslate.append((srcBlockLabel, j, frame.blockTracker._getBlockLabel(j.dstBlockOffset)))

                else:
                    sucInfo = self._translateJumpFromCurrentLoop(j.frame, False,
                           j.srcBlock, j.cond, j.dstBlockOffset, False, j.branchPlaceholder)

                    if sucInfo is not None and sucInfo.dstBlockIsNew:
                        successorsToTranslate.append((srcBlockLabel, sucInfo, None))

                    elif not blockHasBranchPlaceholder(j.srcBlock) and j.srcBlock is not headerBlock:
                        self._onBlockGenerated(j.frame, srcBlockLabel)

        # [todo] do not mark if this header is shared with parent loop
        frame.exitLoop()
        for srcBlockLabel, sucInfo, dstBlockLabel in successorsToTranslate:
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



    def _translateInstructionJumpHw(self,
                                    frame: PyBytecodeFrame,
                                    curBlock: SsaBasicBlock,
                                    instr: Instruction):
        try:
            assert curBlock
            opcode = instr.opcode

            if opcode == RETURN_VALUE or opcode == RAISE_VARARGS or opcode == RERAISE:
                self._onBlockGenerated(frame, self.blockToLabel[curBlock])
                return

            elif opcode in (JUMP_BACKWARD, JUMP_FORWARD, JUMP_BACKWARD_NO_INTERRUPT):
                self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, instr.argval, None, None)

                if not blockHasBranchPlaceholder(curBlock):
                    self._onBlockGenerated(frame, self.blockToLabel[curBlock])
            else:
                condJumpCond = JUMP_OPS.get(opcode, None)
                if condJumpCond is not None:
                    if opcode in (JUMP_IF_FALSE_OR_POP, JUMP_IF_TRUE_OR_POP):
                        raise NotImplementedError("stack pop depends on hw evaluated condition")

                    cond = frame.stack.pop()
                    cond, curBlock = expandBeforeUse(self, instr.offset, frame, cond, curBlock)
                    if isinstance(cond, PyBytecodePreprocDivergence):
                        duplicateCodeUntilConvergencePoint = True
                        cond = cond.cond
                    else:
                        duplicateCodeUntilConvergencePoint = False
                    cond, curBlock = expandBeforeUse(self, instr.offset, frame, cond, curBlock)
                    if isinstance(cond, Interface):
                        cond = cond._sig

                    compileTimeResolved = not isinstance(cond, (RtlSignal, HValue, SsaValue))
                    if not compileTimeResolved:
                        curBlock, cond = self.toSsa.visit_expr(curBlock, cond)

                    ifFalseOffset = self._getFalltroughOffset(frame, curBlock)
                    ifTrueOffset = instr.argval
                    if opcode in (JUMP_IF_FALSE_OR_POP,
                                  POP_JUMP_FORWARD_IF_FALSE,
                                  POP_JUMP_BACKWARD_IF_FALSE):
                        # swap targets because condition is negated
                        ifTrueOffset, ifFalseOffset = ifFalseOffset, ifTrueOffset
                    elif opcode in (POP_JUMP_BACKWARD_IF_NOT_NONE, POP_JUMP_FORWARD_IF_NOT_NONE):
                        assert compileTimeResolved, cond
                        cond = cond is not None
                    elif opcode in (POP_JUMP_BACKWARD_IF_NONE, POP_JUMP_FORWARD_IF_NONE):
                        assert compileTimeResolved, cond
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
                        if isinstance(cond, HValue):
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

