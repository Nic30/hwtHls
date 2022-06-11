from copy import copy
from dis import Instruction
from itertools import islice
from typing import Optional, List, Tuple, Union

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.types.defs import BIT
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.errors import HlsSyntaxError
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.translation.fromPython.blockPredecessorTracker import BlockLabel
from hwtHls.ssa.translation.fromPython.frame import PyBytecodeFrame, \
    PyBytecodeLoopInfo, BranchTargetPlaceholder, LoopExitJumpInfo
from hwtHls.ssa.translation.fromPython.fromPythonLowLevel import PyBytecodeToSsaLowLevel
from hwtHls.ssa.translation.fromPython.indexExpansion import expandBeforeUse
from hwtHls.ssa.translation.fromPython.instructions import JUMP_ABSOLUTE, JUMP_FORWARD, \
    JUMP_IF_FALSE_OR_POP, JUMP_IF_TRUE_OR_POP, POP_JUMP_IF_FALSE, \
    POP_JUMP_IF_TRUE, FOR_ITER, JUMP_OPS, RETURN_VALUE
from hwtHls.ssa.translation.fromPython.markers import PyBytecodeInPreproc
from hwtHls.ssa.value import SsaValue


class PyBytecodeToSsa(PyBytecodeToSsaLowLevel):
    """
    This class translates Python bytecode to hwtHls.ssa
    Methods in this class specifically are responsible for translation of loops and jumps, the rest in base class.

    The SSA basic blocks are constructed from jump targets in instruction list.
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
            curBlock: SsaBasicBlock,
            isLastJumpFromCur: bool,
            sucBlockOffset: int,
            cond: Union[None, HValue, RtlSignal, SsaValue],
            frame: PyBytecodeFrame,
            branchPlaceholder: Optional[BranchTargetPlaceholder],
            allowJumpToNextLoopIteration=False):
        """
        When resolving a new block we need to check if this block is in some loop and if this loop
        is HW evaluated or expanded in preprocessor.
        The loop must be HW evaluated if any break/jump condition is HW evaluated expression.
        This involves conditions for jumps:
        * from body to behind loop
        * from body to header
        * from header to body or behind the loop
        
        Problem there is that the code branches are processes in DFS manner. That means that we may step upon non HW condition
        but there may be a HW condition which drives the loop iteration scheme.
        """
        # print("jmp", curBlock.label, "->", sucBlockOffset, cond)
        res = self._prepareSsaBlockBeforeTranslation(
            curBlock, isLastJumpFromCur, sucBlockOffset, cond, frame, branchPlaceholder, allowJumpToNextLoopIteration)

        if res is not None and res.dstBlockIsNew:
            assert res.branchPlaceholder is None, (curBlock.label, "->", sucBlockOffset, cond)
            self._translateBlockBody(res.isExplicitLoopReenter, res.dstBlockLoops, res.dstBlockOffset, res.dstBlock, frame)
            
    def _prepareSsaBlockBeforeTranslation(self, curBlock: SsaBasicBlock,
            isLastJumpFromCur: bool,
            sucBlockOffset: int,
            cond: Union[None, HValue, RtlSignal, SsaValue],
            frame: PyBytecodeFrame,
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
            lei = LoopExitJumpInfo(None, curBlock, cond, None, sucBlockOffset, None, None, branchPlaceholder)
            frame.markJumpFromBodyOfCurrentLoop(lei)
            return None

        # if this is a jump out of current loop
        if isinstance(cond, HValue):
            assert cond, (cond, "If this was not True the jump should not be evaluated at the first place")
            cond = None  # always jump, but we need this value to know that this will be unconditional jump only in HW
        
        blockTracker = self.blockTracker
        sucLoops = self.loops.get(sucBlockOffset, None)
        isExplicitLoopReenter = False
        if sucLoops: 
            # if entering some loop we ned to add prefix to block labels or copy blocks for new iteration
            # if this is a preprocessor loop
            isExplicitLoopReenter = frame.isLoopReenter(sucLoops[-1]) # [fixme]
            if not isExplicitLoopReenter:
                # rename every loop members to have name scope to this loop
                for sucLoop in sucLoops:
                    frame.enterLoop(sucLoop)
                    newPrefix = tuple(blockTracker._getBlockLabelPrefix(sucBlockOffset))
               
                    for bl in blockTracker.cfgAddPrefixToLoopBlocks(sucLoop, newPrefix):
                        bl: BlockLabel
                        self._onBlockGenerated(bl)

            self._debugDump()

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
            curLoop = self.loops.get(curBlockOffset, None)
            if curLoop is None:
                self._onBlockGenerated(curBlockLabel)

        return LoopExitJumpInfo(sucBlockIsNew, curBlock, cond,
                                sucBlock, sucBlockOffset, sucLoops, isExplicitLoopReenter, None)

    def _translateBlockBody(self,
            isExplicitLoopReenter: bool,
            loops: Optional[PyBytecodeLoopInfo],
            blockOffset: int,
            block: SsaBasicBlock,
            frame: PyBytecodeFrame,):
            """
            Translate block from bytecode to SSA and recursively follow all branches from this block.
            """
            self._translateBytecodeBlock(self.bytecodeBlocks[blockOffset], frame, block)

            if not isExplicitLoopReenter and loops:
                loopInfo: PyBytecodeLoopInfo = frame.loopStack[-1]
                assert loopInfo.loop is loops[-1]
                    
                if loopInfo.mustBeEvaluatedInHw():
                    #print("hw loop, ", loopInfo.loop.entryPoint, loopInfo.jumpsFromLoopBody)
                    self._finalizeJumpsFromHwLoopBody(block, blockOffset, loopInfo, frame)
                else:
                    #print("preproc loop, ", loopInfo.loop.entryPoint, loopInfo.jumpsFromLoopBody)
                    self._runPreprocessorLoop(loopInfo, frame)

    def _runPreprocessorLoop(self, loopInfo: PyBytecodeLoopInfo, frame: PyBytecodeFrame):
        """
        Continue evaluation of the loop in preprocessor.

        Called once we evaluate a single loop body and we can decide that this loop does not have
        control dependent on some hw evaluated condition.
        """
        blockTracker = self.blockTracker
        assert loopInfo.jumpsFromLoopBody, ("Preproc loop must have exit point", loopInfo.loop, frame.loopStack)
        
        while loopInfo.jumpsFromLoopBody:
            # print("preprocessing loop", loopInfo.loop, loopInfo.jumpsFromLoopBody)
            assert frame.loopStack[-1] is loopInfo, (loopInfo, frame.loopStack)
            assert len(loopInfo.jumpsFromLoopBody) == 1, (loopInfo, loopInfo.jumpsFromLoopBody)
            
            jumpsFromLoopBody = loopInfo.jumpsFromLoopBody
            assert len(jumpsFromLoopBody) == 1, jumpsFromLoopBody
            j: LoopExitJumpInfo= jumpsFromLoopBody[0]
            
            if len(frame.loopStack) > 1:
                parentLoop: PyBytecodeLoopInfo = frame.loopStack[-2]
                if parentLoop.isJumpFromLoopBody(j.dstBlockOffset):
                    parentLoop.jumpsFromLoopBody.append(j)
                    break
            
            headerBlockLabel = blockTracker._getBlockLabel(loopInfo.loop.entryPoint[-1])
            self._onBlockGenerated(headerBlockLabel)
            
            loopInfo.markNewIteration()
            
            successorsToTranslate: List[LoopExitJumpInfo] = []
            srcBlockLabel = self.blockToLabel[j.srcBlock]
            dstBlockLabel = blockTracker._getBlockLabel(j.dstBlockOffset)
            
            # update CFG after we resolved reenter or loop exit
            blockTracker.cfg.add_edge(srcBlockLabel, dstBlockLabel)
            isLoopReenter = loopInfo.loop.entryPoint[-1] == j.dstBlockOffset
            if isLoopReenter:
                # a case where next block is current block which is a loop header
                assert frame.loopStack[-1].loop is loopInfo.loop
                newPrefix = tuple(blockTracker._getBlockLabelPrefix(j.dstBlockOffset))
                #print("cfgCopyLoopBlocks", loopInfo.loop, newPrefix)
                for bl in blockTracker.cfgCopyLoopBlocks(loopInfo.loop, newPrefix):
                    bl: BlockLabel
                    self._onBlockGenerated(bl)

            self._debugDump()
            
            sucInfo = self._translateJumpFromCurrentLoop(frame, False,
                   j.srcBlock, j.cond, j.dstBlockOffset, False, j.branchPlaceholder,
                   allowJumpToNextLoopIteration=True)

            assert frame.loopStack[-1] is loopInfo, (loopInfo, frame.loopStack)
            if sucInfo is not None and sucInfo.dstBlockIsNew:
                successorsToTranslate.append(sucInfo)

            if srcBlockLabel != headerBlockLabel:
                # because we we can not jump to a block from anywhere but loop header (because of structural programming)
                self._onBlockGenerated(srcBlockLabel)
            
            for sucInfo in successorsToTranslate:
                sucInfo: LoopExitJumpInfo
                assert sucInfo.branchPlaceholder is None, sucInfo
                self._translateBlockBody(sucInfo.isExplicitLoopReenter, sucInfo.dstBlockLoops, sucInfo.dstBlockOffset, sucInfo.dstBlock, frame)
                assert frame.loopStack[-1] is loopInfo, (loopInfo, frame.loopStack)
            

        frame.exitLoop()

    def _finalizeJumpsFromHwLoopBody(self, headerBlock: SsaBasicBlock, headerOffset: int, loopInfo: PyBytecodeLoopInfo, frame: PyBytecodeFrame):
        blockTracker = self.blockTracker
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
            blockTracker.cfg.add_edge(srcBlockLabel, headerLabel if isJumpToHeader else blockTracker._getBlockLabel(j.dstBlockOffset))
            if j.dstBlockOffset == headerOffset:
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
                # fill back the original backedge in the loop CFG
                self._addNotGeneratedBlock(srcBlockLabel, nextIterationLoopHeaderLabel)
            else:
                sucInfo = self._translateJumpFromCurrentLoop(frame, False,
                       j.srcBlock, j.cond, j.dstBlockOffset, False, j.branchPlaceholder)
                if sucInfo is not None and sucInfo.dstBlockIsNew:
                    successorsToTranslate.append(sucInfo)

            if isLastJumpFromBlock and j.srcBlock is not headerBlock:
                # if this is header we mark it after we finish the loop
                self._onBlockGenerated(srcBlockLabel)

        # [todo] do not mark if this header is shared with parent loop
        self._onBlockGenerated(headerLabel)
        frame.exitLoop()
        for sucInfo in successorsToTranslate:
            sucInfo: LoopExitJumpInfo
            assert sucInfo.branchPlaceholder is None, sucInfo
            self._translateBlockBody(sucInfo.isExplicitLoopReenter, sucInfo.dstBlockLoops, sucInfo.dstBlockOffset, sucInfo.dstBlock, frame)
        
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
                parentLoop.markJumpFromBodyOfLoop(srcBlock, cond, dstBlockOffset, branchPlaceholder)
                return None

        if not allowJumpToNextLoopIteration:
            li = frame.loopStack.pop()
        if translateImmediately:
            self._getOrCreateSsaBasicBlockAndJumpRecursively(
                srcBlock, isLastJumpFromSrc, dstBlockOffset, cond, frame, branchPlaceholder,
                allowJumpToNextLoopIteration=allowJumpToNextLoopIteration)
            res = None

        else:
            res = self._prepareSsaBlockBeforeTranslation(
                srcBlock, isLastJumpFromSrc, dstBlockOffset, cond, frame, branchPlaceholder,
                allowJumpToNextLoopIteration=allowJumpToNextLoopIteration)

        if not allowJumpToNextLoopIteration:
            frame.loopStack.append(li)
        return res

    def _translateBytecodeBlock(self,
            instructions: List[Instruction],
            frame: PyBytecodeFrame,
            curBlock: SsaBasicBlock):
        """
        Evaluate instruction list and translate to SSA all which is using HW types and which can not be evaluated compile time.
        """
        if instructions[0].opcode == FOR_ITER:
            assert len(instructions) == 1, ("It is expected that FOR_ITER opcode is alone in the block", instructions)
            forIter: Instruction = instructions[0]
            # preproc eval for loop
            a = frame.stack[-1]
            bodyBlockOffset = forIter.offset + 2
            try:
                v = next(a)
                frame.stack.append(PyBytecodeInPreproc(v))
            except StopIteration:
                branchPlaceholder = BranchTargetPlaceholder.create(curBlock)
                lei = LoopExitJumpInfo(None, curBlock, None, None, forIter.argval, None, None, branchPlaceholder)
                frame.markJumpFromBodyOfCurrentLoop(lei)
                curBlockLabel = self.blockToLabel[curBlock]
                bodyBlockLabel = self.blockTracker._getBlockLabel(bodyBlockOffset)
                self._addNotGeneratedBlock(curBlockLabel, bodyBlockLabel)
                frame.stack.pop()
                return

            # jump into loop body
            self._getOrCreateSsaBasicBlockAndJumpRecursively(curBlock, True, bodyBlockOffset, None, frame, None)

        else:
            for last, instr in iter_with_last(instructions):
                if last and instr.opcode in JUMP_OPS:
                    self._translateInstructionJumpHw(instr, frame, curBlock)
                elif instr.opcode == RETURN_VALUE:
                    assert last, instr
                    self._onBlockGenerated(self.blockToLabel[curBlock])
                else:
                    curBlock = self._translateBytecodeBlockInstruction(instr, frame, curBlock)
                    if last:
                        # jump to next block, there was no explicit jump because this is regular code flow, but the next instruction
                        # is jump target
                        self._getOrCreateSsaBasicBlockAndJumpRecursively(curBlock, True, instr.offset + 2, None, frame, None)

    def _translateInstructionJumpHw(self, instr: Instruction,
                                    frame: PyBytecodeFrame,
                                    curBlock: SsaBasicBlock):
        try:
            assert curBlock
            opcode = instr.opcode

            if opcode == RETURN_VALUE:
                self._onBlockGenerated(self.blockToLabel[curBlock])
                return None

            elif opcode == JUMP_ABSOLUTE or opcode == JUMP_FORWARD:
                self._getOrCreateSsaBasicBlockAndJumpRecursively(curBlock, True, instr.argval, None, frame, None)

            elif opcode in (
                    JUMP_IF_FALSE_OR_POP,
                    JUMP_IF_TRUE_OR_POP,
                    POP_JUMP_IF_FALSE,
                    POP_JUMP_IF_TRUE):
                if opcode in (JUMP_IF_FALSE_OR_POP,
                              JUMP_IF_TRUE_OR_POP):
                    raise NotImplementedError("stack pop depends on hw evaluated condition")

                cond = frame.stack.pop()
                cond, curBlock = expandBeforeUse(cond, curBlock)
                compileTimeResolved = not isinstance(cond, (RtlSignal, HValue, SsaValue))
                if not compileTimeResolved:
                    curBlock, cond = self.to_ssa.visit_expr(curBlock, cond)

                ifFalseOffset = instr.offset + 2
                ifTrueOffset = instr.argval
                if opcode in (JUMP_IF_FALSE_OR_POP, POP_JUMP_IF_FALSE):
                    # swap targets because condition is reversed
                    ifTrueOffset, ifFalseOffset = ifFalseOffset, ifTrueOffset

                if compileTimeResolved:
                    if cond:
                        self._getOrCreateSsaBasicBlockAndJumpRecursively(curBlock, True, ifTrueOffset, None, frame, None)
                        self._onBlockNotGenerated(curBlock, ifFalseOffset)
                    else:
                        self._getOrCreateSsaBasicBlockAndJumpRecursively(curBlock, True, ifFalseOffset, None, frame, None)
                        self._onBlockNotGenerated(curBlock, ifTrueOffset)
                else:
                    if isinstance(cond, HValue):
                        if cond:
                            self._getOrCreateSsaBasicBlockAndJumpRecursively(curBlock, True, ifTrueOffset, cond, frame, None)
                            self._onBlockNotGenerated(curBlock, ifFalseOffset)
                     
                        else:
                            self._getOrCreateSsaBasicBlockAndJumpRecursively(curBlock, True, ifFalseOffset, ~cond, frame, None)
                            self._onBlockNotGenerated(curBlock, ifTrueOffset)

                    else:
                        secondBranchFrame = copy(frame)
                        self._getOrCreateSsaBasicBlockAndJumpRecursively(curBlock, False, ifTrueOffset, cond, frame, None)
                        # cond = 1 because we did check in ifTrue branch and this is "else branch"
                        self._getOrCreateSsaBasicBlockAndJumpRecursively(curBlock, True, ifFalseOffset, BIT.from_py(1), secondBranchFrame, None)
            else:
                raise NotImplementedError(instr)

        except HlsSyntaxError:
            raise  # do not decorate already decorated exceptions

        except Exception:
            # create decorated exception
            raise self._createInstructionException(instr)

