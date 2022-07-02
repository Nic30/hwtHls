import builtins
from dis import Instruction, dis
from future.moves import sys
import operator
from types import CellType
from types import FunctionType
from typing import Optional, Dict, List

from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.value import HValue
from hwt.pyUtils.arrayQuery import flatten
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.errors import HlsSyntaxError
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.frontend.pyBytecode.blockLabel import BlockLabel
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame, \
    PyBytecodeLoopInfo, _PyBytecodeUnitialized
from hwtHls.frontend.pyBytecode.indexExpansion import PyObjectHwSubscriptRef, expandBeforeUse
from hwtHls.frontend.pyBytecode.instructions import CMP_OPS, BIN_OPS, UN_OPS, \
    INPLACE_BIN_OPS, ROT_OPS, BUILD_OPS, NOP, \
    POP_TOP, LOAD_DEREF, LOAD_ATTR, LOAD_FAST, LOAD_CONST, LOAD_GLOBAL, \
    LOAD_METHOD, LOAD_CLOSURE, STORE_ATTR, STORE_FAST, STORE_DEREF, CALL_METHOD, \
    CALL_FUNCTION, CALL_FUNCTION_KW, COMPARE_OP, GET_ITER, UNPACK_SEQUENCE, \
    MAKE_FUNCTION, STORE_SUBSCR, EXTENDED_ARG, CALL_FUNCTION_EX
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc, \
    PyBytecodeInline
from hwtHls.scope import HlsScope
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue


class SsaBlockGroup():
    """
    Represents a set of block for a specific block label.
    """

    def __init__(self, begin: SsaBasicBlock):
        self.begin = begin
        self.end = begin


class PyBytecodeToSsaLowLevel():

    def __init__(self, hls: HlsScope, label: str):
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
            
        frame = PyBytecodeFrame.fromFunction(fn, fnArgs, fnKwargs, self.callStack)
        self.toSsa = HlsAstToSsa(self.hls.ssaCtx, fn.__name__, None)
        curBlock = self.toSsa.start
        self._debugDump(frame, "_begin")
        
        startBlockLabel = self.blockToLabel[curBlock] = frame.blockTracker._getBlockLabel(0)
        self.labelToBlock[startBlockLabel] = SsaBlockGroup(curBlock)
        try:
            self._translateBytecodeBlock(frame, frame.bytecodeBlocks[0], curBlock)
            assert not frame.loopStack, ("All loops must be exited", frame.loopStack)
        finally:
            self._debugDump(frame, "_final")
        assert len(self.callStack) == 1 and self.callStack[0] is frame, self.callStack
    
        if curBlock.predecessors:
            # because for LLVM entry point must not have predecessors
            self.toSsa.start.label += "_0"
            entry = SsaBasicBlock(self.toSsa.ssaCtx, fn.__name__)
            self.toSsa._onAllPredecsKnown(frame, entry)
            entry.successors.addTarget(None, curBlock)
            self.toSsa.start = entry
        
        self.toSsa.finalize()

    def _debugDump(self, frame: PyBytecodeFrame, label=None):
        if self.debug:
            with open(f"tmp/{self.label:s}_cfg_{self.debugGraphCntr:d}{label if label else ''}.dot", "w") as f:
                sealedBlocks = set(self.blockToLabel[b] for b in self.toSsa.m_ssa_u.sealedBlocks)
                frame.blockTracker.dumpCfgToDot(f, sealedBlocks)
                self.debugGraphCntr += 1

    def _getOrCreateSsaBasicBlock(self, dstLabel: BlockLabel):
        block = self.labelToBlock.get(dstLabel, None)
        if block is None:
            block = SsaBasicBlock(
                self.toSsa.ssaCtx, f"block{'_'.join(str(o) for o in dstLabel)}")
            self.labelToBlock[dstLabel] = SsaBlockGroup(block)
            self.blockToLabel[block] = dstLabel
            return block, True

        return block.begin, False

    def _onBlockGenerated(self, frame: PyBytecodeFrame, label: BlockLabel):
        """
        Called once all predecessors were added in SSA.
        """
        for bl in frame.blockTracker.addGenerated(label):
            # we can seal the block only after body was generated
            # :attention: The header of hardware loop can be sealed only after all body blocks were generated
            #             Otherwise some PHI arguments can be lost
            self._onAllPredecsKnown(frame, self.labelToBlock[bl].begin)
    
    def _addNotGeneratedBlock(self, frame: PyBytecodeFrame, srcBlockLabel: BlockLabel, dstBlockLabel: BlockLabel):
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
        self._addNotGeneratedBlock(frame, srcBlockLabel, dstBlockLabel)

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
     
    def _makeFunction(self, frame: PyBytecodeFrame, instr: Instruction, stack: list):
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
        newFn = FunctionType(code, frame.fn.__globals__, name, defaults, closure)
        stack.append(newFn)

    def _translateCallInlined(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock,
                              fn: FunctionType, fnArgs: list, fnKwargs: dict):
        # create function entry point block, assign to all function parameters and prepare frame where we initialize preproc/hw variable meta
        # for variables from arguments
        callFrame = PyBytecodeFrame.fromFunction(fn, fnArgs, fnKwargs, self.callStack)

        curBlockLabel = self.blockToLabel[curBlock]
        fnEntryBlockLabel = callFrame.blockTracker._getBlockLabel(0)
        fnEntryBlock, fnEntryBlockIsNew = self._getOrCreateSsaBasicBlock(fnEntryBlockLabel)
        curBlock.successors.addTarget(None, fnEntryBlock)
        assert fnEntryBlockIsNew
        self._debugDump(callFrame, label=callFrame.fn.__name__)
        self._translateBytecodeBlock(callFrame, callFrame.bytecodeBlocks[0], fnEntryBlock)
        self._debugDump(callFrame, label=callFrame.fn.__name__)
        
        curBlockAfterCall = SsaBasicBlock(self.toSsa.ssaCtx, f"{curBlock.label:s}_afterCall")
        self.labelToBlock[curBlockLabel].end = curBlockAfterCall
        self.blockToLabel[curBlockAfterCall] = curBlockLabel
        # [todo] iterate return points in frame and jump to curBlockAfterCall
        finalRetVal = None
        for (_, retBlock, retVal) in callFrame.returnPoints:
            if retVal is not None:
                assert len(callFrame.returnPoints) == 1, "If this is not hardware object, the function has to have exactly a single return"
                finalRetVal = retVal

            retBlock.successors.addTarget(None, curBlockAfterCall)
        
        frame.stack.append(finalRetVal)
        # todo process return points and connected to curBlockAfterCall block in cfg
        self.callStack.pop()
        self._onAllPredecsKnown(frame, curBlockAfterCall)

        return curBlockAfterCall
        
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
                res, curBlock = expandBeforeUse(frame, res, curBlock)
                if isinstance(res, HlsWrite):
                    res: HlsWrite
                    if isinstance(res.dst, PyObjectHwSubscriptRef):
                        hls = self.hls
                        return res.dst.expandSetitemAsSwitchCase(frame, curBlock,
                                                                 lambda i, dst: hls.write(res._origSrc, dst))
                    
                if isinstance(res, (HlsWrite, HlsRead, HdlAssignmentContainer)):
                    self.toSsa.visit_CodeBlock_list(curBlock, [res, ])

            elif opcode == LOAD_DEREF:
                # nested scopes: access a variable through its cell object
                closure = frame.fn.__closure__
                if closure is None:
                    # [todo] check what is the relation between function without closure
                    #  and child function closure
                    v = locals_[frame.cellVarI[instr.arg]]
                else:
                    v = closure[instr.arg].cell_contents
                # closure[instr.arg] = None
                assert v is not _PyBytecodeUnitialized, (instr.argval, "used before defined")
                stack.append(v)

            elif opcode == LOAD_ATTR:
                v = stack[-1]
                v = getattr(v, instr.argval)
                stack[-1] = v

            elif opcode == LOAD_FAST:
                v = locals_[instr.arg]
                assert v is not _PyBytecodeUnitialized, (instr.argval, "used before defined")
                stack.append(v)

            elif opcode == LOAD_CONST:
                stack.append(instr.argval)

            elif opcode == LOAD_GLOBAL:
                if instr.argval in frame.fn.__globals__:
                    v = frame.fn.__globals__[instr.argval]
                else:
                    # assert instr.argval in builtins.__dict__, instr.argval
                    v = builtins.__dict__[instr.argval]
                assert v is not _PyBytecodeUnitialized, (instr.argval, "used before defined")
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
                src, curBlock = expandBeforeUse(frame, src, curBlock)

                if isinstance(dst, (Interface, RtlSignal)):
                    # stm = self.hls.write(src, dst)
                    self.toSsa.visit_CodeBlock_list(curBlock, flatten(dst(src)))
                else:
                    raise NotImplementedError(instr, dst)

            elif opcode == STORE_FAST:
                vVal = stack.pop()
                vVal, curBlock = expandBeforeUse(frame, vVal, curBlock)
                v = locals_[instr.arg]
                varIndex = instr.arg
                if varIndex not in frame.preprocVars:
                    if v is _PyBytecodeUnitialized and isinstance(vVal, (HValue, RtlSignal, SsaValue)):
                        # only if it is a value which generates HW variable
                        t = getattr(vVal, "_dtypeOrig", vVal._dtype)
                        v = self.hls.var(instr.argval, t)
                        locals_[varIndex] = v

                    if isinstance(v, (RtlSignal, Interface)):
                        # only if it is a hw variable, create assignment to HW variable
                        stm = v(vVal)
                        self.toSsa.visit_CodeBlock_list(curBlock, flatten([stm, ]))
                        return curBlock

                if isinstance(vVal, PyBytecodeInPreproc):
                    vVal = vVal.ref
                    frame.preprocVars.add(varIndex)

                locals_[varIndex] = vVal

            elif opcode == STORE_DEREF:
                # nested scopes: access a variable through its cell object
                vVal = stack.pop()
                vVal, curBlock = expandBeforeUse(frame, vVal, curBlock)
                closure = frame.fn.__closure__
                varIndex = frame.cellVarI[instr.arg]
                if closure is None:
                    # [todo] check what is the relation between function without closure
                    #  and child function closure
                    v = locals_[varIndex]
                    
                    if varIndex not in frame.preprocVars:
                        if v is _PyBytecodeUnitialized and isinstance(vVal, (HValue, RtlSignal, SsaValue)):
                            # only if it is a value which generates HW variable
                            t = getattr(vVal, "_dtypeOrig", vVal._dtype)
                            v = self.hls.var(instr.argval, t)
                            locals_[varIndex] = v
    
                        if isinstance(v, (RtlSignal, Interface)):
                            # only if it is a hw variable, create assignment to HW variable
                            stm = v(vVal)
                            self.toSsa.visit_CodeBlock_list(curBlock, flatten([stm, ]))
                            return curBlock

                    if isinstance(vVal, PyBytecodeInPreproc):
                        vVal = vVal.ref
                        frame.preprocVars.add(varIndex)

                    locals_[varIndex] = vVal
                    
                else:
                    v = closure[varIndex].cell_contents
                    varIndex = instr.arg
                    if varIndex not in frame.preprocVars:
                        if v is _PyBytecodeUnitialized and isinstance(vVal, (HValue, RtlSignal, SsaValue)):
                            # only if it is a value which generates HW variable
                            t = getattr(vVal, "_dtypeOrig", vVal._dtype)
                            v = self.hls.var(instr.argval, t)
                            closure[varIndex].cell_contents = v
    
                        if isinstance(v, (RtlSignal, Interface)):
                            # only if it is a hw variable, create assignment to HW variable
                            stm = v(vVal)
                            self.toSsa.visit_CodeBlock_list(curBlock, flatten([stm, ]))
                            return curBlock
    
                    if isinstance(vVal, PyBytecodeInPreproc):
                        vVal = vVal.ref
                        frame.preprocVars.add(varIndex)
    
                    closure[varIndex].cell_contents = vVal

            elif opcode == CALL_METHOD or opcode == CALL_FUNCTION:
                argCnt = instr.arg
                if argCnt == 0:
                    args = []
                else:
                    args = stack[-argCnt:]
                for _ in range(argCnt):
                    stack.pop()
                m = stack.pop()
                if isinstance(m, PyBytecodeInline):
                    kwargs = {}
                    return self._translateCallInlined(frame, curBlock, m.ref, args, kwargs)

                res = m(*args)
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
                    raise NotImplementedError(instr, kw_args)

                args = stack.pop()
                m = stack.pop()
                res = m(*reversed(tuple(args)))
                stack.append(res)
                
            elif opcode == COMPARE_OP:
                binOp = CMP_OPS[instr.arg]
                b = stack.pop()
                a = stack.pop()
                a, curBlock = expandBeforeUse(frame, a, curBlock)
                b, curBlock = expandBeforeUse(frame, b, curBlock)
                stack.append(binOp(a, b))

            elif opcode == GET_ITER:
                a = stack.pop()
                a, curBlock = expandBeforeUse(frame, a, curBlock)
                stack.append(iter(a))

            elif opcode == EXTENDED_ARG:
                pass

            elif opcode == UNPACK_SEQUENCE:
                seq = stack.pop()
                stack.extend(reversed(tuple(seq)))

            elif opcode == MAKE_FUNCTION:
                self._makeFunction(frame, instr, stack)
                
            elif opcode == STORE_SUBSCR:
                index = stack.pop()
                sequence = stack.pop()
                val = stack.pop()
                index, curBlock = expandBeforeUse(frame, index, curBlock)
                val, curBlock = expandBeforeUse(frame, val, curBlock)
                if isinstance(index, (RtlSignal, SsaValue)) and not isinstance(sequence, (RtlSignal, SsaValue)):
                    if not isinstance(sequence, PyObjectHwSubscriptRef):
                        sequence = PyObjectHwSubscriptRef(self, sequence, index, instr.offset)
                    return sequence.expandSetitemAsSwitchCase(frame, curBlock, lambda i, dst: dst(val))

                operator.setitem(sequence, index, val)
                #stack.append()

            else:
                binOp = BIN_OPS.get(opcode, None)
                if binOp is not None:
                    b = stack.pop()
                    a = stack.pop()
                    a, curBlock = expandBeforeUse(frame, a, curBlock)
                    b, curBlock = expandBeforeUse(frame, b, curBlock)
                
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
                    a, curBlock = expandBeforeUse(frame, a, curBlock)
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
                    b, curBlock = expandBeforeUse(frame, b, curBlock)
                
                    a = stack.pop()
                    if isinstance(a, PyObjectHwSubscriptRef):
                        a: PyObjectHwSubscriptRef
                        # we expand as a regular bin op, and store later in store_subscript
                        a, curBlock = a.expandIndexOnPyObjAsSwitchCase(frame, curBlock)
                        # .expandSetitemAsSwitchCase(frame, curBlock, lambda _, dst: dst(inplaceOp(dst, b)))
                    res = inplaceOp(a, b)

                    stack.append(res)
                    
                    return curBlock
            
                raise NotImplementedError(instr)

        except HlsSyntaxError:
            raise  # already decorated exception, just propagate

        except Exception:
            # a new exception generated directly from user code
            raise self._createInstructionException(frame, instr)

        return curBlock
