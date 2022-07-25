import operator
from dis import Instruction
from typing import Type
from opcode import opmap, cmp_op

# https://docs.python.org/3/library/dis.html
NOP = opmap['NOP']
POP_TOP = opmap['POP_TOP']
LOAD_DEREF = opmap['LOAD_DEREF']      
LOAD_ATTR = opmap['LOAD_ATTR']       
LOAD_FAST = opmap['LOAD_FAST']       
LOAD_CONST = opmap['LOAD_CONST']      
LOAD_GLOBAL = opmap['LOAD_GLOBAL']     
LOAD_METHOD = opmap['LOAD_METHOD']     
LOAD_CLOSURE = opmap['LOAD_CLOSURE']
DELETE_FAST = opmap['DELETE_FAST']
DELETE_DEREF = opmap["DELETE_DEREF"]   
STORE_ATTR = opmap['STORE_ATTR']      
STORE_FAST = opmap['STORE_FAST']      
STORE_DEREF = opmap['STORE_DEREF']     
CALL_METHOD = opmap['CALL_METHOD']     
CALL_FUNCTION = opmap['CALL_FUNCTION']   
CALL_FUNCTION_KW = opmap['CALL_FUNCTION_KW']
CALL_FUNCTION_EX = opmap['CALL_FUNCTION_EX']

COMPARE_OP = opmap['COMPARE_OP']      
GET_ITER = opmap['GET_ITER']        
EXTENDED_ARG = opmap['EXTENDED_ARG']    
UNPACK_SEQUENCE = opmap['UNPACK_SEQUENCE'] 
MAKE_FUNCTION = opmap['MAKE_FUNCTION']   
STORE_SUBSCR = opmap['STORE_SUBSCR']    
FOR_ITER = opmap['FOR_ITER']
UNARY_POSITIVE = opmap['UNARY_POSITIVE']
UNARY_NEGATIVE = opmap['UNARY_NEGATIVE']
UNARY_NOT = opmap['UNARY_NOT'     ]
UNARY_INVERT = opmap['UNARY_INVERT'  ]

BINARY_POWER = opmap['BINARY_POWER']
BINARY_MULTIPLY = opmap['BINARY_MULTIPLY']
BINARY_MATRIX_MULTIPLY = opmap['BINARY_MATRIX_MULTIPLY']
BINARY_FLOOR_DIVIDE = opmap['BINARY_FLOOR_DIVIDE']
BINARY_TRUE_DIVIDE = opmap['BINARY_TRUE_DIVIDE']

BINARY_MODULO = opmap['BINARY_MODULO']
BINARY_ADD = opmap['BINARY_ADD']
BINARY_SUBTRACT = opmap['BINARY_SUBTRACT']
BINARY_SUBSCR = opmap['BINARY_SUBSCR']

BINARY_LSHIFT = opmap['BINARY_LSHIFT']
BINARY_RSHIFT = opmap['BINARY_RSHIFT']
BINARY_AND = opmap['BINARY_AND']
BINARY_XOR = opmap['BINARY_XOR']
BINARY_OR = opmap['BINARY_OR']

IS_OP = opmap['IS_OP']
CONTAINS_OP = opmap['CONTAINS_OP']

INPLACE_POWER = opmap['INPLACE_POWER']
INPLACE_MULTIPLY = opmap['INPLACE_MULTIPLY']
INPLACE_MATRIX_MULTIPLY = opmap['INPLACE_MATRIX_MULTIPLY']

INPLACE_FLOOR_DIVIDE = opmap['INPLACE_FLOOR_DIVIDE']
INPLACE_TRUE_DIVIDE = opmap['INPLACE_TRUE_DIVIDE']
INPLACE_MODULO = opmap['INPLACE_MODULO']

INPLACE_ADD = opmap['INPLACE_ADD']
INPLACE_SUBTRACT = opmap['INPLACE_SUBTRACT']

INPLACE_LSHIFT = opmap['INPLACE_LSHIFT']
INPLACE_RSHIFT = opmap['INPLACE_RSHIFT']
INPLACE_AND = opmap['INPLACE_AND']
INPLACE_XOR = opmap['INPLACE_XOR']
INPLACE_OR = opmap['INPLACE_OR']
DELETE_SUBSCR = opmap['DELETE_SUBSCR']

JUMP_ABSOLUTE = opmap['JUMP_ABSOLUTE']
JUMP_FORWARD = opmap['JUMP_FORWARD']
JUMP_IF_FALSE_OR_POP = opmap['JUMP_IF_FALSE_OR_POP']
JUMP_IF_TRUE_OR_POP = opmap['JUMP_IF_TRUE_OR_POP']
POP_JUMP_IF_FALSE = opmap['POP_JUMP_IF_FALSE']
POP_JUMP_IF_TRUE = opmap['POP_JUMP_IF_TRUE']
RETURN_VALUE = opmap['RETURN_VALUE']

ROT_TWO = opmap['ROT_TWO']
ROT_THREE = opmap['ROT_THREE']
ROT_FOUR = opmap['ROT_FOUR']  # 3.8+

DUP_TOP = opmap.get('DUP_TOP', -1)  # 3.2 - 3.11
DUP_TOP_TWO = opmap.get('DUP_TOP_TWO', -1)  # 3.2 - 3.11

BUILD_SLICE = opmap['BUILD_SLICE']
BUILD_TUPLE = opmap['BUILD_TUPLE']
BUILD_LIST = opmap['BUILD_LIST']
BUILD_SET = opmap['BUILD_SET']
FORMAT_VALUE = opmap['FORMAT_VALUE']
BUILD_STRING = opmap['BUILD_STRING']

UN_OPS = {
    UNARY_POSITIVE: operator.pos,
    UNARY_NEGATIVE: operator.neg,
    UNARY_NOT: operator.not_,
    UNARY_INVERT: operator.invert,
}

BIN_OPS = {
    BINARY_POWER: operator.pow,
    BINARY_MULTIPLY: operator.mul,
    BINARY_MATRIX_MULTIPLY: operator.matmul,
    BINARY_FLOOR_DIVIDE: operator.floordiv,
    BINARY_TRUE_DIVIDE: operator.truediv,

    BINARY_MODULO: operator.mod,
    BINARY_ADD: operator.add,
    BINARY_SUBTRACT: operator.sub,
    BINARY_SUBSCR: operator.getitem,

    BINARY_LSHIFT: operator.lshift,
    BINARY_RSHIFT: operator.rshift,
    BINARY_AND: operator.and_,
    BINARY_XOR: operator.xor,
    BINARY_OR: operator.or_,
    IS_OP: operator.is_,
    CONTAINS_OP: operator.contains,
}

CMP_OP_LT = cmp_op.index('<')
CMP_OP_LE = cmp_op.index('<=')
CMP_OP_EQ = cmp_op.index('==')
CMP_OP_NE = cmp_op.index('!=')
CMP_OP_GT = cmp_op.index('>')
CMP_OP_GE = cmp_op.index('>=')

CMP_OPS = {
    CMP_OP_LT: operator.lt,
    CMP_OP_LE: operator.le,
    CMP_OP_EQ: operator.eq,
    CMP_OP_NE: operator.ne,
    CMP_OP_GT: operator.gt,
    CMP_OP_GE: operator.ge,
    # 'in': operator.contains,
    # 'not in': lambda x, col: not operator.contains(x, col),
}

INPLACE_BIN_OPS = {
    INPLACE_POWER: operator.pow,
    INPLACE_MULTIPLY: operator.mul,
    INPLACE_MATRIX_MULTIPLY: operator.imatmul,
    
    INPLACE_FLOOR_DIVIDE: operator.floordiv,
    INPLACE_TRUE_DIVIDE: operator.truediv,
    INPLACE_MODULO: operator.mod,

    INPLACE_ADD: operator.add,
    INPLACE_SUBTRACT: operator.sub,

    INPLACE_LSHIFT: operator.lshift,
    INPLACE_RSHIFT: operator.rshift,
    INPLACE_AND: operator.and_,
    INPLACE_XOR: operator.xor,
    INPLACE_OR: operator.or_,
    DELETE_SUBSCR: operator.delitem,
}

JUMP_OPS = {
    JUMP_ABSOLUTE,
    JUMP_FORWARD,
    JUMP_IF_FALSE_OR_POP,
    JUMP_IF_TRUE_OR_POP,
    POP_JUMP_IF_FALSE,
    POP_JUMP_IF_TRUE,
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
    ROT_TWO: rot_two,
    ROT_THREE: rot_three,
    ROT_FOUR: rot_four,  # 3.8+
    
    DUP_TOP: dup_top,  # 3.2 - 3.11
    DUP_TOP_TWO: dup_top_two,  # 3.2 - 3.11
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
    BUILD_SLICE: _buildSlice,
    BUILD_TUPLE: lambda instr, stack: _buildCollection(instr, stack, tuple),
    BUILD_LIST: lambda instr, stack: _buildCollection(instr, stack, list),
    BUILD_SET: lambda instr, stack: _buildCollection(instr, stack, set),
}      
