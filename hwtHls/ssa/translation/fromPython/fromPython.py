import builtins
from collections import deque
from dis import findlinestarts, _get_instructions_bytes, Instruction, dis
import operator
import sys
from types import FunctionType, CellType
from typing import Dict, Optional, List, Tuple, Union, Deque

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.types.defs import BIT
from hwt.hdl.value import HValue
from hwt.pyUtils.arrayQuery import flatten
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.errors import HlsSyntaxError
from hwtHls.hlsStreamProc.statementsIo import HlsStreamProcWrite, \
    HlsStreamProcRead
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.translation.fromPython.blockLabel import generateBlockLabel
from hwtHls.ssa.translation.fromPython.blockPredecessorTracker import BlockLabel, \
    BlockPredecessorTracker
from hwtHls.ssa.translation.fromPython.bytecodeBlockAnalysis import extractBytecodeBlocks
from hwtHls.ssa.translation.fromPython.frame import PythonBytecodeFrame
from hwtHls.ssa.translation.fromPython.indexExpansion import PyObjectHwSubscriptRef
from hwtHls.ssa.translation.fromPython.instructions import CMP_OPS, BIN_OPS, UN_OPS, \
    INPLACE_BIN_OPS, JUMP_OPS, ROT_OPS, BUILD_OPS, FOR_ITER, RETURN_VALUE, NOP, \
    POP_TOP, LOAD_DEREF, LOAD_ATTR, LOAD_FAST, LOAD_CONST, LOAD_GLOBAL, \
    LOAD_METHOD, LOAD_CLOSURE, STORE_ATTR, STORE_FAST, STORE_DEREF, CALL_METHOD, \
    CALL_FUNCTION, CALL_FUNCTION_KW, COMPARE_OP, GET_ITER, UNPACK_SEQUENCE, \
    MAKE_FUNCTION, STORE_SUBSCR, EXTENDED_ARG, JUMP_ABSOLUTE, JUMP_FORWARD, \
    JUMP_IF_FALSE_OR_POP, JUMP_IF_TRUE_OR_POP, POP_JUMP_IF_FALSE, \
    POP_JUMP_IF_TRUE, CALL_FUNCTION_EX
from hwtHls.ssa.translation.fromPython.loopsDetect import PyBytecodeLoop, \
    PreprocLoopScope
from hwtHls.ssa.translation.fromPython.markers import PythonBytecodeInPreproc
from hwtHls.ssa.value import SsaValue


class SsaBlockGroup():

    def __init__(self, begin: SsaBasicBlock):
        self.begin = begin
        self.end = begin


def expandBeforeUse(o, curBlock: SsaBasicBlock):
    if isinstance(o, PyObjectHwSubscriptRef):
        o: PyObjectHwSubscriptRef
        return o.expandOnUse(curBlock)
    
    return o, curBlock


class PythonBytecodeToSsa():
    """
    This class translates Python bytecode to hwtHls.ssa
    
    The SSA basic blocks are constructed from jump targets in instruction list.
    A single jump target may generate multiple basic blocks if it is part of the cycle.
    
    Description of Python bytecode:
        * https://docs.python.org/3/library/dis.html
        * https://towardsdatascience.com/understanding-python-bytecode-e7edaae8734d

    Custom Python interprets:
        * https://github.com/pypyjs/pypy
        * https://github.com/kentdlee/CoCo

    :note: The block is generated for every jump target, even if it is just in preprocessor.
        If it is used just in preprocessor the jumps conditions of this block are resolved compile time.
        (Because for cycles we may find out that the cycle is HW evaluated somewhere inside of cycle body)
        And thus the blocks which were generated in preprocessor are entry points of clusters of blocks generated for HW
        connected in linear sequence or are entirely disconnected because preprocessor optimized them out. 
    """

    def __init__(self, hls: HlsStreamProc, fn: FunctionType):
        assert sys.version_info >= (3, 10, 0), ("Python3.10 is minimum requirement", sys.version_info)
        self.hls = hls
        self.fn = fn
        self.to_ssa: Optional[AstToSsa] = None
        self.blockToLabel: Dict[SsaBasicBlock, BlockLabel] = {}
        self.labelToBlock: Dict[BlockLabel, SsaBlockGroup] = {}
        self.instructions: Tuple[Instruction] = ()
        self.bytecodeBlocks: Dict[int, List[Instruction]] = {}

    # https://www.synopsys.com/blogs/software-security/understanding-python-bytecode/
    def translateFunction(self, *fnArgs, **fnKwargs):
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
        fn = self.fn
        # dis(fn)
        co = fn.__code__
        cell_names = co.co_cellvars + co.co_freevars
        linestarts = dict(findlinestarts(co))

        self.instructions = tuple(_get_instructions_bytes(
            co.co_code, co.co_varnames, co.co_names,
            co.co_consts, cell_names, linestarts))

        self.bytecodeBlocks, cfg = extractBytecodeBlocks(self.instructions)
        self.loops: Dict[int, PyBytecodeLoop] = {
            loop.entryPoint[0]: loop
            for loop in PyBytecodeLoop.detectLoops(cfg)
        }

        self.blockTracker = BlockPredecessorTracker(cfg)
        self.hwEvaluatedLoops: UniqList[BlockLabel] = UniqList()

        # print(self.loops)
        # print(cfg._adj)
        # print(self.loops)

        self.to_ssa = AstToSsa(self.hls.ssaCtx, fn.__name__, None)
        curBlock = self.to_ssa.start
        self.blockToLabel[curBlock] = (0,)
        self.labelToBlock[(0,)] = SsaBlockGroup(curBlock)
        frame = PythonBytecodeFrame.fromFunction(fn, fnArgs, fnKwargs)
        with open("tmp/cfg_begin.dot", "w") as f:
            self.blockTracker.dumpCfgToDot(f)

        self._translateBytecodeBlock(self.bytecodeBlocks[0], frame, curBlock)
        if curBlock.predecessors:
            # because for LLVM entry point must not have predecessors
            self.to_ssa.start.label += "_0"
            entry = SsaBasicBlock(self.to_ssa.ssaCtx, fn.__name__)
            self.to_ssa._onAllPredecsKnown(entry)
            entry.successors.addTarget(None, curBlock)
            self.to_ssa.start = entry

        # with open("tmp/cfg_final.dot", "w") as f:
        #     self.blockTracker.dumpCfgToDot(f)

        self.to_ssa.finalize()

    def _getOrCreateSsaBasicBlock(self, dstLabel: BlockLabel):
        block = self.labelToBlock.get(dstLabel, None)
        if block is None:
            block = SsaBasicBlock(
                self.to_ssa.ssaCtx, f"block{'_'.join(str(o) for o in dstLabel)}")
            self.labelToBlock[dstLabel] = SsaBlockGroup(block)
            self.blockToLabel[block] = dstLabel
            return block, True

        return block.begin, False

    def _getOrCreateSsaBasicBlockAndJump(self,
            curBlock: SsaBasicBlock,
            isLastJumpFromCur: bool,
            sucBlockOffset: int,
            cond: Union[None, RtlSignal, SsaValue],
            frame: PythonBytecodeFrame):

        # print("jmp", curBlock.label, sucBlockOffset, cond)
        prevLoopMeta: Deque[PreprocLoopScope] = deque()
        # if this is a jump out of current loop
        preprocLoopScope = self.blockTracker.preprocLoopScope
        loopMeta = None
        loopMetaAdded = False
        blockWithAllPredecessorsNewlyKnown = None
        if isinstance(cond, HValue):
            assert cond, (cond, "If this was not True the jump should not be evaluated at the first place")
            cond = None  # always jump, but we need this value to know that this will be unconditional jump only in HW
            isHwEvaluatedCond = True

        elif isinstance(cond, (RtlSignal, SsaValue)):
            # regular hw evaluated jump
            isHwEvaluatedCond = True

        else:
            assert cond is None, cond
            isHwEvaluatedCond = False
        
        # potentially preproc evaluated jump
        # it is a preproc loop if we are jumping from loop header unconditionally (cond is None is this case)
        curBlockLabel = self.blockToLabel[curBlock]
        curBlockOffset = curBlockLabel[-1]
        loop = self.loops.get(curBlockOffset, None)
        sucLoop = self.loops.get(sucBlockOffset, None)
        reenteringLoopBody = any(s.loop is loop for s in preprocLoopScope)
        isJumpFromLoopHeaderToBody = (
            loop is not None and  # src is loop header
            (sucBlockOffset,) in loop.allBlocks  # dst is in loop body
        )
        isJumpFromPreprocLoopHeaderToBody = isJumpFromLoopHeaderToBody and not isHwEvaluatedCond
        isJumpFromPreprocLoopBodyToLoopHeader = (
            sucLoop is not None and
            any((sucBlockOffset,) == s.loop.entryPoint for s in preprocLoopScope)
        )
        # if jumping from body of the current loop and this loop does not have a preproc scope it means
        # that it is completely HW evaluated and we should not touch preproc scopes
        # :note: if loop is not None the curBlock is a header of that loop
        if isJumpFromLoopHeaderToBody and isHwEvaluatedCond:
            self.hwEvaluatedLoops.append(curBlockLabel)

        # if this is a jump to a header of some currently evaluated loop
        if isJumpFromPreprocLoopHeaderToBody or isJumpFromPreprocLoopBodyToLoopHeader:
            if isJumpFromPreprocLoopBodyToLoopHeader:
                # prepare scope for start of new iteration
                while preprocLoopScope:
                    curLoop: PyBytecodeLoop = preprocLoopScope[-1].loop
                    if (sucBlockOffset,) in curLoop.allBlocks:
                        break  # in current loop
                    else:
                        prevLoopMeta.appendleft(preprocLoopScope.pop())

            # if this is a jump to a header of new loop
            if isJumpFromPreprocLoopHeaderToBody and not reenteringLoopBody:
                # jump from first header to body
                loopMeta = PreprocLoopScope(loop, 0)
                preprocLoopScope.append(loopMeta)
                loopMetaAdded = True

            elif isJumpFromPreprocLoopBodyToLoopHeader:
                # isJumpFromPreprocLoopBodyToLoopHeader
                # this must be jump to a new body of already executed loop  
                prevLoopMeta.appendleft(preprocLoopScope.pop())
                loopMeta = PreprocLoopScope(loop if isJumpFromPreprocLoopHeaderToBody else sucLoop,
                                            prevLoopMeta[0].iterationIndex + 1)
                preprocLoopScope.append(loopMeta)
                loopMetaAdded = True
            else:
                loopMeta = preprocLoopScope[-1]

            if isJumpFromPreprocLoopHeaderToBody or reenteringLoopBody:
                if loopMeta.iterationIndex == 0:
                    assert not reenteringLoopBody
                    # update cycle entry point label for label prefix adding
                    oldLabel = self.blockToLabel[curBlock]
                    newLabel = generateBlockLabel(preprocLoopScope, oldLabel[-1])
                    self.blockToLabel[curBlock] = newLabel
                    self.labelToBlock[newLabel] = SsaBlockGroup(curBlock)
                    
                    # prepare blocks first loop body in cfg
                    blockWithAllPredecessorsNewlyKnown = list(
                        self.blockTracker.cfgAddPrefixToLoopBody(loopMeta.loop, preprocLoopScope))
                    
                else:
                    assert reenteringLoopBody
                    # this is a jump to a next iteration of preproc loop
                    blockWithAllPredecessorsNewlyKnown = list(
                        self.blockTracker.cfgCopyLoopBody(loopMeta.loop, preprocLoopScope))
                #with open(f"tmp/cfg_{preprocLoopScope}.dot", "w") as f:
                #    self.blockTracker.dumpCfgToDot(f)
        
        # if this is a jump just in linear code or inside body of the loop
        sucBlockLabel = self.blockTracker._getBlockLabel(sucBlockOffset)
        sucBlock, sucBlockIsNew = self._getOrCreateSsaBasicBlock(sucBlockLabel)
        curBlock.successors.addTarget(cond, sucBlock)

        if blockWithAllPredecessorsNewlyKnown is not None:
            for bl in blockWithAllPredecessorsNewlyKnown:
                if bl not in self.hwEvaluatedLoops:
                    # :attention: The header of hardware loop can be sealed only after all body blocks were generated
                    #             Otherwise some PHI arguments can be lost
                    self._onAllPredecsKnown(self.labelToBlock[bl].begin)

        if isLastJumpFromCur:
            self._onBlockGenerated(self.blockToLabel[curBlock])
        
        # if (not sucBlockIsNew and sucBlock not in self.to_ssa.m_ssa_u.sealedBlocks and
        #    self.blockTracker.hasAllPredecessorsKnown(sucBlockLabel)):
        #    # if just added predecessor sealed this already existing successor block
        #    self._onAllPredecsKnown(sucBlock)
        if sucBlockIsNew:
            self._translateBytecodeBlock(self.bytecodeBlocks[sucBlockOffset], frame, sucBlock)

        if (loop is not None and
            curBlockLabel in self.hwEvaluatedLoops and
            self.blockTracker.hasAllPredecessorsKnown(curBlockLabel)# and
            #curBlock not in self.to_ssa.m_ssa_u.sealedBlocks
            ):
            # if this was hw loop we have to close header after all body blocks were generated
            _curBlock = self.labelToBlock[curBlockLabel].begin
            self._onAllPredecsKnown(_curBlock)

        if loopMetaAdded:
            assert preprocLoopScope[-1] is loopMeta, (preprocLoopScope[-1], loopMeta)
            preprocLoopScope.pop()

        if prevLoopMeta:
            # will be removed by parent call
            preprocLoopScope.extend(prevLoopMeta)

    def _translateBytecodeBlock(self,
            instructions: List[Instruction],
            frame: PythonBytecodeFrame,
            curBlock: SsaBasicBlock):
        """
        Evaluate instruction list and translate to SSA all which is using HW types and which can not be evaluated compile time.
        """
        # print(instructions[0].offset)
        if instructions[0].opcode == FOR_ITER:
            assert len(instructions) == 1, ("It is expected that FOR_ITER opcode is alone in the block", instructions)
            forIter: Instruction = instructions[0]
            # preproc eval for loop
            a = frame.stack[-1]
            try:
                v = next(a)
                frame.stack.append(PythonBytecodeInPreproc(v))
            except StopIteration:
                # jump behind the loop
                frame.stack.pop()
                self._getOrCreateSsaBasicBlockAndJump(curBlock, True, forIter.argval, None, frame)
                return

            # jump into loop body
            self._getOrCreateSsaBasicBlockAndJump(curBlock, True, forIter.offset + 2, None, frame)

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
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, True, instr.offset + 2, None, frame)

    def _translateInstructionJumpHw(self, instr: Instruction,
                                    frame: PythonBytecodeFrame,
                                    curBlock: SsaBasicBlock):
        try:
            assert curBlock
            opcode = instr.opcode

            if opcode == RETURN_VALUE:
                self._onBlockGenerated(self.blockToLabel[curBlock])
                return None

            elif opcode == JUMP_ABSOLUTE or opcode == JUMP_FORWARD:
                self._getOrCreateSsaBasicBlockAndJump(curBlock, True, instr.argval, None, frame)

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
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, True, ifTrueOffset, None, frame)
                        self._onBlockNotGenerated(curBlock, ifFalseOffset)
                    else:
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, True, ifFalseOffset, None, frame)
                        self._onBlockNotGenerated(curBlock, ifTrueOffset)
                else:
                    if isinstance(cond, HValue):
                        if cond:
                            self._getOrCreateSsaBasicBlockAndJump(curBlock, True, ifTrueOffset, cond, frame)
                            self._onBlockNotGenerated(curBlock, ifFalseOffset)
                     
                        else:
                            self._getOrCreateSsaBasicBlockAndJump(curBlock, True, ifFalseOffset, ~cond, frame)
                            self._onBlockNotGenerated(curBlock, ifTrueOffset)

                    else:
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, False, ifTrueOffset, cond, frame)
                        # cond = 1 because we did check in ifTrue branch and this is "else branch"
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, True, ifFalseOffset, BIT.from_py(1), frame)
            else:
                raise NotImplementedError(instr)

        except HlsSyntaxError:
            raise  # do not decorate already decorated exceptions

        except Exception:
            # create decorated exception
            raise self._createInstructionException(instr)

    def _onBlockGenerated(self, label: BlockLabel):
        for bl in self.blockTracker.addGenerated(label):
            # we can seal the block only after body was generated
            if bl not in self.hwEvaluatedLoops:
                # :attention: The header of hardware loop can be sealed only after all body blocks were generated
                #             Otherwise some PHI arguments can be lost
                self._onAllPredecsKnown(self.labelToBlock[bl].begin)

    def _onBlockNotGenerated(self, curBlock: SsaBasicBlock, blockOffset: int):
        for loopScope in reversed(self.blockTracker.preprocLoopScope):
            loopScope: PreprocLoopScope
            if loopScope.loop.entryPoint[-1] == blockOffset:
                # is backedge in preproc loop, edge of this type was not generated in the first place
                return

        srcBlockLabel = self.blockToLabel[curBlock]
        dstBlockLabel = self.blockTracker._getBlockLabel(blockOffset)
        for bl in self.blockTracker.addNotGenerated(srcBlockLabel, dstBlockLabel):
            # sealing begin should be sufficient because all block behind begin in this
            # group should already have all predecessors known
            if bl not in self.hwEvaluatedLoops:
                # :attention: The header of hardware loop can be sealed only after all body blocks were generated
                #             Otherwise some PHI arguments can be lost
            
                self._onAllPredecsKnown(self.labelToBlock[bl].begin)

    def _onAllPredecsKnown(self, block: SsaBasicBlock):
        label = self.blockToLabel[block]
        # print("seal", block.label)
        loop = self.loops.get(label[-1], None)
        self.to_ssa._onAllPredecsKnown(block)
        if loop is not None:
            # if the value of PHI have branch in loop body where it is not modified it results in the case
            # where PHI would be its own argument, this is illegal and we fix it by adding block between loop body end and loop header
            # However we have to also transplant some other PHIs or create a new PHIs and move some args as we are modifying the predecessors
            predecCnt = len(block.predecessors)
            if any(len(phi.operands) != predecCnt for phi in block.phis):
                raise NotImplementedError(loop)
     
    def _makeFunction(self, instr: Instruction, stack: list):
        # MAKE_FUNCTION_FLAGS = ('defaults', 'kwdefaults', 'annotations', 'closure')
        name = stack.pop()
        assert isinstance(name, str), name
        code = stack.pop()

        if instr.arg & 1:
            # a tuple of default values for positional-only and positional-or-keyword parameters in positional order
            defaults = stack.pop()
        else:
            defaults = ()

        if instr.arg & (1 << 1):
            # a dictionary of keyword-only parameters’ default values
            raise NotImplementedError()

        if instr.arg & (1 << 2):
            # a tuple of strings containing parameters’ annotations
            # Changed in version 3.10: Flag value 0x04 is a tuple of strings instead of dictionary
            raise NotImplementedError()

        if instr.arg & (1 << 3):
            closure = stack.pop()
        else:
            closure = ()

        # PyCodeObject *code, PyObject *globals, 
        # PyObject *name, PyObject *defaults, PyObject *closure
        newFn = FunctionType(code, self.fn.__globals__, name, defaults, closure)
        stack.append(newFn)

    def _translateBytecodeBlockInstruction(self,
            instr: Instruction,
            frame: PythonBytecodeFrame,
            curBlock: SsaBasicBlock) -> SsaBasicBlock:

        stack = frame.stack
        locals_ = frame.locals
        try:
            # Python assigns each name in a scope to exactly one category:
            #  local, enclosing, or global/builtin.
            # CPython, implements that rule by using:
            #  FAST locals, DEREF closure cells, and NAME or GLOBAL lookups.
            
            opcode = instr.opcode
            if opcode == NOP:
                # Do nothing code. Used as a placeholder by the bytecode optimizer.
                return curBlock

            elif opcode == POP_TOP:
                # Removes the top-of-stack (TOS) item.
                res = stack.pop()
                res, curBlock = expandBeforeUse(res, curBlock)
                if isinstance(res, HlsStreamProcWrite):
                    res: HlsStreamProcWrite
                    if isinstance(res.dst, PyObjectHwSubscriptRef):
                        hls = self.hls
                        return res.dst.expandSetitemAsSwitchCase(curBlock,
                                                                 lambda i, dst: hls.write(res._orig_src, dst))
                    
                if isinstance(res, (HlsStreamProcWrite, HlsStreamProcRead, HdlAssignmentContainer)):
                    self.to_ssa.visit_CodeBlock_list(curBlock, [res, ])

            elif opcode == LOAD_DEREF:
                # nested scopes: access a variable through its cell object
                closure = self.fn.__closure__
                if closure is None:
                    # [todo] check what is the relation between function without closure
                    #  and child function closure
                    v = frame.locals[frame.cellVarI[instr.arg]]
                else:
                    v = closure[instr.arg].cell_contents
                # closure[instr.arg] = None
                stack.append(v)

            elif opcode == LOAD_ATTR:
                v = stack[-1]
                v = getattr(v, instr.argval)
                stack[-1] = v

            elif opcode == LOAD_FAST:
                v = locals_[instr.arg]
                assert v is not None, (instr.argval, "used before defined")
                stack.append(v)

            elif opcode == LOAD_CONST:
                stack.append(instr.argval)

            elif opcode == LOAD_GLOBAL:
                if instr.argval in self.fn.__globals__:
                    v = self.fn.__globals__[instr.argval]
                else:
                    assert instr.argval in builtins.__dict__, instr.argval
                    v = builtins.__dict__[instr.argval]
                stack.append(v)

            elif opcode == LOAD_METHOD:
                v = stack.pop()
                v = getattr(v, instr.argval)
                stack.append(v)

            elif opcode == LOAD_CLOSURE:
                # nested scopes: access the cell object
                v = locals_[frame.cellVarI[instr.arg]]
                stack.append(CellType(v))

            elif opcode == STORE_ATTR:
                dstParent = stack.pop()
                dst = getattr(dstParent, instr.argval)
                src = stack.pop()
                src, curBlock = expandBeforeUse(src, curBlock)

                if isinstance(dst, (Interface, RtlSignal)):
                    # stm = self.hls.write(src, dst)
                    self.to_ssa.visit_CodeBlock_list(curBlock, flatten(dst(src)))
                else:
                    raise NotImplementedError(instr, dst)

            elif opcode == STORE_FAST:
                vVal = stack.pop()
                vVal, curBlock = expandBeforeUse(vVal, curBlock)
                v = locals_[instr.arg]

                if instr.arg not in frame.preprocVars:
                    if v is None and isinstance(vVal, (HValue, RtlSignal, SsaValue)):
                        # only if it is a value which generates HW variable
                        t = getattr(vVal, "_dtypeOrig", vVal._dtype)
                        v = self.hls.var(instr.argval, t)
                        locals_[instr.arg] = v

                    if isinstance(v, (RtlSignal, Interface)):
                        # only if it is a hw variable, create assignment to HW variable
                        stm = v(vVal)
                        self.to_ssa.visit_CodeBlock_list(curBlock, flatten([stm, ]))
                        return curBlock

                if isinstance(vVal, PythonBytecodeInPreproc):
                    vVal = vVal.ref
                    frame.preprocVars.add(instr.arg)

                locals_[instr.arg] = vVal    

            elif opcode == STORE_DEREF:
                # nested scopes: access a variable through its cell object
                raise NotImplementedError(instr)

            elif opcode == CALL_METHOD or opcode == CALL_FUNCTION:
                args = []
                for _ in range(instr.arg):
                    args.append(stack.pop())
                m = stack.pop()
                res = m(*reversed(args))
                stack.append(res)

            elif opcode == CALL_FUNCTION_KW:
                args = []
                kwNames = stack.pop()
                assert isinstance(kwNames, tuple), kwNames
                for _ in range(instr.arg):
                    args.append(stack.pop())

                kwArgs = {}
                for kwName, a in zip(kwNames, args[:len(args) - len(kwNames)]):
                    kwArgs[kwName] = a
                del args[:len(kwNames)]

                m = stack.pop()
                res = m(*reversed(args), **kwArgs)
                stack.append(res)

            elif opcode == CALL_FUNCTION_EX:
                if instr.arg:
                    kw_args = stack.pop()
                    raise NotImplementedError(instr)

                args = stack.pop()
                m = stack.pop()
                res = m(*reversed(tuple(args)))
                stack.append(res)
                
            elif opcode == COMPARE_OP:
                binOp = CMP_OPS[instr.arg]
                b = stack.pop()
                a = stack.pop()
                a, curBlock = expandBeforeUse(a, curBlock)
                b, curBlock = expandBeforeUse(b, curBlock)
                stack.append(binOp(a, b))

            elif opcode == GET_ITER:
                a = stack.pop()
                a, curBlock = expandBeforeUse(a, curBlock)
                stack.append(iter(a))

            elif opcode == EXTENDED_ARG:
                pass

            elif opcode == UNPACK_SEQUENCE:
                seq = stack.pop()
                stack.extend(reversed(tuple(seq)))

            elif opcode == MAKE_FUNCTION:
                self._makeFunction(instr, stack)
                
            elif opcode == STORE_SUBSCR:
                operator.setitem
                index = stack.pop()
                index, curBlock = expandBeforeUse(index, curBlock)
                sequence = stack.pop()
                val = stack.pop()
                val, curBlock = expandBeforeUse(val, curBlock)
                if isinstance(index, (RtlSignal, SsaValue)) and not isinstance(sequence, (RtlSignal, SsaValue)):
                    if not isinstance(sequence, PyObjectHwSubscriptRef):
                        sequence = PyObjectHwSubscriptRef(self, sequence, index, instr.offset)
                    return sequence.expandSetitemAsSwitchCase(curBlock, lambda i, dst: dst(val))

                stack.append(operator.setitem(sequence, index, val))

            else:
                binOp = BIN_OPS.get(opcode, None)
                if binOp is not None:
                    b = stack.pop()
                    a = stack.pop()
                    a, curBlock = expandBeforeUse(a, curBlock)
                    b, curBlock = expandBeforeUse(b, curBlock)
                
                    if binOp is operator.getitem and isinstance(b, (RtlSignal, Interface, SsaValue)) and not isinstance(a, (RtlSignal, SsaValue)):
                        # if this is indexing using hw value on non hw object we need to expand it to a switch-case on individual cases
                        # must generate blocks for switch cases,
                        # for this we need a to keep track of start/end for each block because we do not have this newly generated blocks in original CFG
                        o = PyObjectHwSubscriptRef(self, a, b, instr.offset)
                        stack.append(o)
                        return curBlock

                    stack.append(binOp(a, b))
                    return curBlock

                unOp = UN_OPS.get(opcode, None)
                if unOp is not None:
                    a = stack.pop()
                    a, curBlock = expandBeforeUse(a, curBlock)
                    stack.append(unOp(a))
                    return curBlock

                rotOp = ROT_OPS.get(opcode, None)
                if rotOp is not None:
                    rotOp(stack)
                    return curBlock

                buildOp = BUILD_OPS.get(opcode, None)
                if buildOp is not None:
                    buildOp(instr, stack)
                    return curBlock
                
                inplaceOp = INPLACE_BIN_OPS.get(opcode, None)
                if inplaceOp is not None:
                    b = stack.pop()
                    b, curBlock = expandBeforeUse(b, curBlock)
                
                    a = stack.pop()
                    if isinstance(a, PyObjectHwSubscriptRef):
                        a: PyObjectHwSubscriptRef
                        # we expand as a regular bin op, and store later in store_subscript
                        a, curBlock = a.expandIndexOnPyObjAsSwitchCase(curBlock)
                        #.expandSetitemAsSwitchCase(curBlock, lambda _, dst: dst(inplaceOp(dst, b)))
                    res = inplaceOp(a, b)

                    stack.append(res)
                    
                    return curBlock
            
                raise NotImplementedError(instr)

        except HlsSyntaxError:
            raise

        except Exception:
            raise self._createInstructionException(instr)

        return curBlock

    def _createInstructionException(self, instr: Instruction):
        if instr.starts_line is not None:
            instrLine = instr.starts_line
        else:
            instrLine = -1
            for i in reversed(self.instructions[:self.instructions.index(instr)]):
                if i.starts_line is not None:
                    instrLine = i.starts_line
                    break

        fn = self.fn
        return HlsSyntaxError(f"  File \"%s\", line %d, in %s\n    %r" % (fn.__globals__['__file__'],
                                                                instrLine,
                                                                fn.__name__,
                                                                instr))

