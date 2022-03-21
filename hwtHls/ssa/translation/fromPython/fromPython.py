import builtins
from collections import deque
from dis import findlinestarts, _get_instructions_bytes, Instruction, dis
import inspect
from types import FunctionType
from typing import Dict, Optional, List, Tuple, Union, Deque

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.value import HValue
from hwt.pyUtils.arrayQuery import flatten
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.errors import HlsSyntaxError
from hwtHls.hlsStreamProc.statements import HlsStreamProcWrite, \
    HlsStreamProcRead
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.translation.fromPython.blockLabel import generateBlockLabel
from hwtHls.ssa.translation.fromPython.blockPredecessorTracker import BlockLabel, \
    BlockPredecessorTracker
from hwtHls.ssa.translation.fromPython.bytecodeBlockAnalysis import extractBytecodeBlocks
from hwtHls.ssa.translation.fromPython.instructions import CMP_OPS, BIN_OPS, UN_OPS, INPLACE_OPS, JUMP_OPS
from hwtHls.ssa.translation.fromPython.loopsDetect import PyBytecodeLoop, \
    PreprocLoopScope
from hwtHls.ssa.value import SsaValue


class PythonBytecodeToSsa():
    """
    This class translates Python bytecode to hwtHls.ssa
    
    The SSA basic blocks are constructed from jump targets in instruction list.
    A single jump target may generate multiple basic blocks if it is part of the cycle.

    :note: The block is generated for every jump target, even if it is just in preprocessor.
        If it is used just in preprocessor the jumps conditions of this block are resolved compile time.
        (Because for cycles we may find out that the cycle is hw evaluated somewhere inside of cycle body)
        And thus the blocks which were generated in preprocessor are entry points of clusters of blocks generated for HW
        connected in linear sequence or are entirely disconnected because preprocessor optimized them out. 
    """

    def __init__(self, hls: HlsStreamProc, fn: FunctionType):
        self.hls = hls
        self.to_ssa: Optional[AstToSsa] = None
        # self.blockPredecesorOffsetUnseen: Dict[int, int] = {}
        self.blockToLabel: Dict[SsaBasicBlock, BlockLabel] = {}
        self.offsetToBlock: Dict[BlockLabel, SsaBasicBlock] = {}
        self.instructions: Tuple[Instruction] = ()
        self.bytecodeBlocks: Dict[int, List[Instruction]] = {}
        self.fn = fn

    def _initInterpretVars(self, fn: FunctionType, fnArgs: tuple, fnKwargs:dict):
        co = fn.__code__
        localVars = [None for _ in range(fn.__code__.co_nlocals)]
        if inspect.ismethod(fn):
            fnArgs = tuple((fn.__self__, *fnArgs))
        assert len(fnArgs) == co.co_argcount, ("Must have the correct number of arguments", len(fnArgs), co.co_argcount)
        for i, v in enumerate(fnArgs):
            localVars[i] = v
        if fnKwargs:
            raise NotImplementedError()

        return localVars

    # https://www.synopsys.com/blogs/software-security/understanding-python-bytecode/

    def translateFunction(self, *fnArgs, **fnKwargs):
        """
        The input function may have features which should be evaluated during compile time and the rest should be translate to SSA for hardware compilation.
        We can not simply run preprocessor on a function because we know that instruction should be evaluated compile time only after we resolve its arguments.
        However in order to resolve all arguments we have to translate whole code.
        Because of this we must run preprocessor while translating the code and because of thit a single basic block from python can generate multiple basic blocks in SSA.
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
        # print(self.loops)
        self.blockTracker = BlockPredecessorTracker(cfg)
        # print(cfg._adj)
        # print(self.loops)

        self.to_ssa = AstToSsa(self.hls.ssaCtx, fn.__name__, None)
        # self.to_ssa._onAllPredecsKnown(self.to_ssa.start)
        curBlock = self.to_ssa.start
        self.blockToLabel[curBlock] = (0,)
        self.offsetToBlock[(0,)] = curBlock
        for _ in self.blockTracker.addGenerated((0,)):
            pass

        localVars = self._initInterpretVars(fn, fnArgs, fnKwargs)
        stack = []
        self._translateBytecodeBlock(self.bytecodeBlocks[0], stack, localVars, curBlock)
        self.to_ssa.finalize()
        if curBlock.predecessors:
            # because for LLVM entry point must not have predecessors
            entry = SsaBasicBlock(self.to_ssa.ssaCtx, "entry")
            entry.successors.addTarget(None, curBlock)
            self.to_ssa.start = entry

        return self.to_ssa, None

    def _translateBytecodeBlockInstruction(self, instr: Instruction, last: bool,
                                           stack: list,
                                           localVars:list,
                                           curBlock: SsaBasicBlock):
        if last and instr.opname in JUMP_OPS:
            self._translateInstructionJumpHw(instr, stack, localVars, curBlock)

        elif instr.opname == "RETURN_VALUE":
            assert last, instr
            return

        else:
            self._translateInstruction(instr, stack, localVars, curBlock)
            if last:
                # jump to next block, there was no explicit jump because this is regular code flow, but the next instruction
                # is jump target
                self._getOrCreateSsaBasicBlockAndJump(curBlock, instr.offset + 2, None, stack, localVars)

    def _addBlockSuccessor(self, block: SsaBasicBlock, cond: Union[RtlSignal, None, SsaValue], blockSuccessor: SsaBasicBlock):
        block.successors.addTarget(cond, blockSuccessor)

    def _blockToSsa(self, curBlock: SsaBasicBlock, curBlockCode: Union[SsaValue, List[SsaValue]]):
        self.to_ssa.visit_CodeBlock_list(curBlock, flatten(curBlockCode))

    def _jumpToNextBlock(self, instr: Instruction, curBlock: SsaBasicBlock, blocks:Dict[BlockLabel, SsaBasicBlock]):
        nextBlock = blocks[self.blockTracker._getBlockLabel(instr.offset)]
        if curBlock is not nextBlock:
            prevBlock = curBlock
            curBlock = nextBlock
            if not prevBlock.successors.targets or prevBlock.successors.targets[-1][0] is not None:
                prevBlock.successors.addTarget(None, curBlock)
        return curBlock

    def _getOrCreateSsaBasicBlock(self, dstLabel: BlockLabel):
        block = self.offsetToBlock.get(dstLabel, None)
        if block is None:
            block = self.offsetToBlock[dstLabel] = SsaBasicBlock(self.to_ssa.ssaCtx, f"block{'_'.join(str(o) for o in dstLabel)}")
            self.blockToLabel[block] = dstLabel
            return block, True

        return block, False

    def _getOrCreateSsaBasicBlockAndJump(self,
                                         curBlock: SsaBasicBlock,
                                         sucBlockOffset: int,
                                         cond: Union[None, RtlSignal, SsaValue],
                                         stack: list,
                                         localVars: list):
        # print("jmp", curBlock.label, sucBlockOffset, cond)
        prevLoopMeta: Deque[PreprocLoopScope] = deque()
        # if this is a jump out of current loop
        preprocLoopScope = self.blockTracker.preprocLoopScope
        loopMeta = None
        if isinstance(cond, HValue):
            assert cond, (cond, "If this was not True the jump should not be evaluated at the first place")
            cond = None  # always jump
        elif isinstance(cond, (RtlSignal, SsaValue)):
            # regular hw evalueated jump
            pass
        else:
            # preproc evaluated jump
            assert cond is None, cond
            curBlockOffset = self.blockToLabel[curBlock][-1]
            loop = self.loops.get(curBlockOffset, None)
            # if jumping from body of the current loop and this loop does not have a preproc scope it means
            # that it is completely HW evaluated and we should not touch preproc scopes
            if loop is not None and (curBlockOffset,) in loop.allBlocks:
                isPreprocLoop = False
                for ls in preprocLoopScope:
                    ls: PreprocLoopScope
                    if ls.loop is loop:
                        isPreprocLoop = True
                        break
            else:
                isPreprocLoop = True

            if isPreprocLoop:
                while preprocLoopScope:
                    curLoop: PyBytecodeLoop = preprocLoopScope[-1].loop
                    if (sucBlockOffset,) in curLoop.allBlocks:
                        break  # in current loop
                    else:
                        prevLoopMeta.appendleft(preprocLoopScope.pop())

                if loop is not None:
                    # if this is a jump to a header of new loop
                    if not preprocLoopScope or preprocLoopScope[-1].loop is not loop:
                        loopMeta = PreprocLoopScope(loop, 0)
                    else:
                        # if this is a current loop, just increment index
                        prevLoopMeta.appendleft(preprocLoopScope.pop())
                        loopMeta = PreprocLoopScope(loop, prevLoopMeta[0].iterationIndex + 1)
        
                    preprocLoopScope.append(loopMeta)
        
                    # prepare blocks next loop body in cfg
                    if loopMeta.iterationIndex == 0:
                        for bl in self.blockTracker.cfgAddPrefixToLoopBody(loopMeta.loop, preprocLoopScope, True):
                            self.to_ssa._onAllPredecsKnown(self.offsetToBlock[bl])
                        # update cycle entry point
                        oldLabel = self.blockToLabel[curBlock]
                        newLabel = generateBlockLabel(preprocLoopScope, oldLabel[-1])
                        self.blockToLabel[curBlock] = newLabel
                        self.offsetToBlock[newLabel] = curBlock
        
                    else:
                        # [todo] if this is a jump to a next iteration of preproc loop
                        for bl in self.blockTracker.cfgCopyLoopBody(loopMeta.loop, preprocLoopScope, True):
                            self.to_ssa._onAllPredecsKnown(self.offsetToBlock[bl])
        
            # if this is a jump to a header of some currently evaluated loop

        # if this is a jump just in linear code or inside body of the loop
        target = self.blockTracker._getBlockLabel(sucBlockOffset)
        sucBlock, sucBlockIsNew = self._getOrCreateSsaBasicBlock(target)
        self._addBlockSuccessor(curBlock, cond, sucBlock)
        if sucBlockIsNew:
            for bl in self.blockTracker.addGenerated(self.blockToLabel[sucBlock]):
                self.to_ssa._onAllPredecsKnown(self.offsetToBlock[bl])

            self._translateBytecodeBlock(self.bytecodeBlocks[sucBlockOffset], stack, localVars, sucBlock)

            if loopMeta is not None:
                assert preprocLoopScope[-1] is loopMeta, (preprocLoopScope[-1], loopMeta)
                preprocLoopScope.pop()

            if prevLoopMeta:
                # will be removed by parent call
                preprocLoopScope.extend(prevLoopMeta)

    def _translateBytecodeBlock(self, instructions: List[Instruction],
                                stack: list,
                                localVars:list,
                                curBlock: SsaBasicBlock):
        """
        Evaluate instruction list and translate to SSA all which is using HW types and which can not be evaluated compile time.
        """
        # print(instructions[0].offset)
        if instructions[0].opname == "FOR_ITER":
            assert len(instructions) == 1, ("It is expected that FOR_ITER opcode is alone in the block", instructions)
            forIter: Instruction = instructions[0]
            # preproc eval for loop
            a = stack[-1]
            try:
                v = next(a)
                stack.append(v)
            except StopIteration:
                # jump behind the loop
                stack.pop()
                self._getOrCreateSsaBasicBlockAndJump(curBlock, forIter.argval, None, stack, localVars)
                return
            # jump into loop body
            self._getOrCreateSsaBasicBlockAndJump(curBlock, forIter.offset + 2, None, stack, localVars)
        else:
            for last, instr in iter_with_last(instructions):
                self._translateBytecodeBlockInstruction(instr, last, stack, localVars, curBlock)

    def _onBlockNotGenerated(self, curBlock: SsaBasicBlock, blockOffset: int):
        for loopScope in reversed(self.blockTracker.preprocLoopScope):
            loopScope: PreprocLoopScope
            if loopScope.loop.entryPoint[-1] == blockOffset:
                # is backedge in preproc loop, edge of this type was not generated in the first place
                return
        
        srcBlockLabel = self.blockToLabel[curBlock]
        dstBlockLabel = self.blockTracker._getBlockLabel(blockOffset)
        for bl in self.blockTracker.addNotGenerated(srcBlockLabel, dstBlockLabel):
            self.to_ssa._onAllPredecsKnown(self.offsetToBlock[bl])

    def _translateInstructionJumpHw(self, instr: Instruction,
                                    stack: list,
                                    localVars: list,
                                    curBlock: SsaBasicBlock):
        try:
            assert curBlock
            opname = instr.opname
            if opname == 'RETURN_VALUE':
                return None

            elif opname == 'JUMP_ABSOLUTE' or opname == 'JUMP_FORWARD':
                self._getOrCreateSsaBasicBlockAndJump(curBlock, instr.argval, None, stack, localVars)

            elif opname in (
                    'JUMP_IF_FALSE_OR_POP',
                    'JUMP_IF_TRUE_OR_POP',
                    'POP_JUMP_IF_FALSE',
                    'POP_JUMP_IF_TRUE'):
                if opname in ('JUMP_IF_FALSE_OR_POP', 'JUMP_IF_TRUE_OR_POP'):
                    raise NotImplementedError("stack pop may depend on hw evaluated condition")

                cond = stack.pop()
                compileTimeResolved = not isinstance(cond, (RtlSignal, HValue, SsaValue))
                if not compileTimeResolved:
                    curBlock, cond = self.to_ssa.visit_expr(curBlock, cond)

                ifFalseOffset = instr.offset + 2
                ifTrueOffset = instr.argval
                if opname in ('JUMP_IF_FALSE_OR_POP', 'POP_JUMP_IF_FALSE'):
                    # swap targets because condition is reversed
                    ifTrueOffset, ifFalseOffset = ifFalseOffset, ifTrueOffset

                if compileTimeResolved:
                    if cond:
                        self._onBlockNotGenerated(curBlock, ifFalseOffset)
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, ifTrueOffset, None, stack, localVars)
                    else:
                        self._onBlockNotGenerated(curBlock, ifTrueOffset)
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, ifFalseOffset, None, stack, localVars)

                else:
                    if isinstance(cond, HValue):
                        if cond:
                            self._getOrCreateSsaBasicBlockAndJump(curBlock, ifTrueOffset, cond, stack, localVars)
                        else:
                            self._getOrCreateSsaBasicBlockAndJump(curBlock, ifFalseOffset, ~cond, stack, localVars)
                            
                    else:
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, ifTrueOffset, cond, stack, localVars)
                        # cond = None because we did check in ifTrue branch and this is "else branch"
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, ifFalseOffset, None, stack, localVars)

            else:
                raise NotImplementedError(instr)

        except HlsSyntaxError:
            raise

        except Exception:
            raise self._createInstructionException(instr)

    def _translateInstruction(self,
                              instr: Instruction,
                              stack: list,
                              localVars:list,
                              curBlock: SsaBasicBlock):
        try:
            opname = instr.opname
            # https://docs.python.org/3/library/dis.html
            if opname == 'LOAD_DEREF':
                v = self.fn.__closure__[instr.arg].cell_contents
                stack.append(v)

            elif opname == 'LOAD_ATTR':
                v = stack[-1]
                v = getattr(v, instr.argval)
                stack[-1] = v

            elif opname == 'STORE_ATTR':
                dst = stack.pop()
                dst = getattr(dst, instr.argval)
                src = stack.pop()

                if isinstance(dst, (Interface, RtlSignal)):
                    stm = self.hls.write(src, dst)
                    self._blockToSsa(curBlock, stm)
                else:
                    raise NotImplementedError(instr)

            elif opname == 'STORE_FAST':
                vVal = stack.pop()
                v = localVars[instr.arg]
                if v is None:
                    if isinstance(vVal, (HValue, RtlSignal, SsaValue)):
                        # only if it is a value which generates hw variable
                        v = self.hls.var(instr.argval, vVal._dtype)
                    localVars[instr.arg] = v

                if isinstance(v, RtlSignal):
                    # only if it is a hw variable
                    stm = v(vVal)
                    self._blockToSsa(curBlock, stm)
                else:
                    localVars[instr.arg] = vVal

            elif opname == 'LOAD_FAST':
                v = localVars[instr.arg]
                assert v is not None, (instr.argval, "used before defined")
                stack.append(v)

            elif opname == 'LOAD_CONST':
                stack.append(instr.argval)

            elif opname == 'LOAD_GLOBAL':
                if instr.argval in self.fn.__globals__:
                    v = self.fn.__globals__[instr.argval]
                else:
                    assert instr.argval in builtins.__dict__, instr.argval
                    v = builtins.__dict__[instr.argval]
                stack.append(v)

            elif opname == 'LOAD_METHOD':
                v = stack.pop()
                v = getattr(v, instr.argval)
                stack.append(v)

            elif opname == 'CALL_METHOD' or opname == "CALL_FUNCTION":
                args = []
                for _ in range(instr.arg):
                    args.append(stack.pop())
                m = stack.pop()
                res = m(*reversed(args))
                stack.append(res)

            elif opname == 'CALL_FUNCTION_KW':
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

            elif opname == "POP_TOP":
                res = stack.pop()
                if isinstance(res, (HlsStreamProcWrite, HlsStreamProcRead)):
                    self._blockToSsa(curBlock, res)

            elif opname == 'COMPARE_OP':
                binOp = CMP_OPS[instr.argval]
                b = stack.pop()
                a = stack.pop()
                stack.append(binOp(a, b))

            elif opname == "BUILD_SLICE":
                b = stack.pop()
                a = stack.pop()
                stack.append(slice(a, b))

            elif opname == "GET_ITER":
                a = stack.pop()
                stack.append(iter(a))
            elif opname == "EXTENDED_ARG":
                pass   
            else:
                binOp = BIN_OPS.get(opname, None)
                if binOp is not None:
                    b = stack.pop()
                    a = stack.pop()
                    stack.append(binOp(a, b))
                    return

                unOp = UN_OPS.get(opname, None)
                if unOp is not None:
                    a = stack.pop()
                    stack.append(unOp(a))
                    return

                inplaceOp = INPLACE_OPS.get(opname, None)
                if inplaceOp is not None:
                    b = stack.pop()
                    a = stack.pop()
                    stack.append(inplaceOp(a, b))
                else:
                    raise NotImplementedError(instr)
        except HlsSyntaxError:
            raise
        except Exception:
            raise self._createInstructionException(instr)

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


def pyFunctionToSsa(hls: HlsStreamProc, fn: FunctionType, *fnArgs, **fnKwargs):
    c = PythonBytecodeToSsa(hls, fn)
    return c.translateFunction(*fnArgs, **fnKwargs)
