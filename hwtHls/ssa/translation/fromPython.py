from dis import findlinestarts, _get_instructions_bytes, Instruction, dis
import inspect
import operator
from types import FunctionType
from typing import Dict

from hwt.code import In
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.defs import BIT, BOOL
from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.hlsStreamProc.statements import HlsStreamProcWrite, \
    HlsStreamProcRead
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.value import SsaValue
from hwt.pyUtils.arrayQuery import flatten

# import inspect
UN_OPS = {
    'UNARY_NEGATIVE': operator.neg,
    'UNARY_NOT': operator.not_,
    'UNARY_INVERT': operator.invert,
}
BIN_OPS = {
    'BINARY_POWER': operator.pow,
    'BINARY_MULTIPLY': operator.mul,
    
    'BINARY_MODULO': operator.mod,
    'BINARY_ADD': operator.add,
    'BINARY_SUBTRACT': operator.sub,
    'BINARY_SUBSCR': operator.index,
    'BINARY_FLOOR_DIVIDE': operator.floordiv,
    'BINARY_TRUE_DIVIDE': operator.truediv,

    'BINARY_LSHIFT': operator.lshift,
    'BINARY_RSHIFT': operator.rshift,
    'BINARY_AND': operator.and_,
    'BINARY_XOR': operator.xor,
    'BINARY_OR': operator.or_,
}
CMP_OPS = {
    '<': operator.lt,
    '<=': operator.le,
    '==': AllOps.EQ._evalFn,
    '!=': operator.ne,
    '>': operator.gt,
    '>=': operator.ge,
    'in': In,
    'not in': lambda x, col:~In(x, col),
}
INPLACE_OPS = {
    'INPLACE_FLOOR_DIVIDE': operator.floordiv,
    'INPLACE_TRUE_DIVIDE': operator.truediv,
    'INPLACE_ADD': operator.add,
    'INPLACE_SUBTRACT': operator.sub,
    'INPLACE_MULTIPLY': operator.mul,
    
    'INPLACE_MODULO': operator.mod,
    
    'INPLACE_POWER': operator.pow,
    'INPLACE_LSHIFT': operator.lshift,
    'INPLACE_RSHIFT': operator.rshift,
    'INPLACE_AND': operator.and_,
    'INPLACE_XOR': operator.xor,
    'INPLACE_OR': operator.or_,
}


# https://www.synopsys.com/blogs/software-security/understanding-python-bytecode/
def pyFunctionToSsa(hls: HlsStreamProc, fn: FunctionType, *fnArgs, **fnKwargs):
    co = fn.__code__
    cell_names = co.co_cellvars + co.co_freevars
    linestarts = dict(findlinestarts(co))
    
    to_ssa = AstToSsa(hls.ssaCtx, "entry", None)
    to_ssa._onAllPredecsKnown(to_ssa.start)
    curBlock = to_ssa.start
    blocks: Dict[int, SsaBasicBlock] = {}
    curBlockCode = []
    # print(dis(fn))
    stack = []
    localVars = [None for _ in range(fn.__code__.co_nlocals)]
    if inspect.ismethod(fn):
        fnArgs = tuple((fn.__self__, *fnArgs))
    assert len(fnArgs) == co.co_argcount, ("Must have the correct number of arguments", len(fnArgs), co.co_argcount)
    for i, v in enumerate(fnArgs):
        localVars[i] = v
    if fnKwargs:
        raise NotImplementedError()

    instructions = tuple(_get_instructions_bytes(
        co.co_code, co.co_varnames, co.co_names,
        co.co_consts, cell_names, linestarts))
    
    blockPredecesorCount: Dict[int, int] = {}
    startOfBlock = True
    for instr in instructions:
        instr: Instruction
        if instr.is_jump_target or startOfBlock:
            b = blocks[instr.offset] = SsaBasicBlock(to_ssa.ssaCtx, f"block{instr.offset:d}")
            if instr.offset == 0:
                to_ssa.start.successors.addTarget(None, b)

        opname = instr.opname
        if opname == 'JUMP_ABSOLUTE':
            blockPredecesorCount[instr.argval] = blockPredecesorCount.get(instr.argval, 0) + 1
            startOfBlock = True
        elif opname == 'JUMP_FORWARD':
            raise NotImplementedError()
            startOfBlock = True
        elif opname in  ('JUMP_IF_FALSE_OR_POP',
                'JUMP_IF_TRUE_OR_POP',
                'POP_JUMP_IF_FALSE',
                'POP_JUMP_IF_TRUE',):
            startOfBlock = True
            blockPredecesorCount[instr.argval] = blockPredecesorCount.get(instr.argval, 0) + 1
            blockPredecesorCount[instr.offset + 2] = blockPredecesorCount.get(instr.offset + 2, 0) + 1
        else:
            startOfBlock = False
            
    blockPredecesorUnseen: Dict[SsaBasicBlock, int] = {blocks[k]: v for k, v in blockPredecesorCount.items()}
    
    def addBlockSuccessor(block: SsaBasicBlock, cond, blockSuccessor: SsaBasicBlock):
        block.successors.addTarget(cond, blockSuccessor)
        predRem = blockPredecesorUnseen[blockSuccessor]
        predRem -= 1
        blockPredecesorUnseen[blockSuccessor] = predRem
        if predRem == 0:
            to_ssa._onAllPredecsKnown(blockSuccessor)

    def blockToSsa():
        to_ssa.visit_CodeBlock_list(curBlock, flatten(curBlockCode))
        curBlockCode.clear()

    def checkIoRead(src):
        # if src is None or isinstance(src, (Interface, RtlSignal, int, HValue, SsaValue)):
        #    pass
        # else:
        #    raise NotImplementedError(instr, src)

        return src
   
    # :note: available instructions can be seen in opcode module
    for instr in instructions:
        assert curBlock is not None, "curBlock can be None only after the end of program"
        instr: Instruction
        if instr.is_jump_target:
            nextBlock = blocks[instr.offset]
            if curBlock is not nextBlock:
                blockToSsa()
                prevBlock = curBlock
                curBlock = nextBlock
                if not prevBlock.successors.targets or prevBlock.successors.targets[-1][0] is not None:
                    prevBlock.successors.addTarget(None, curBlock)
                
        opname = instr.opname
        if opname == 'LOAD_DEREF':
            v = fn.__closure__[instr.arg].cell_contents
            stack.append(v)

        elif opname == 'LOAD_ATTR':
            v = stack[-1]
            v = getattr(v, instr.argval)
            stack[-1] = v

        elif opname == 'STORE_ATTR':
            dst = stack.pop()
            dst = getattr(dst, instr.argval)
            src = checkIoRead(stack.pop())

            if isinstance(dst, (Interface, RtlSignal)):
                curBlockCode.append(hls.write(src, dst))
            else:
                raise NotImplementedError(instr)

        elif opname == 'STORE_FAST':
            vVal = checkIoRead(stack.pop())
            v = localVars[instr.arg]
            if v is None:
                v = hls.var(instr.argval, vVal._dtype)
                localVars[instr.arg] = v
            curBlockCode.append(v(vVal))

        elif opname == 'LOAD_FAST':
            v = localVars[instr.arg]
            assert v is not None, (instr.argval, "used before defined")
            stack.append(v)
  
        elif opname == 'LOAD_CONST':
            stack.append(instr.argval)

        elif opname == 'LOAD_GLOBAL':
            stack.append(fn.__globals__[instr.argval])

        elif opname == 'LOAD_METHOD':
            v = stack.pop()
            v = getattr(v, instr.argval)
            stack.append(v)

        elif opname == 'CALL_METHOD' or opname == "CALL_FUNCTION":
            args = []
            for _ in range(instr.arg):
                args.append(checkIoRead(stack.pop()))
            m = stack.pop()
            res = m(*reversed(args))
            stack.append(res)
        elif opname == 'CALL_FUNCTION_KW':
            args = []
            kwNames = stack.pop()
            assert isinstance(kwNames, tuple), kwNames
            for _ in range(instr.arg):
                args.append(checkIoRead(stack.pop()))

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
                curBlockCode.append(res)

        elif opname == 'RETURN_VALUE':
            # finalizeBlock()
            continue
        
        elif opname == 'JUMP_ABSOLUTE':
            blockToSsa()
            sucBlock = blocks.get(instr.argval)
            addBlockSuccessor(curBlock, None, sucBlock)
            
            curBlock = blocks.get(instr.offset + 2, None)
            # this could be the None only on the end of the program
 
        elif opname == 'POP_JUMP_IF_FALSE':
            blockToSsa()
            cond = checkIoRead(stack.pop())
            curBlock, cond = to_ssa.visit_expr(curBlock, cond)
            sucIfTrueBlock = blocks.get(instr.offset + 2)
            sucIfFalseBlock = blocks.get(instr.argval)
            addBlockSuccessor(curBlock, cond, sucIfTrueBlock)
            addBlockSuccessor(curBlock, None, sucIfFalseBlock)
            
            curBlock = sucIfTrueBlock

        elif opname == 'COMPARE_OP':
            binOp = CMP_OPS[instr.argval]
            b = checkIoRead(stack.pop())
            a = checkIoRead(stack.pop())
            stack.append(binOp(a, b))
        else:
            binOp = BIN_OPS.get(opname, None)
            if binOp is not None:
                b = checkIoRead(stack.pop())
                a = checkIoRead(stack.pop())
                stack.append(binOp(a, b))
                continue
            unOp = UN_OPS.get(opname, None) 
            if unOp is not None:
                a = checkIoRead(stack.pop())
                stack.append(unOp(a))
                continue
            inplaceOp = INPLACE_OPS.get(opname, None)
            if inplaceOp is not None:
                b = checkIoRead(stack.pop())
                a = checkIoRead(stack.pop())
                stack.append(inplaceOp(a, b))
            else:
                raise NotImplementedError(instr)

    to_ssa.finalize()
   
    return to_ssa, None
