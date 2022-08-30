import builtins
from dis import Instruction
import operator
from types import FunctionType, CellType
from typing import Callable, Dict, Union

from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.value import HValue
from hwt.interfaces.std import Signal
from hwt.pyUtils.arrayQuery import flatten
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame, \
    _PyBytecodeUnitialized
from hwtHls.frontend.pyBytecode.indexExpansion import expandBeforeUse, \
    PyObjectHwSubscriptRef
from hwtHls.frontend.pyBytecode.instructions import CMP_OPS, BIN_OPS, UN_OPS, \
    INPLACE_BIN_OPS, ROT_OPS, BUILD_OPS, NOP, \
    POP_TOP, LOAD_DEREF, LOAD_ATTR, LOAD_FAST, LOAD_CONST, LOAD_GLOBAL, \
    LOAD_METHOD, LOAD_CLOSURE, STORE_ATTR, STORE_FAST, STORE_DEREF, CALL_METHOD, \
    CALL_FUNCTION, CALL_FUNCTION_KW, COMPARE_OP, GET_ITER, UNPACK_SEQUENCE, \
    MAKE_FUNCTION, STORE_SUBSCR, EXTENDED_ARG, CALL_FUNCTION_EX, DELETE_DEREF, DELETE_FAST, \
    FORMAT_VALUE, LIST_EXTEND, LIST_TO_TUPLE, LIST_APPEND, IS_OP
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc, \
    PyBytecodeInline, _PyBytecodePragma, PyBytecodePreprocHwCopy
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue


class PyBytecodeToSsaLowLevelOpcodes():
    """
    https://docs.python.org/3/library/dis.html
    """

    def __init__(self):
        self.opcodeDispatch: Dict[int, Callable[[], SsaBasicBlock]] = {
            NOP: self.opcode_NOP,
            POP_TOP: self.opcode_POP_TOP,
            DELETE_FAST: self.opcode_DELETE_FAST,
            DELETE_DEREF: self.opcode_DELETE_DEREF,
            LOAD_CLOSURE: self.opcode_LOAD_CLOSURE,
            LOAD_DEREF: self.opcode_LOAD_DEREF,
            STORE_DEREF: self.opcode_STORE_DEREF,
            LOAD_ATTR: self.opcode_LOAD_ATTR,
            LOAD_FAST: self.opcode_LOAD_FAST,
            LOAD_CONST: self.opcode_LOAD_CONST,
            LOAD_GLOBAL: self.opcode_LOAD_GLOBAL,
            LOAD_METHOD: self.opcode_LOAD_METHOD,
            STORE_ATTR: self.opcode_STORE_ATTR,
            STORE_FAST: self.opcode_STORE_FAST,
            CALL_METHOD: self.opcode_CALL_METHOD,
            CALL_FUNCTION: self.opcode_CALL_METHOD,
            CALL_FUNCTION_KW: self.opcode_CALL_FUNCTION_KW,
            CALL_FUNCTION_EX: self.opcode_CALL_FUNCTION_EX,
            COMPARE_OP: self.opcode_COMPARE_OP,
            GET_ITER: self.opcode_GET_ITER,
            EXTENDED_ARG: self.opcode_EXTENDED_ARG,
            UNPACK_SEQUENCE: self.opcode_UNPACK_SEQUENCE,
            MAKE_FUNCTION: self.opcode_MAKE_FUNCTION,
            STORE_SUBSCR: self.opcode_STORE_SUBSCR,
            FORMAT_VALUE: self.opcode_FORMAT_VALUE,
            LIST_EXTEND: self.opcode_LIST_EXTEND,
            LIST_TO_TUPLE: self.opcode_LIST_TO_TUPLE,
            LIST_APPEND: self.opcode_LIST_APPEND,
            IS_OP: self.opcode_IS_OP,
        }
        opD = self.opcodeDispatch
        for createFn, opcodes in [
                (self.opcodeMakeBinaryOp, BIN_OPS),
                (self.opcodeMakeUnaryOp, UN_OPS),
                (self.opcodeMakeRotOp, ROT_OPS),
                (self.opcodeMakeBuildOp, BUILD_OPS),
                (self.opcodeMakeInplaceOp, INPLACE_BIN_OPS),
            ]:
            for opcode, op in opcodes.items():
                opD[opcode] = createFn(op)

    def opcode_NOP(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        # Do nothing code. Used as a placeholder by the bytecode optimizer.
        return curBlock

    def opcode_POP_TOP(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        res = frame.stack.pop()
        res, curBlock = expandBeforeUse(self, instr.offset, frame, res, curBlock)
        if isinstance(res, HlsWrite):
            res: HlsWrite
            dst = res.dst
            if isinstance(dst, PyObjectHwSubscriptRef):
                hls = self.hls
                if isinstance(dst.sequence, IoProxyAddressed):
                    raise AssertionError(dst, "This should already been expanded when HlsWrite was generated")
                return dst.expandSetitemAsSwitchCase(self, instr.offset, frame, curBlock,
                                                     lambda i, _dst: hls.write(res._origSrc, _dst))
            
        if isinstance(res, (HlsWrite, HlsRead, HdlAssignmentContainer)):
            self.toSsa.visit_CodeBlock_list(curBlock, [res, ])
        elif isinstance(res, list) and len(res) > 0 and isinstance(res[0], (HlsWrite, HlsRead, HdlAssignmentContainer)):
            self.toSsa.visit_CodeBlock_list(curBlock, res)
        elif isinstance(res, _PyBytecodePragma):
            res.apply(self, frame, curBlock, instr)

        return curBlock

    def opcode_DELETE_FAST(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        locals_ = frame.locals
        v = locals_[instr.arg]
        assert v is not _PyBytecodeUnitialized, "Delete of uninitalized"
        locals_[instr.arg] = _PyBytecodeUnitialized
        return curBlock

    def opcode_DELETE_DEREF(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        v = frame.freevars[instr.arg]
        assert v.get() is not _PyBytecodeUnitialized, "Delete of uninitalized"
        v.set(_PyBytecodeUnitialized)
        return curBlock

    def opcode_LOAD_CLOSURE(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        # nested scopes: access the cell object
        # Pushes a reference to the cell contained in slot i of the cell and free variable storage.
        # The name of the variable is co_cellvars[i] if i is less than the length of co_cellvars.
        # Otherwise it is co_freevars[i - len(co_cellvars)].
        v = frame.freevars[instr.arg]
        assert isinstance(v, CellType), v
        frame.stack.append(v)
        return curBlock

    def opcode_LOAD_DEREF(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        # nested scopes: access a variable through its cell object
        v = frame.freevars[instr.arg]
        assert isinstance(v, CellType), v
        _v = v.cell_contents
        assert _v is not _PyBytecodeUnitialized, (instr.argval, "used before defined")
        frame.stack.append(_v)
        return curBlock

    def opcode_STORE_DEREF(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        # nested scopes: access a variable through its cell object
        vVal = frame.stack.pop()
        vVal, curBlock = expandBeforeUse(self, instr.offset, frame, vVal, curBlock)
        v: CellType = frame.freevars[instr.arg]
        assert isinstance(v, CellType), v
        _v = v.cell_contents
        preprocVarKey = (CellType, instr.arg)
        if preprocVarKey not in frame.preprocVars:
            if _v is _PyBytecodeUnitialized and isinstance(vVal, (HValue, RtlSignal, SsaValue)):
                # only if it is a value which generates HW variable
                t = getattr(vVal, "_dtypeOrig", vVal._dtype)
                _v = self.hls.var(instr.argval, t)
    
            if isinstance(_v, (RtlSignal, Interface)):
                # only if it is a hw variable, create assignment to HW variable
                v.cell_contents = _v
                return self._storeToHwSignal(curBlock, _v, vVal)

        if isinstance(vVal, PyBytecodeInPreproc):
            vVal = vVal.ref
            frame.preprocVars.add(preprocVarKey)

        v.cell_contents = vVal
        return curBlock

    def opcode_LOAD_ATTR(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        v = stack[-1]
        try:
            v = getattr(v, instr.argval)
        except:
            raise
        stack[-1] = v
        return curBlock

    def opcode_LOAD_FAST(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        v = frame.locals[instr.arg]
        assert v is not _PyBytecodeUnitialized, (instr.argval, "used before defined")
        frame.stack.append(v)
        return curBlock

    def opcode_LOAD_CONST(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        frame.stack.append(instr.argval)
        return curBlock

    def opcode_LOAD_GLOBAL(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        if instr.argval in frame.fn.__globals__:
            v = frame.fn.__globals__[instr.argval]
        else:
            # assert instr.argval in builtins.__dict__, instr.argval
            v = builtins.__dict__[instr.argval]
        assert v is not _PyBytecodeUnitialized, (instr.argval, "used before defined")
        frame.stack.append(v)
        return curBlock

    def opcode_LOAD_METHOD(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        v = stack.pop()
        v = getattr(v, instr.argval)
        stack.append(v)
        return curBlock

    def _storeToHwSignal(self, curBlock, dst: Union[RtlSignal, InterfaceBase], src):
        if isinstance(src, SsaValue) and not isinstance(src, InterfaceBase):
            # :note: HlsRead is for exmple SsaValue and InterfaceBase
            if isinstance(dst, InterfaceBase):
                dst = dst._sig
            self.toSsa.m_ssa_u.writeVariable(dst, [], curBlock, src)
            return curBlock
        else:
            stm = dst(src)
            return self.toSsa.visit_CodeBlock_list(curBlock, flatten([stm, ]))
        
    def opcode_STORE_ATTR(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        dstParent = stack.pop()
        dst = getattr(dstParent, instr.argval)
        src = stack.pop()
        src, curBlock = expandBeforeUse(self, instr.offset, frame, src, curBlock)
        if isinstance(dst, (Interface, RtlSignal)):
            # stm = self.hls.write(src, dst)
            self._storeToHwSignal(curBlock, dst, src)
        else:
            raise NotImplementedError(instr, dst)

        return curBlock

    def opcode_STORE_FAST(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        locals_ = frame.locals
        vVal = stack.pop()
        vVal, curBlock = expandBeforeUse(self, instr.offset, frame, vVal, curBlock)
        v = locals_[instr.arg]
        varIndex = instr.arg
        if varIndex not in frame.preprocVars:
            if v is _PyBytecodeUnitialized and isinstance(vVal, (HValue, RtlSignal, Interface, SsaValue, Interface)):
                # only if it is a value which generates HW variable
                t = getattr(vVal, "_dtypeOrig", vVal._dtype)
                v = self.hls.var(instr.argval, t)
                locals_[varIndex] = v

            if isinstance(v, (RtlSignal, Interface)):
                # only if it is a hw variable, create assignment to HW variable
                return self._storeToHwSignal(curBlock, v, vVal)

        if isinstance(vVal, PyBytecodeInPreproc):
            vVal = vVal.ref
            frame.preprocVars.add(varIndex)

        locals_[varIndex] = vVal
        return curBlock

    def _translateCallInlined(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock,
                              fn: FunctionType, callSiteAddress: int, fnArgs: list, fnKwargs: dict):
        # create function entry point block, assign to all function parameters and prepare frame where we initialize preproc/hw variable meta
        # for variables from arguments
        callFrame = PyBytecodeFrame.fromFunction(fn, callSiteAddress, fnArgs, fnKwargs, self.callStack)

        curBlockLabel = self.blockToLabel[curBlock]
        fnEntryBlockLabel = callFrame.blockTracker._getBlockLabel(0)
        _fnEntryBlockLabel = fnEntryBlockLabel
        fnEntryBlock, fnEntryBlockIsNew = self._getOrCreateSsaBasicBlock(fnEntryBlockLabel)
        curBlock.successors.addTarget(None, fnEntryBlock)
        assert fnEntryBlockIsNew, "Must not reuse other existing block because every inline should generate new blocks only"
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

    def opcode_LIST_APPEND(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        Calls list.append(TOS1[-i], TOS). Used to implement list comprehensions.
        """
        stack = frame.stack
        v = stack.pop()
        list_ = stack[-instr.argval]
        list.append(list_, v)
        return curBlock
    
    def opcode_IS_OP(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        Performs is comparison, or is not if invert is 1.
        New in version 3.9.
        """
        stack = frame.stack
        v1 = stack.pop()
        v0 = stack.pop()
        
        invert = instr.argval
        if invert:
            res = v0 is not v1
        else:
            res = v0 is v1
        stack.append(res)
        return curBlock
     
    # CALL_FUNCTION
    def opcode_CALL_METHOD(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack

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
            return self._translateCallInlined(frame, curBlock, m.ref, instr.offset, args, kwargs)
        elif m is PyBytecodePreprocHwCopy:
            assert len(args) == 1, args
            curBlock, res, = self.toSsa.visit_expr(curBlock, args[0])
        else:
            res = m(*args)
        
        stack.append(res)
        return curBlock
    
    def opcode_LIST_EXTEND(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        Calls list.extend(TOS1[-i], TOS). Used to build lists.
        New in version 3.9.
        """
        stack = frame.stack
        v = stack.pop()
        list_ = stack[-instr.argval]
        list.extend(list_, v)
        return curBlock

    def opcode_LIST_TO_TUPLE(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        Pops a list from the stack and pushes a tuple containing the same values.
        New in version 3.9.
        """
        stack = frame.stack
        v = stack.pop()
        stack.append(tuple(v))
        return curBlock

    def opcode_CALL_FUNCTION_KW(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
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
        return curBlock

    def opcode_CALL_FUNCTION_EX(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack

        if instr.arg:
            kw_args = stack.pop()
            raise NotImplementedError(instr, kw_args)

        args = stack.pop()
        m = stack.pop()
        res = m(*reversed(tuple(args)))
        stack.append(res)
        return curBlock

    def opcode_COMPARE_OP(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        binOp = CMP_OPS[instr.arg]
        b = stack.pop()
        a = stack.pop()
        a, curBlock = expandBeforeUse(self, instr.offset, frame, a, curBlock)
        b, curBlock = expandBeforeUse(self, instr.offset, frame, b, curBlock)
        stack.append(binOp(a, b))
        return curBlock

    def opcode_GET_ITER(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        a = stack.pop()
        a, curBlock = expandBeforeUse(self, instr.offset, frame, a, curBlock)
        stack.append(iter(a))
        return curBlock

    def opcode_EXTENDED_ARG(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        return curBlock

    def opcode_UNPACK_SEQUENCE(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        seq = stack.pop()
        stack.extend(reversed(tuple(seq)))
        return curBlock

    def opcode_MAKE_FUNCTION(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        # MAKE_FUNCTION_FLAGS = ('defaults', 'kwdefaults', 'annotations', 'closure')
        stack = frame.stack
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
        return curBlock

    def opcode_STORE_SUBSCR(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        index = stack.pop()
        sequence = stack.pop()
        val = stack.pop()
        index, curBlock = expandBeforeUse(self, instr.offset, frame, index, curBlock)
        val, curBlock = expandBeforeUse(self, instr.offset, frame, val, curBlock)
        if isinstance(index, (RtlSignal, SsaValue, Signal)) and not isinstance(sequence, (RtlSignal, SsaValue, Signal)):
            if not isinstance(sequence, PyObjectHwSubscriptRef):
                sequence = PyObjectHwSubscriptRef(instr.offset, sequence, index)
            return sequence.expandSetitemAsSwitchCase(self, instr.offset, frame, curBlock, lambda i, dst: dst(val))
        if isinstance(sequence, (RtlSignal, Signal)):
            if isinstance(index, (RtlSignal, SsaValue, Signal)):
                raise NotImplementedError()
            else:
                stm = sequence[index](val)
                self.toSsa.visit_CodeBlock_list(curBlock, flatten([stm, ]))
                return curBlock
                
        operator.setitem(sequence, index, val)
        # stack.append()
        return curBlock

    def opcodeMakeBinaryOp(self, binOp: Callable):
        
        def opcode_BIN_OP(frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
            stack = frame.stack
            b = stack.pop()
            a = stack.pop()
            a, curBlock = expandBeforeUse(self, instr.offset, frame, a, curBlock)
            b, curBlock = expandBeforeUse(self, instr.offset, frame, b, curBlock)
            
            if binOp is operator.getitem and isinstance(b, (RtlSignal, Interface, SsaValue)) and not isinstance(a, (RtlSignal, SsaValue)):
                # if this is indexing using hw value on non hw object we need to expand it to a switch-case on individual cases
                # must generate blocks for switch cases,
                # for this we need a to keep track of start/end for each block because we do not have this newly generated blocks in original CFG
                o = PyObjectHwSubscriptRef(instr.offset, a, b)
                stack.append(o)
                return curBlock

            stack.append(binOp(a, b))
            return curBlock

        return opcode_BIN_OP

    def opcodeMakeUnaryOp(self, unOp: Callable):
        
        def opcode_UN_OP(frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
            stack = frame.stack
            a = stack.pop()
            a, curBlock = expandBeforeUse(self, instr.offset, frame, a, curBlock)
            stack.append(unOp(a))
            return curBlock

        return opcode_UN_OP
    
    def opcodeMakeRotOp(self, rotOp: Callable[[list], None]):

        def opcode_ROT_OP(frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
            rotOp(frame.stack)
            return curBlock

        return opcode_ROT_OP
    
    def opcodeMakeBuildOp(self, buildOp: Callable[[Instruction, list], None]):

        def opcode_BUILD_OP(frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
            buildOp(instr, frame.stack)
            return curBlock

        return opcode_BUILD_OP
    
    def opcodeMakeInplaceOp(self, inplaceOp: Callable[[Instruction, list], None]):

        def opcode_INPLACE_OP(frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
            stack = frame.stack
            b = stack.pop()
            b, curBlock = expandBeforeUse(self, instr.offset, frame, b, curBlock)
            
            a = stack.pop()
            if isinstance(a, PyObjectHwSubscriptRef):
                a: PyObjectHwSubscriptRef
                # we expand as a regular bin op, and store later in store_subscript
                a, curBlock = a.expandIndexOnPyObjAsSwitchCase(self, instr.offset, frame, curBlock)
                # .expandSetitemAsSwitchCase(frame, curBlock, lambda _, dst: dst(inplaceOp(dst, b)))
            res = inplaceOp(a, b)
    
            stack.append(res)
            
            return curBlock

        return opcode_INPLACE_OP

    def opcode_FORMAT_VALUE(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        Used for implementing formatted literal strings (f-strings). Pops an optional fmt_spec from the stack, then a required value. flags is interpreted as follows:
            (flags & 0x03) == 0x00: value is formatted as-is.
            (flags & 0x03) == 0x01: call str() on value before formatting it.
            (flags & 0x03) == 0x02: call repr() on value before formatting it.
            (flags & 0x03) == 0x03: call ascii() on value before formatting it.
            (flags & 0x04) == 0x04: pop fmt_spec from the stack and use it, else use an empty fmt_spec.
    
        Formatting is performed using PyObject_Format(). The result is pushed on the stack.
        New in version 3.6.
        """
        flags = instr.arg
        v = frame.stack.pop()
        if flags & 0x03 == 0x00:
            pass
        elif (flags & 0x03) == 0x01:
            v = str(v)
        elif (flags & 0x03) == 0x02:
            v = repr(v)
        elif (flags & 0x03) == 0x03:
            v = ascii(v)
        else:
            raise NotImplementedError(instr)
        
        frame.stack.append(v)
        return curBlock
    
