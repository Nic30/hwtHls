import builtins
from collections import deque
from dis import findlinestarts, _get_instructions_bytes, Instruction, dis
import inspect
from types import FunctionType, CellType
from typing import Dict, Optional, List, Tuple, Union, Deque, Set

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.types.defs import BIT
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
from hwtHls.ssa.translation.fromPython.instructions import CMP_OPS, BIN_OPS, UN_OPS, \
    INPLACE_OPS, JUMP_OPS, ROT_OPS, BUILD_OPS
from hwtHls.ssa.translation.fromPython.loopsDetect import PyBytecodeLoop, \
    PreprocLoopScope
from hwtHls.ssa.value import SsaValue


class PythonBytecodeInPreproc():
    """
    A container of hw object marked that the immediate store is store of preproc variable only
    """

    def __init__(self, ref: Union[SsaValue, HValue, RtlSignal]):
        self.ref = ref
    
    def __iter__(self):
        for i in self.ref:
            yield PythonBytecodeInPreproc(i)


# assert sys.version_info >= (3, 10, 0), ("Python3.10 is minimum requirement", sys.version_info)
class PythonBytecodeFrame():

    def __init__(self, locals_: list, cellVarI: Dict[int, int], stack: list):
        self.locals = locals_
        self.stack = stack
        self.cellVarI = cellVarI
        self.preprocVars: Set[int] = set() 

    @classmethod
    def fromFunction(cls, fn: FunctionType, fnArgs: tuple, fnKwargs: dict):
        co = fn.__code__
        localVars = [None for _ in range(fn.__code__.co_nlocals)]
        if inspect.ismethod(fn):
            fnArgs = tuple((fn.__self__, *fnArgs))

        assert len(fnArgs) == co.co_argcount, ("Must have the correct number of arguments",
                                               len(fnArgs), co.co_argcount)
        for i, v in enumerate(fnArgs):
            localVars[i] = v
        if fnKwargs:
            raise NotImplementedError()

        varNameToI = {n: i for i, n in enumerate(fn.__code__.co_varnames)}
        cellVarI = {}
        for i, name in enumerate(fn.__code__.co_cellvars):
            cellVarI[i] = varNameToI[name]

        return PythonBytecodeFrame(localVars, cellVarI, [])


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
        self.hls = hls
        self.fn = fn
        self.to_ssa: Optional[AstToSsa] = None
        self.blockToLabel: Dict[SsaBasicBlock, BlockLabel] = {}
        self.offsetToBlock: Dict[BlockLabel, SsaBasicBlock] = {}
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
        with open("tmp/cfg.dot", "w") as f:
            self.blockTracker.dumpCfgToDot(f)

        # print(self.loops)
        # print(cfg._adj)
        # print(self.loops)

        self.to_ssa = AstToSsa(self.hls.ssaCtx, fn.__name__, None)
        # self.to_ssa._onAllPredecsKnown(self.to_ssa.start)
        curBlock = self.to_ssa.start
        self.blockToLabel[curBlock] = (0,)
        self.offsetToBlock[(0,)] = curBlock
        for _ in self.blockTracker.addGenerated((0,)):
            pass  # should yield only entry block which should be already sealed

        frame = PythonBytecodeFrame.fromFunction(fn, fnArgs, fnKwargs)
        self._translateBytecodeBlock(self.bytecodeBlocks[0], frame, curBlock)
        if curBlock.predecessors:
            # because for LLVM entry point must not have predecessors
            entry = SsaBasicBlock(self.to_ssa.ssaCtx, "entry")
            entry.successors.addTarget(None, curBlock)
            self.to_ssa.start = entry
        # with open("tmp/cfg_final.dot", "w") as f:
        #    self.blockTracker.dumpCfgToDot(f)

        self.to_ssa.finalize()

        return self.to_ssa, None

    def _blockToSsa(self,
            curBlock: SsaBasicBlock,
            curBlockCode: Union[SsaValue, List[SsaValue]]) -> SsaBasicBlock:
        return self.to_ssa.visit_CodeBlock_list(curBlock, flatten(curBlockCode))

    def _jumpToNextBlock(self,
            instr: Instruction,
            curBlock: SsaBasicBlock,
            blocks: Dict[BlockLabel, SsaBasicBlock]):
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
            block = self.offsetToBlock[dstLabel] = SsaBasicBlock(
                self.to_ssa.ssaCtx, f"block{'_'.join(str(o) for o in dstLabel)}")
            self.blockToLabel[block] = dstLabel
            return block, True

        return block, False

    def _getOrCreateSsaBasicBlockAndJump(self,
            curBlock: SsaBasicBlock,
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

        elif isinstance(cond, (RtlSignal, SsaValue)):
            # regular hw evaluated jump
            pass

        else:
            assert cond is None, cond
            # potentially preproc evaluated jump
            # it is a preproc loop if we are jumping from loop header unconditionally (cond is None is this case)
            curBlockOffset = self.blockToLabel[curBlock][-1]
            loop = self.loops.get(curBlockOffset, None)
            sucLoop = self.loops.get(sucBlockOffset, None)
            reenteringLoopBody = any(s.loop is loop for s in preprocLoopScope)
            isJumpFromLoopEntryToBody = (
                loop is not None and  # src is loop header
                (sucBlockOffset,) in loop.allBlocks  # dst is in loop body
            )
            isJumpFromPreprocLoopBodyToLoopEntry = (
                sucLoop is not None and
                any((sucBlockOffset,) == s.loop.entryPoint for s in preprocLoopScope)
            )
            # if jumping from body of the current loop and this loop does not have a preproc scope it means
            # that it is completely HW evaluated and we should not touch preproc scopes
            # :note: if loop is not None the curBlock is a header of that loop

            # if this is a jump to a header of some currently evaluated loop
            if isJumpFromLoopEntryToBody or isJumpFromPreprocLoopBodyToLoopEntry:
                if isJumpFromPreprocLoopBodyToLoopEntry:
                    # prepare scope for start of new iteration
                    while preprocLoopScope:
                        curLoop: PyBytecodeLoop = preprocLoopScope[-1].loop
                        if (sucBlockOffset,) in curLoop.allBlocks:
                            break  # in current loop
                        else:
                            prevLoopMeta.appendleft(preprocLoopScope.pop())

                # if this is a jump to a header of new loop
                if isJumpFromLoopEntryToBody and not reenteringLoopBody:
                    # jump from first header to body
                    loopMeta = PreprocLoopScope(loop, 0)
                    preprocLoopScope.append(loopMeta)
                    loopMetaAdded = True

                elif isJumpFromPreprocLoopBodyToLoopEntry:
                    # isJumpFromPreprocLoopBodyToLoopEntry
                    # this must be jump to a new body of already executed loop  
                    prevLoopMeta.appendleft(preprocLoopScope.pop())
                    loopMeta = PreprocLoopScope(loop if isJumpFromLoopEntryToBody else sucLoop, prevLoopMeta[0].iterationIndex + 1)
                    preprocLoopScope.append(loopMeta)
                    loopMetaAdded = True
                else:
                    loopMeta = preprocLoopScope[-1]

                if isJumpFromLoopEntryToBody or reenteringLoopBody:
                    if loopMeta.iterationIndex == 0:
                        assert not reenteringLoopBody
                        # update cycle entry point label for label prefix adding
                        oldLabel = self.blockToLabel[curBlock]
                        newLabel = generateBlockLabel(preprocLoopScope, oldLabel[-1])
                        self.blockToLabel[curBlock] = newLabel
                        self.offsetToBlock[newLabel] = curBlock
                        
                        # prepare blocks first loop body in cfg
                        blockWithAllPredecessorsNewlyKnown = list(
                            self.blockTracker.cfgAddPrefixToLoopBody(loopMeta.loop, preprocLoopScope)
                        )
                        
                    else:
                        assert reenteringLoopBody
                        # this is a jump to a next iteration of preproc loop
                        blockWithAllPredecessorsNewlyKnown = list(
                            self.blockTracker.cfgCopyLoopBody(loopMeta.loop, preprocLoopScope)
                        )
                    # with open(f"tmp/cfg_{preprocLoopScope}.dot", "w") as f:
                    #    self.blockTracker.dumpCfgToDot(f)
            
        # if this is a jump just in linear code or inside body of the loop
        target = self.blockTracker._getBlockLabel(sucBlockOffset)
        sucBlock, sucBlockIsNew = self._getOrCreateSsaBasicBlock(target)
        curBlock.successors.addTarget(cond, sucBlock)
    
        if blockWithAllPredecessorsNewlyKnown is not None:
            for bl in blockWithAllPredecessorsNewlyKnown:
                self.to_ssa._onAllPredecsKnown(self.offsetToBlock[bl])

        if sucBlockIsNew:
            for bl in self.blockTracker.addGenerated(target):
                self.to_ssa._onAllPredecsKnown(self.offsetToBlock[bl])

            self._translateBytecodeBlock(self.bytecodeBlocks[sucBlockOffset], frame, sucBlock)

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
        if instructions[0].opname == "FOR_ITER":
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
                self._getOrCreateSsaBasicBlockAndJump(curBlock, forIter.argval, None, frame)
                return
            # jump into loop body
            self._getOrCreateSsaBasicBlockAndJump(curBlock, forIter.offset + 2, None, frame)

        else:
            for last, instr in iter_with_last(instructions):
                self._translateBytecodeBlockInstruction(instr, last, frame, curBlock)

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

    def _translateBytecodeBlockInstruction(self,
            instr: Instruction,
            last: bool,
            frame: PythonBytecodeFrame,
            curBlock: SsaBasicBlock):

        if last and instr.opname in JUMP_OPS:
            self._translateInstructionJumpHw(instr, frame, curBlock)
            return

        elif instr.opname == "RETURN_VALUE":
            assert last, instr
            return
        
        stack = frame.stack
        locals_ = frame.locals
        try:
            # Python assigns each name in a scope to exactly one category:
            #  local, enclosing, or global/builtin.
            # CPython, implements that rule by using:
            #  FAST locals, DEREF closure cells, and NAME or GLOBAL lookups.
            
            opname = instr.opname
            if opname == 'NOP':
                # Do nothing code. Used as a placeholder by the bytecode optimizer.
                return

            elif opname == "POP_TOP":
                # Removes the top-of-stack (TOS) item.
                res = stack.pop()
                if isinstance(res, (HlsStreamProcWrite, HlsStreamProcRead, HdlAssignmentContainer)):
                    self._blockToSsa(curBlock, res)

            elif opname == 'LOAD_DEREF':
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

            elif opname == 'LOAD_ATTR':
                v = stack[-1]
                v = getattr(v, instr.argval)
                stack[-1] = v

            elif opname == 'LOAD_FAST':
                v = locals_[instr.arg]
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

            elif opname == 'LOAD_CLOSURE':
                # nested scopes: access the cell object
                v = locals_[frame.cellVarI[instr.arg]]
                stack.append(CellType(v))

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
                v = locals_[instr.arg]
                if v is None:
                    if isinstance(vVal, (HValue, RtlSignal, SsaValue)):
                        # only if it is a value which generates hw variable
                        v = self.hls.var(instr.argval, vVal._dtype)

                    locals_[instr.arg] = v

                if instr.arg not in frame.preprocVars and isinstance(v, RtlSignal):
                    # only if it is a hw variable
                    stm = v(vVal)
                    self._blockToSsa(curBlock, stm)
                else:
                    if isinstance(vVal, PythonBytecodeInPreproc):
                        vVal = vVal.ref
                        frame.preprocVars.add(instr.arg)

                    locals_[instr.arg] = vVal

            elif opname == 'STORE_DEREF':
                # nested scopes: access a variable through its cell object
                raise NotImplementedError()

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

            elif opname == 'COMPARE_OP':
                binOp = CMP_OPS[instr.argval]
                b = stack.pop()
                a = stack.pop()
                stack.append(binOp(a, b))

            elif opname == "GET_ITER":
                a = stack.pop()
                stack.append(iter(a))

            elif opname == "EXTENDED_ARG":
                pass

            elif opname == "UNPACK_SEQUENCE":
                seq = stack.pop()
                stack.extend(reversed(tuple(seq)))

            elif opname == "MAKE_FUNCTION":
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
                newFn = FunctionType(code, {}, name, defaults, closure)
                stack.append(newFn)

            else:
                binOp = BIN_OPS.get(opname, None)
                if binOp is not None:
                    b = stack.pop()
                    a = stack.pop()
                    # if binOp is operator.getitem:
                    #    if this is indexing using hw value on non hw object we need to expand it to a switch on individual cases
                    #    raise NotImplementedError()
                    stack.append(binOp(a, b))
                    return

                unOp = UN_OPS.get(opname, None)
                if unOp is not None:
                    a = stack.pop()
                    stack.append(unOp(a))
                    return

                rotOp = ROT_OPS.get(opname, None)
                if rotOp is not None:
                    rotOp(stack)
                    return

                buildOp = BUILD_OPS.get(opname, None)
                if buildOp is not None:
                    buildOp(instr, stack)
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

        if last:
            # jump to next block, there was no explicit jump because this is regular code flow, but the next instruction
            # is jump target
            self._getOrCreateSsaBasicBlockAndJump(curBlock, instr.offset + 2, None, frame)

    def _translateInstructionJumpHw(self, instr: Instruction,
                                    frame: PythonBytecodeFrame,
                                    curBlock: SsaBasicBlock):
        try:
            assert curBlock
            opname = instr.opname

            if opname == 'RETURN_VALUE':
                return None

            elif opname == 'JUMP_ABSOLUTE' or opname == 'JUMP_FORWARD':
                self._getOrCreateSsaBasicBlockAndJump(curBlock, instr.argval, None, frame)

            elif opname in (
                    'JUMP_IF_FALSE_OR_POP',
                    'JUMP_IF_TRUE_OR_POP',
                    'POP_JUMP_IF_FALSE',
                    'POP_JUMP_IF_TRUE'):
                if opname in ('JUMP_IF_FALSE_OR_POP',
                              'JUMP_IF_TRUE_OR_POP'):
                    raise NotImplementedError("stack pop may depend on hw evaluated condition")

                cond = frame.stack.pop()
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
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, ifTrueOffset, None, frame)
                        self._onBlockNotGenerated(curBlock, ifFalseOffset)
                    else:
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, ifFalseOffset, None, frame)
                        self._onBlockNotGenerated(curBlock, ifTrueOffset)

                else:
                    if isinstance(cond, HValue):
                        if cond:
                            self._getOrCreateSsaBasicBlockAndJump(curBlock, ifTrueOffset, cond, frame)
                            self._onBlockNotGenerated(curBlock, ifFalseOffset)
                        else:
                            self._getOrCreateSsaBasicBlockAndJump(curBlock, ifFalseOffset, ~cond, frame)
                            self._onBlockNotGenerated(curBlock, ifTrueOffset)

                    else:
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, ifTrueOffset, cond, frame)
                        # cond = 1 because we did check in ifTrue branch and this is "else branch"
                        self._getOrCreateSsaBasicBlockAndJump(curBlock, ifFalseOffset, BIT.from_py(1), frame)

            else:
                raise NotImplementedError(instr)

        except HlsSyntaxError:
            raise  # do not decorate already decorated exceptions

        except Exception:
            # create decorated exception
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
