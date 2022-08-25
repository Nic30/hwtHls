from copy import copy
from dis import Instruction
from itertools import islice
from typing import Optional, List, Tuple, Union

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.types.defs import BIT
from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.errors import HlsSyntaxError
from hwtHls.frontend.pyBytecode.blockPredecessorTracker import BlockLabel
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.frontend.pyBytecode.fromPythonLowLevel import PyBytecodeToSsaLowLevel
from hwtHls.frontend.pyBytecode.indexExpansion import expandBeforeUse
from hwtHls.frontend.pyBytecode.instructions import JUMP_ABSOLUTE, JUMP_FORWARD, \
    JUMP_IF_FALSE_OR_POP, JUMP_IF_TRUE_OR_POP, POP_JUMP_IF_FALSE, \
    POP_JUMP_IF_TRUE, FOR_ITER, JUMP_OPS, RETURN_VALUE
from hwtHls.frontend.pyBytecode.loopMeta import PyBytecodeLoopInfo, \
    BranchTargetPlaceholder, LoopExitJumpInfo
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc, \
    PyBytecodePreprocDivergence
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import ConditionBlockTuple
from hwtHls.ssa.value import SsaValue


class PyBytecodeToSsa(PyBytecodeToSsaLowLevel):
    """
    This class translates Python bytecode to hwtHls.ssa. The preprocessor tries to evaluate as much as possible
    and only things which do depend on hardware evaluated values are in output SSA code.
    
    Methods in this class specifically are responsible for translation of loops and jumps, the rest in base class.

    The SSA basic blocks are constructed on jumps in instruction list.
    A single jump target may generate multiple basic blocks if it is part of the preprocessor evaluated loop.
  
    Description of Python bytecode:
        * https://docs.python.org/3/library/dis.html
        * https://towardsdatascience.com/understanding-python-bytecode-e7edaae8734d

    Custom Python interprets:
        * https://github.com/pypyjs/pypy
        * https://github.com/kentdlee/CoCo

    :note: The block is generated for every jump target, even if it is just in preprocessor.
        If it is used just in preprocessor the jump condition of this block is resolved compile time.
        (Because for loops we may find out that the loop is HW evaluated somewhere inside of cycle body)
        And thus the blocks which were generated in preprocessor are entry points of clusters of blocks generated for HW
        connected in linear sequence or are entirely disconnected because preprocessor optimized them out. 

    :note: HW evaluated loop is an opposite of preprocessor loop. It is not evaluated during translation.
        The preprocessor loop is evaluated during the translation and each iteration replicates all block of the loop
        to create new iteration.
    """

    def _getOrCreateSsaBasicBlockAndJumpRecursively(self,
            frame: PyBytecodeFrame,
            curBlock: SsaBasicBlock,
            isLastJumpFromCur: bool,
            sucBlockOffset: int,
            cond: Union[None, HValue, RtlSignal, SsaValue],
            branchPlaceholder: Optional[BranchTargetPlaceholder],
            allowJumpToNextLoopIteration=False):
        """
        Get existing or new block, prepare jump to this block and translate body of blocks recursively.
        If the loop exit is detected the meta information is saved to loop for later use when all loop exits are resolved.
        """
        # print("jmp", curBlock.label, "->", sucBlockOffset, cond)
        res = self._prepareSsaBlockBeforeTranslation(frame,
            curBlock, isLastJumpFromCur, sucBlockOffset, cond, branchPlaceholder, allowJumpToNextLoopIteration)

        if res is not None and res.dstBlockIsNew:
            assert res.branchPlaceholder is None, (curBlock.label, "->", sucBlockOffset, cond)
            self._translateBlockBody(frame, res.isExplicitLoopReenter, res.dstBlockLoops, res.dstBlockOffset, res.dstBlock)
            
    def _prepareSsaBlockBeforeTranslation(self,
            frame: PyBytecodeFrame,
            curBlock: SsaBasicBlock,
            isLastJumpFromCur: bool,
            sucBlockOffset: int,
            cond: Union[None, HValue, RtlSignal, SsaValue],
            branchPlaceholder: Optional[BranchTargetPlaceholder],
            allowJumpToNextLoopIteration=False) -> Optional[LoopExitJumpInfo]:
        """
        Prepare the jump and block to jump or create placeholder if this is the jump from the loop.
        """

        if not allowJumpToNextLoopIteration and frame.isJumpFromCurrentLoopBody(sucBlockOffset):
            # this is the case where we can not generate jump target because we do not know for sure if this
            # will be some existing block or we will have to generate new one because of loop expansion
            if branchPlaceholder is None:
                branchPlaceholder = BranchTargetPlaceholder.create(curBlock)
            lei = LoopExitJumpInfo(None, curBlock, cond, None, sucBlockOffset, None, None, branchPlaceholder, frame)
            frame.markJumpFromBodyOfCurrentLoop(lei)
            return None

        # if this is a jump out of current loop
        if isinstance(cond, HValue):
            assert cond, (cond, "If this was not True the jump should not be evaluated at the first place")
            cond = None  # always jump, but we need this value to know that this will be unconditional jump only in HW
        
        blockTracker = frame.blockTracker
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
                    newPrefix = tuple(blockTracker._getBlockLabelPrefix(sucBlockOffset))
               
                    for bl in blockTracker.cfgAddPrefixToLoopBlocks(sucLoop, newPrefix):
                        bl: BlockLabel
                        self._onBlockGenerated(frame, bl)

                    self._debugDump(frame, f"_afterPrefix_{newPrefix}")

        # if this is a jump just in linear code or inside body of the loop
        sucBlockLabel = blockTracker._getBlockLabel(sucBlockOffset)
        sucBlock, sucBlockIsNew = self._getOrCreateSsaBasicBlock(sucBlockLabel)
        if branchPlaceholder is None:
            curBlock.successors.addTarget(cond, sucBlock)
        else:
            branchPlaceholder.replace(cond, sucBlock)

        if isLastJumpFromCur:
            # if all predecessors and successors are know mark this in CFG recursively
            curBlockLabel = self.blockToLabel[curBlock]
            curBlockOffset = curBlockLabel[-1]
            curLoop = frame.loops.get(curBlockOffset, None)
            if curLoop is None:
                self._onBlockGenerated(frame, curBlockLabel)

        return LoopExitJumpInfo(sucBlockIsNew, curBlock, cond,
                                sucBlock, sucBlockOffset, sucLoops, isExplicitLoopReenter, None, frame)

    def _applyLoopPragma(self, headerBlock: SsaBasicBlock, loopInfo:PyBytecodeLoopInfo):
        """
        In LLVM loop metadata are specified on jumps from latch blocks to a loop header.
        :see: Loop::setLoopID, Loop::getLoopID 
        """
        anyJumpToHeaderFound = False
        latchOrExitBlocks = set(j.srcBlock for j in loopInfo.jumpsFromLoopBody)
        
        for pred in headerBlock.predecessors:
            if pred in latchOrExitBlocks:
                for i, t in enumerate(pred.successors.targets):
                    if t.dstBlock is headerBlock:
                        found = True
                        meta = t.meta
                        if meta is None:
                            meta = []
                            pred.successors.targets[i] = ConditionBlockTuple(t.condition, t.dstBlock, meta)

                        meta.extend(loopInfo.pragma)
    
                assert found, ("Jump from latch block ", pred.label, " to header block ", headerBlock.label,
                               " was from loop was not found", j.srcBlock.successors.targets)
                anyJumpToHeaderFound |= found

    def _translateBlockBody(self,
            frame: PyBytecodeFrame,
            isExplicitLoopReenter: bool,
            loops: Optional[PyBytecodeLoopInfo],
            blockOffset: int,
            block: SsaBasicBlock):
            """
            Translate block from bytecode to SSA and recursively follow all branches from this block.
            """
            self._translateBytecodeBlock(frame, frame.bytecodeBlocks[blockOffset], block)

            if not isExplicitLoopReenter and loops:
                # now header block of loop was already translated by previous _translateBytecodeBlock()
                loopInfo: PyBytecodeLoopInfo = frame.loopStack[-1]
                assert loopInfo.loop is loops[-1]
                    
                if loopInfo.mustBeEvaluatedInHw():
                    self._finalizeJumpsFromHwLoopBody(frame, block, blockOffset, loopInfo)
                    if loopInfo.pragma:
                        self._applyLoopPragma(block, loopInfo)

                else:
                    self._runPreprocessorLoop(frame, loopInfo)
                    if loopInfo.pragma:
                        raise NotImplementedError("_runPreprocessorLoop + pragma", loopInfo.pragma)

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
        loopExitsToTranslate = []
        headerBlockLabels = []
        while loopInfo.jumpsFromLoopBody:
            # print("preprocessing loop", loopInfo.loop, loopInfo.jumpsFromLoopBody)
            assert frame.loopStack[-1] is loopInfo, (loopInfo, frame.loopStack)
            
            jumpsFromLoopBody = loopInfo.jumpsFromLoopBody
            _jumpsFromLoopBody = []
            for j in jumpsFromLoopBody:
                j: LoopExitJumpInfo
                
                isLoopReenter = loopInfo.loop.entryPoint[-1] == j.dstBlockOffset
                if not isLoopReenter and len(frame.loopStack) > 1:
                    parentLoop: PyBytecodeLoopInfo = frame.loopStack[-2]
                    if parentLoop.isJumpFromLoopBody(j.dstBlockOffset):
                        # if this jump is also jump from parent loop delegate it to parent loop
                        parentLoop.jumpsFromLoopBody.append(j)
                        continue
                
                _jumpsFromLoopBody.append((isLoopReenter, j))

            if not _jumpsFromLoopBody:
                break
            _jumpsFromLoopBody.sort(key=lambda x: not x[0])

            headerBlockLabel = blockTracker._getBlockLabel(loopInfo.loop.entryPoint[-1])
            headerBlockLabels.append(headerBlockLabel)

            loopInfo.markNewIteration()
            
            successorsToTranslate: List[Tuple[bool, LoopExitJumpInfo]] = []
            for i, (isLoopReenter, j) in enumerate(_jumpsFromLoopBody):
                srcBlockLabel = self.blockToLabel[j.srcBlock]
                dstBlockLabel = blockTracker._getBlockLabel(j.dstBlockOffset)
                
                # update CFG after we resolved reenter or loop exit
                if isLoopReenter:
                    blockTracker.cfg.add_edge(srcBlockLabel, dstBlockLabel)
                    # a case where next block is current block which is a loop header
                    assert frame.loopStack[-1].loop is loopInfo.loop
                    newPrefix = tuple(blockTracker._getBlockLabelPrefix(j.dstBlockOffset))
                    # print("cfgCopyLoopBlocks", loopInfo.loop, newPrefix)
                    for bl in blockTracker.cfgCopyLoopBlocks(loopInfo.loop, newPrefix):
                        bl: BlockLabel
                        self._onBlockGenerated(j.frame, bl)
                    # self._onBlockGenerated(frame, dstBlockLabel)

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
                        self._isLastJumpFromBlock([j for  (_, j) in _jumpsFromLoopBody], j.srcBlock, i) and
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
        self._debugDump(frame, f"_afterLoopExit{loopInfo.loop.entryPoint[-1]}")
        for src, dst in loopInfo.notGeneratedExits:
            self._addNotGeneratedBlock(frame, src, dst)

    def _finalizeJumpsFromHwLoopBody(self, frame: PyBytecodeFrame, headerBlock: SsaBasicBlock, headerOffset: int, loopInfo: PyBytecodeLoopInfo):
        blockTracker = frame.blockTracker
        # connect the loop header re-entry to a current loop header
        # and continue execution on loop exit points
        headerLabel = self.blockToLabel[headerBlock]
        jumpsFromLoopBody = loopInfo.jumpsFromLoopBody
        
        # delete next iteration block header because this loop will not be unrolled in preprocessor
        # :attention: must be done before processing of jumps from the loop because it works in DFS and
        #             we may step on this block before we remove it
        # we will not copy the loop body but instead create a regular loop
        successorsToTranslate: List[LoopExitJumpInfo] = []
        for i, j in enumerate(jumpsFromLoopBody):
            j: LoopExitJumpInfo
            isLastJumpFromBlock = self._isLastJumpFromBlock(jumpsFromLoopBody, j.srcBlock, i)
            isJumpToHeader = j.dstBlockOffset == headerOffset
            srcBlockLabel = self.blockToLabel[j.srcBlock]
            # fill back the original backedge (srcBlock -> header) in the loop CFG
            if isJumpToHeader:
                blockTracker.cfg.add_edge(srcBlockLabel, headerLabel)
                # else the edge should be already present
                c = j.cond
                if isinstance(c, HValue):
                    assert int(c) == 1, c
                    c = None
                # srcBlock.successors.addTarget(c, headerBlock)
                j.branchPlaceholder.replace(c, headerBlock)

                # make next look header as not generated
                loopInfo.iteraionI += 1
                nextIterationLoopHeaderLabel = blockTracker._getBlockLabel(j.dstBlockOffset)
                loopInfo.iteraionI -= 1
                self._addNotGeneratedBlock(j.frame, srcBlockLabel, nextIterationLoopHeaderLabel)
                if isLastJumpFromBlock and srcBlockLabel not in blockTracker.generated:
                    self._onBlockGenerated(j.frame, srcBlockLabel)

            else:
                sucInfo = self._translateJumpFromCurrentLoop(j.frame, False,
                       j.srcBlock, j.cond, j.dstBlockOffset, False, j.branchPlaceholder)
                if sucInfo is not None and sucInfo.dstBlockIsNew:
                    successorsToTranslate.append((isLastJumpFromBlock, srcBlockLabel, sucInfo))
                elif (isLastJumpFromBlock and j.srcBlock is not headerBlock):
                    self._onBlockGenerated(j.frame, srcBlockLabel)

        # [todo] do not mark if this header is shared with parent loop
        frame.exitLoop()
        for isLastJumpFromBlock, srcBlockLabel, sucInfo in successorsToTranslate:
            sucInfo: LoopExitJumpInfo
            assert sucInfo.branchPlaceholder is None, sucInfo
            self._translateBlockBody(sucInfo.frame, sucInfo.isExplicitLoopReenter, sucInfo.dstBlockLoops,
                                     sucInfo.dstBlockOffset, sucInfo.dstBlock)
                    # because the block was in the loop and we see its last successor we know that this block was completly generated
            if (isLastJumpFromBlock and j.srcBlock is not headerBlock):
                self._onBlockGenerated(sucInfo.frame, srcBlockLabel)
        for src, dst in loopInfo.notGeneratedExits:
            self._addNotGeneratedBlock(frame, src, dst)
        if headerLabel not in blockTracker.generated:
            self._onBlockGenerated(frame, headerLabel)
        
    def _isLastJumpFromBlock(self,
                             jumpsFromLoopBody: List[Tuple[Union[None, SsaValue, HValue], SsaBasicBlock, int]],
                             srcBlock: SsaBasicBlock,
                             i: int):
        return not any(j.srcBlock is srcBlock for j in islice(jumpsFromLoopBody, i + 1, None))

    def _translateJumpFromCurrentLoop(self, frame: PyBytecodeFrame,
                                      isLastJumpFromSrc: bool, srcBlock: SsaBasicBlock, cond,
                                      dstBlockOffset: int,
                                      translateImmediately: bool,
                                      branchPlaceholder: Optional[BranchTargetPlaceholder],
                                      allowJumpToNextLoopIteration=False) -> Optional[LoopExitJumpInfo]:
        """
        Prepare dst block and create jump between src and dst block.
        :returns: tuple (sucBlockIsNew, srcBlock, sucBlock, sucBlockOffset, sucLoops, isExplicitLoopReenter)
        """
        if len(frame.loopStack) > 1:
            parentLoop: PyBytecodeLoopInfo = frame.loopStack[-2]
            if (dstBlockOffset,) not in parentLoop.loop.allBlocks or parentLoop.loop.entryPoint[-1] == dstBlockOffset:
                # if it is jump also from parent block forward handling to parent loop
                lei = LoopExitJumpInfo(None, srcBlock, cond, None, dstBlockOffset, None, None, branchPlaceholder, frame)
                parentLoop.markJumpFromBodyOfLoop(lei)
                return None

        if not allowJumpToNextLoopIteration:
            li = frame.loopStack.pop()

        if translateImmediately:
            self._getOrCreateSsaBasicBlockAndJumpRecursively(frame,
                srcBlock, isLastJumpFromSrc, dstBlockOffset, cond, branchPlaceholder,
                allowJumpToNextLoopIteration=allowJumpToNextLoopIteration)
            res = None

        else:
            res = self._prepareSsaBlockBeforeTranslation(frame,
                srcBlock, isLastJumpFromSrc, dstBlockOffset, cond, branchPlaceholder,
                allowJumpToNextLoopIteration=allowJumpToNextLoopIteration)

        if not allowJumpToNextLoopIteration:
            frame.loopStack.append(li)
        return res

    def _translateBytecodeBlock(self,
            frame: PyBytecodeFrame,
            instructions: List[Instruction],
            curBlock: SsaBasicBlock):
        """
        Evaluate instruction list and translate to SSA all which is using HW types and which can not be evaluated compile time.
        """
        if instructions[0].opcode == FOR_ITER:
            assert len(instructions) == 1, ("It is expected that FOR_ITER opcode is alone in the block", instructions)
            forIter: Instruction = instructions[0]
            # preproc eval for loop
            curLoop: PyBytecodeLoopInfo = frame.loopStack[-1]
            assert curLoop.loop.entryPoint[-1] == self.blockToLabel[curBlock][-1], (curLoop, curBlock)
            curLoop.mustBeEvaluatedInPreproc = True
            a = frame.stack[-1]
            bodyBlockOffset = forIter.offset + 2
            exitBlockOffset = forIter.argval
            curBlockLabel = self.blockToLabel[curBlock]
            try:
                v = next(a)
                frame.stack.append(PyBytecodeInPreproc(v))
            except StopIteration:
                # create only branch placeholder to delegate processing of this jump from the loop to a _translateBlockBody on a loop header
                branchPlaceholder = BranchTargetPlaceholder.create(curBlock)
                lei = LoopExitJumpInfo(None, curBlock, None, None, exitBlockOffset, None, None, branchPlaceholder, frame)
                frame.markJumpFromBodyOfCurrentLoop(lei)
                bodyBlockLabel = frame.blockTracker._getBlockLabel(bodyBlockOffset)
                self._addNotGeneratedBlock(frame, curBlockLabel, bodyBlockLabel)
                frame.stack.pop()  # pop iterator itself
                return

            # jump into loop body
            exitBlockLabel = frame.blockTracker._getBlockLabel(exitBlockOffset)
            curLoop.notGeneratedExits.append((curBlockLabel, exitBlockLabel))
            self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, True, bodyBlockOffset, None, None)

        else:
            for last, instr in iter_with_last(instructions):
                if last and instr.opcode in JUMP_OPS:
                    self._translateInstructionJumpHw(frame, curBlock, instr)
                elif instr.opcode == RETURN_VALUE:
                    assert last, instr
                    self._onBlockGenerated(frame, self.blockToLabel[curBlock])
                    frame.returnPoints.append((frame, curBlock, frame.stack.pop()))
                else:
                    curBlock = self._translateBytecodeBlockInstruction(frame, curBlock, instr)
                    if last:
                        # jump to next block, there was no explicit jump because this is regular code flow, but the next instruction
                        # is jump target
                        self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, True, instr.offset + 2, None, None)

    def _translateInstructionJumpHw(self,
                                    frame: PyBytecodeFrame,
                                    curBlock: SsaBasicBlock,
                                    instr: Instruction):
        try:
            assert curBlock
            opcode = instr.opcode

            if opcode == RETURN_VALUE:
                self._onBlockGenerated(frame, self.blockToLabel[curBlock])
                return None

            elif opcode == JUMP_ABSOLUTE or opcode == JUMP_FORWARD:
                self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, True, instr.argval, None, None)

            elif opcode in (
                    JUMP_IF_FALSE_OR_POP,
                    JUMP_IF_TRUE_OR_POP,
                    POP_JUMP_IF_FALSE,
                    POP_JUMP_IF_TRUE):
                if opcode in (JUMP_IF_FALSE_OR_POP,
                              JUMP_IF_TRUE_OR_POP):
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

                ifFalseOffset = instr.offset + 2
                ifTrueOffset = instr.argval
                if opcode in (JUMP_IF_FALSE_OR_POP, POP_JUMP_IF_FALSE):
                    # swap targets because condition is reversed
                    ifTrueOffset, ifFalseOffset = ifFalseOffset, ifTrueOffset

                if compileTimeResolved:
                    assert not duplicateCodeUntilConvergencePoint
                    if cond:
                        self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, True, ifTrueOffset, None, None)
                        self._onBlockNotGenerated(frame, curBlock, ifFalseOffset)
                    else:
                        self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, True, ifFalseOffset, None, None)
                        self._onBlockNotGenerated(frame, curBlock, ifTrueOffset)
                else:
                    if isinstance(cond, HValue):
                        assert not duplicateCodeUntilConvergencePoint
                        if cond:
                            self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, True, ifTrueOffset, cond, None)
                            self._onBlockNotGenerated(frame, curBlock, ifFalseOffset)
                     
                        else:
                            self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, True, ifFalseOffset, ~cond, None)
                            self._onBlockNotGenerated(frame, curBlock, ifTrueOffset)

                    else:
                        if duplicateCodeUntilConvergencePoint:
                            raise NotImplementedError()
                        secondBranchFrame = copy(frame)
                        self._getOrCreateSsaBasicBlockAndJumpRecursively(frame, curBlock, False, ifTrueOffset, cond, None)
                        # cond = 1 because we did check in ifTrue branch and this is "else branch"
                        firstBranchFrame = self.callStack[-1]
                        self.callStack[-1] = secondBranchFrame
                        self._getOrCreateSsaBasicBlockAndJumpRecursively(secondBranchFrame, curBlock, True, ifFalseOffset, BIT.from_py(1), None)
                        self.callStack[-1] = firstBranchFrame
            else:
                raise NotImplementedError(instr)

        except HlsSyntaxError:
            raise  # do not decorate already decorated exceptions

        except Exception:
            # create decorated exception
            raise self._createInstructionException(frame, instr)

