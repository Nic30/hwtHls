import operator
from dis import Instruction
from typing import Type

# https://docs.python.org/3/library/dis.html
UN_OPS = {
    'UNARY_POSITIVE': operator.pos,
    'UNARY_NEGATIVE': operator.neg,
    'UNARY_NOT': operator.not_,
    'UNARY_INVERT': operator.invert,
}

BIN_OPS = {
    'BINARY_POWER': operator.pow,
    'BINARY_MULTIPLY': operator.mul,
    'BINARY_MATRIX_MULTIPLY': operator.matmul,
    'BINARY_FLOOR_DIVIDE': operator.floordiv,
    'BINARY_TRUE_DIVIDE': operator.truediv,

    'BINARY_MODULO': operator.mod,
    'BINARY_ADD': operator.add,
    'BINARY_SUBTRACT': operator.sub,
    'BINARY_SUBSCR': operator.getitem,

    'BINARY_LSHIFT': operator.lshift,
    'BINARY_RSHIFT': operator.rshift,
    'BINARY_AND': operator.and_,
    'BINARY_XOR': operator.xor,
    'BINARY_OR': operator.or_,
}

CMP_OPS = {
    '<': operator.lt,
    '<=': operator.le,
    '==': operator.eq,
    '!=': operator.ne,
    '>': operator.gt,
    '>=': operator.ge,
    'in': operator.contains,
    'not in': lambda x, col: not operator.contains(x, col),
}

INPLACE_BIN_OPS = {
    'INPLACE_POWER': operator.pow,
    'INPLACE_MULTIPLY': operator.mul,
    'INPLACE_MATRIX_MULTIPLY': operator.imatmul,
    
    'INPLACE_FLOOR_DIVIDE': operator.floordiv,
    'INPLACE_TRUE_DIVIDE': operator.truediv,
    'INPLACE_MODULO': operator.mod,

    'INPLACE_ADD': operator.add,
    'INPLACE_SUBTRACT': operator.sub,

    'INPLACE_LSHIFT': operator.lshift,
    'INPLACE_RSHIFT': operator.rshift,
    'INPLACE_AND': operator.and_,
    'INPLACE_XOR': operator.xor,
    'INPLACE_OR': operator.or_,
    'DELETE_SUBSCR': operator.delitem,
}

JUMP_OPS = {
    'JUMP_ABSOLUTE',
    'JUMP_FORWARD',
    'JUMP_IF_FALSE_OR_POP',
    'JUMP_IF_TRUE_OR_POP',
    'POP_JUMP_IF_FALSE',
    'POP_JUMP_IF_TRUE',
}


def rot_two(stack):
    # Swaps the two top-most stack items.
    v0 = stack.pop()
    v1 = stack.pop()
    stack.append(v0)
    stack.append(v1)


def rot_three(stack):
    # Lifts second and third stack item one position up, moves top down to position three.
    v0 = stack.pop()
    v1 = stack.pop()
    v2 = stack.pop()
    stack.append(v0)
    stack.append(v2)   
    stack.append(v1)


def rot_four(stack):
    # Lifts second, third and fourth stack items one position up, moves top down to position four.
    v0 = stack.pop()
    v1 = stack.pop()
    v2 = stack.pop()
    v3 = stack.pop()
    stack.append(v0)
    stack.append(v3)
    stack.append(v2) 
    stack.append(v1)


def dup_top(stack):
    stack.append(stack[-1])


def dup_top_two(stack):
    stack.append(stack[-2])
    stack.append(stack[-2])


ROT_OPS = {
    'ROT_TWO': rot_two,
    'ROT_THREE': rot_three,
    'ROT_FOUR': rot_four,  # 3.8+
    
    'DUP_TOP': dup_top,  # 3.2 - 3.11
    'DUP_TOP_TWO': dup_top_two,  # 3.2 - 3.11
}


def _buildCollection(instr: Instruction, stack: list, collectionType: Type):
    v = stack[len(stack) - instr.argval:]
    if collectionType is not list:
        v = collectionType(v)
    for _ in range(instr.argval):
        stack.pop()
    stack.append(v)


def _buildSlice(instr: Instruction, stack: list):
    b = stack.pop()
    a = stack.pop()
    stack.append(slice(a, b))


BUILD_OPS = {
    "BUILD_SLICE":_buildSlice,
    "BUILD_TUPLE": lambda instr, stack: _buildCollection(instr, stack, tuple),
    "BUILD_LIST": lambda instr, stack: _buildCollection(instr, stack, list),
    "BUILD_SET": lambda instr, stack: _buildCollection(instr, stack, set),
}      
