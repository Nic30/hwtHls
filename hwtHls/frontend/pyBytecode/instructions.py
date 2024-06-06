from dis import Instruction
from io import StringIO
from opcode import opmap, cmp_op, _nb_ops, _intrinsic_1_descs,\
    _intrinsic_2_descs
import operator
import sys
from typing import Type, Tuple, Dict, Callable


# https://docs.python.org/3/library/dis.html
assert (sys.version_info[0], sys.version_info[1]) == (3, 12), (
    "This module is for python3.11 only (3.11 or 3.13 will not work due to bytecode changes)", sys.version_info)


class _NULLMeta(type):

    def __repr__(self):
        return self.__name__


class NULL(metaclass=_NULLMeta):

    def __init__(self):
        raise AssertionError("This class should be used as constant")


POP_TOP = opmap['POP_TOP']
END_FOR = opmap['END_FOR']
PUSH_NULL = opmap['PUSH_NULL']

NOP = opmap['NOP']
UNARY_NEGATIVE = opmap['UNARY_NEGATIVE']
UNARY_NOT = opmap['UNARY_NOT']

UNARY_INVERT = opmap['UNARY_INVERT']

BINARY_SUBSCR = opmap['BINARY_SUBSCR']
BINARY_SLICE = opmap['BINARY_SLICE']
STORE_SLICE = opmap['STORE_SLICE']

GET_LEN = opmap['GET_LEN']  # 3.10+
MATCH_MAPPING = opmap['MATCH_MAPPING']  # 3.10+
MATCH_SEQUENCE = opmap['MATCH_SEQUENCE']  # 3.10+
MATCH_KEYS = opmap['MATCH_KEYS']  # 3.10+

PUSH_EXC_INFO = opmap['PUSH_EXC_INFO']
CHECK_EXC_MATCH = opmap['CHECK_EXC_MATCH']
CHECK_EG_MATCH = opmap['CHECK_EG_MATCH']

WITH_EXCEPT_START = opmap['WITH_EXCEPT_START']  # 3.9+

STORE_SUBSCR = opmap['STORE_SUBSCR']
DELETE_SUBSCR = opmap['DELETE_SUBSCR']

GET_ITER = opmap['GET_ITER']
GET_YIELD_FROM_ITER = opmap['GET_YIELD_FROM_ITER']

LOAD_BUILD_CLASS = opmap['LOAD_BUILD_CLASS']

LOAD_ASSERTION_ERROR = opmap['LOAD_ASSERTION_ERROR']

RETURN_VALUE = opmap['RETURN_VALUE']
RETURN_CONST = opmap['RETURN_CONST']

YIELD_VALUE = opmap['YIELD_VALUE']

POP_EXCEPT = opmap['POP_EXCEPT']

UNPACK_SEQUENCE = opmap['UNPACK_SEQUENCE']
FOR_ITER = opmap['FOR_ITER']
UNPACK_EX = opmap['UNPACK_EX']
STORE_ATTR = opmap['STORE_ATTR']
DELETE_ATTR = opmap['DELETE_ATTR']

SWAP = opmap['SWAP']
LOAD_CONST = opmap['LOAD_CONST']

BUILD_TUPLE = opmap['BUILD_TUPLE']
BUILD_LIST = opmap['BUILD_LIST']
BUILD_SET = opmap['BUILD_SET']
BUILD_MAP = opmap['BUILD_MAP']
LOAD_ATTR = opmap['LOAD_ATTR']
COMPARE_OP = opmap['COMPARE_OP']

JUMP_FORWARD = opmap['JUMP_FORWARD']
JUMP_BACKWARD = opmap['JUMP_BACKWARD']
JUMP_BACKWARD_NO_INTERRUPT = opmap['JUMP_BACKWARD_NO_INTERRUPT']
POP_JUMP_IF_TRUE = opmap['POP_JUMP_IF_TRUE']
POP_JUMP_IF_FALSE = opmap['POP_JUMP_IF_FALSE']
POP_JUMP_IF_NOT_NONE = opmap['POP_JUMP_IF_NOT_NONE']
POP_JUMP_IF_NONE = opmap['POP_JUMP_IF_NONE']


LOAD_GLOBAL = opmap['LOAD_GLOBAL']
IS_OP = opmap['IS_OP']
CONTAINS_OP = opmap['CONTAINS_OP']
RERAISE = opmap['RERAISE']
COPY = opmap['COPY']
BINARY_OP = opmap['BINARY_OP']
SEND = opmap['SEND']

LOAD_FAST = opmap['LOAD_FAST']
LOAD_FAST_CHECK = opmap['LOAD_FAST_CHECK']
LOAD_FAST_AND_CLEAR = opmap['LOAD_FAST_AND_CLEAR']
STORE_FAST = opmap['STORE_FAST']
DELETE_FAST = opmap['DELETE_FAST']
RAISE_VARARGS = opmap['RAISE_VARARGS']

MAKE_FUNCTION = opmap['MAKE_FUNCTION']
BUILD_SLICE = opmap['BUILD_SLICE']
JUMP_BACKWARD_NO_INTERRUPT = opmap['JUMP_BACKWARD_NO_INTERRUPT']
MAKE_CELL = opmap['MAKE_CELL']
LOAD_CLOSURE = opmap['LOAD_CLOSURE']
LOAD_DEREF = opmap['LOAD_DEREF']
LOAD_FROM_DICT_OR_DEREF = opmap['LOAD_FROM_DICT_OR_DEREF']
STORE_DEREF = opmap['STORE_DEREF']
DELETE_DEREF = opmap["DELETE_DEREF"]
JUMP_BACKWARD = opmap['JUMP_BACKWARD']

CALL_FUNCTION_EX = opmap['CALL_FUNCTION_EX']
EXTENDED_ARG = opmap['EXTENDED_ARG']

LIST_APPEND = opmap['LIST_APPEND']
SET_ADD = opmap['SET_ADD']
MAP_ADD = opmap['MAP_ADD']
COPY_FREE_VARS = opmap['COPY_FREE_VARS']

RESUME = opmap['RESUME']
MATCH_CLASS = opmap['MATCH_CLASS']

FORMAT_VALUE = opmap['FORMAT_VALUE']
BUILD_CONST_KEY_MAP = opmap["BUILD_CONST_KEY_MAP"]
BUILD_STRING = opmap['BUILD_STRING']

LOAD_METHOD = opmap['LOAD_METHOD']

LIST_EXTEND = opmap['LIST_EXTEND']
SET_UPDATE = opmap['SET_UPDATE']
DICT_MERGE = opmap['DICT_MERGE']
DICT_UPDATE = opmap['DICT_UPDATE']

CALL = opmap['CALL']
KW_NAMES = opmap['KW_NAMES']

UN_OPS = {
    UNARY_NEGATIVE: operator.neg,
    UNARY_NOT: operator.not_,
    UNARY_INVERT: operator.invert,
}


def _binOpOpc(descrTuple: Tuple[str, str]) -> int:
    return _nb_ops.index(descrTuple)


BINARY_OPS: Dict[int, Tuple[bool, Callable[object, object]]] = {
    _binOpOpc(("NB_ADD", "+")): (False, operator.add),
    _binOpOpc(("NB_AND", "&")): (False, operator.and_),
    _binOpOpc(("NB_FLOOR_DIVIDE", "//")): (False, operator.floordiv),
    _binOpOpc(("NB_LSHIFT", "<<")): (False, operator.lshift),
    _binOpOpc(("NB_MATRIX_MULTIPLY", "@")): (False, operator.matmul),
    _binOpOpc(("NB_MULTIPLY", "*")): (False, operator.mul),
    _binOpOpc(("NB_REMAINDER", "%")): (False, operator.mod),
    _binOpOpc(("NB_OR", "|")): (False, operator.or_),
    _binOpOpc(("NB_POWER", "**")): (False, operator.pow),
    _binOpOpc(("NB_RSHIFT", ">>")): (False, operator.rshift),
    _binOpOpc(("NB_SUBTRACT", "-")): (False, operator.sub),
    _binOpOpc(("NB_TRUE_DIVIDE", "/")): (False, operator.truediv),
    _binOpOpc(("NB_XOR", "^")): (False, operator.xor),

    _binOpOpc(("NB_INPLACE_ADD", "+=")): (True, operator.add),
    _binOpOpc(("NB_INPLACE_AND", "&=")): (True, operator.and_),
    _binOpOpc(("NB_INPLACE_FLOOR_DIVIDE", "//=")): (True, operator.floordiv),
    _binOpOpc(("NB_INPLACE_LSHIFT", "<<=")): (True, operator.lshift),
    _binOpOpc(("NB_INPLACE_MATRIX_MULTIPLY", "@=")): (True, operator.matmul),
    _binOpOpc(("NB_INPLACE_MULTIPLY", "*=")): (True, operator.mul),
    _binOpOpc(("NB_INPLACE_REMAINDER", "%=")): (True, operator.mod),
    _binOpOpc(("NB_INPLACE_OR", "|=")): (True, operator.or_),
    _binOpOpc(("NB_INPLACE_POWER", "**=")): (True, operator.pow),
    _binOpOpc(("NB_INPLACE_RSHIFT", ">>=")): (True, operator.rshift),
    _binOpOpc(("NB_INPLACE_SUBTRACT", "-=")): (True, operator.sub),
    _binOpOpc(("NB_INPLACE_TRUE_DIVIDE", "/=")): (True, operator.truediv),
    _binOpOpc(("NB_INPLACE_XOR", "^=")): (True, operator.xor),

    # IS_OP: operator.is_, # "is" operator has inversion flag, we have to use a custom evaluator fn.
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


def _dictMerge(dst: dict, src: dict):
    for k, v in src.items():
        assert k not in dst, k
        dst[k] = v


INPLACE_UPDATE_OPS = {
    SET_ADD: set.add,
    LIST_APPEND: list.append,
    # MAP_ADD:
    LIST_EXTEND: list.extend,
    SET_UPDATE: set.update,
    DICT_MERGE: _dictMerge,
    DICT_UPDATE: dict.update,
}

JUMPS_NON_OPTIONAL = (
    JUMP_FORWARD,
    JUMP_BACKWARD,
    JUMP_BACKWARD_NO_INTERRUPT,
    RETURN_VALUE,
    RETURN_CONST,
    RERAISE,
    RAISE_VARARGS
)

JUMPS_CONDITIONAL = (
    POP_JUMP_IF_NOT_NONE,
    POP_JUMP_IF_NONE,
    POP_JUMP_IF_FALSE,
    POP_JUMP_IF_TRUE,
)

JUMPS_CONDITIONAL_ANY = (
    *JUMPS_CONDITIONAL,
    FOR_ITER,
)

JUMP_OPS = {
    JUMP_FORWARD: None,
    JUMP_BACKWARD: None,
    JUMP_BACKWARD_NO_INTERRUPT: None,
    POP_JUMP_IF_NOT_NONE: lambda x: x is not None,
    POP_JUMP_IF_NONE: lambda x: x is None,
    POP_JUMP_IF_FALSE: False,
    POP_JUMP_IF_TRUE: True,
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


def _BUILD_MAP(instr: Instruction, stack: list):
    """
    Pushes a new dictionary object onto the stack. Pops 2 * count items so that the dictionary holds count entries: {..., TOS3: TOS2, TOS1: TOS}.

    Changed in version 3.5: The dictionary is created from stack items instead of creating an empty dictionary pre-sized to hold count items.
    """
    d = {}
    for _ in range(instr.argval):
        v = stack.pop()
        k = stack.pop()
        d[k] = v
    stack.append(d)


def _BUILD_CONST_KEY_MAP(instr: Instruction, stack: list):
    """
    The version of BUILD_MAP specialized for constant keys. Pops the top element on the stack which contains a tuple of keys, then starting from TOS1, pops count values to form values in the built dictionary.

    New in version 3.6.
    """
    keys = stack.pop()
    values = stack[-instr.argval:]
    del stack[-instr.argval:]
    stack.append({k: v for k, v in zip(keys, values)})


def _BUILD_STRING(instr: Instruction, stack: list):
    """
    Concatenates count strings from the stack and pushes the resulting string onto the stack.

    New in version 3.6.
    """
    parts = stack[-instr.argval:]
    del stack[-instr.argval:]
    buf = StringIO()
    for p in parts:
        if not isinstance(p, str):
            p = str(p)
        buf.write(p)
    stack.append(buf.getvalue())


BUILD_OPS = {
    BUILD_SLICE: _buildSlice,
    BUILD_TUPLE: lambda instr, stack: _buildCollection(instr, stack, tuple),
    BUILD_LIST: lambda instr, stack: _buildCollection(instr, stack, list),
    BUILD_SET: lambda instr, stack: _buildCollection(instr, stack, set),
    BUILD_CONST_KEY_MAP: BUILD_CONST_KEY_MAP,
    BUILD_STRING: _BUILD_STRING,
    BUILD_MAP: _BUILD_MAP,
    BUILD_CONST_KEY_MAP: _BUILD_CONST_KEY_MAP,
}

INTRINSIC_1_INVALID =           _intrinsic_1_descs.index("INTRINSIC_1_INVALID")
INTRINSIC_PRINT =               _intrinsic_1_descs.index("INTRINSIC_PRINT")
INTRINSIC_IMPORT_STAR =         _intrinsic_1_descs.index("INTRINSIC_IMPORT_STAR")
INTRINSIC_STOPITERATION_ERROR = _intrinsic_1_descs.index("INTRINSIC_STOPITERATION_ERROR")
INTRINSIC_ASYNC_GEN_WRAP =      _intrinsic_1_descs.index("INTRINSIC_ASYNC_GEN_WRAP")
INTRINSIC_UNARY_POSITIVE =      _intrinsic_1_descs.index("INTRINSIC_UNARY_POSITIVE")
INTRINSIC_LIST_TO_TUPLE =       _intrinsic_1_descs.index("INTRINSIC_LIST_TO_TUPLE")
INTRINSIC_TYPEVAR =             _intrinsic_1_descs.index("INTRINSIC_TYPEVAR")
INTRINSIC_PARAMSPEC =           _intrinsic_1_descs.index("INTRINSIC_PARAMSPEC")
INTRINSIC_TYPEVARTUPLE =        _intrinsic_1_descs.index("INTRINSIC_TYPEVARTUPLE")
INTRINSIC_SUBSCRIPT_GENERIC =   _intrinsic_1_descs.index("INTRINSIC_SUBSCRIPT_GENERIC")
INTRINSIC_TYPEALIAS =           _intrinsic_1_descs.index("INTRINSIC_TYPEALIAS")

INTRINSIC_2_INVALID =                _intrinsic_2_descs.index("INTRINSIC_2_INVALID")
INTRINSIC_PREP_RERAISE_STAR =        _intrinsic_2_descs.index("INTRINSIC_PREP_RERAISE_STAR")
INTRINSIC_TYPEVAR_WITH_BOUND =       _intrinsic_2_descs.index("INTRINSIC_TYPEVAR_WITH_BOUND")
INTRINSIC_TYPEVAR_WITH_CONSTRAINTS = _intrinsic_2_descs.index("INTRINSIC_TYPEVAR_WITH_CONSTRAINTS")
INTRINSIC_SET_FUNCTION_TYPE_PARAMS = _intrinsic_2_descs.index("INTRINSIC_SET_FUNCTION_TYPE_PARAMS")

