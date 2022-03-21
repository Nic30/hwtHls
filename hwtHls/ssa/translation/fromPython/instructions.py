import operator

from hwt.code import In
from hwt.hdl.operatorDefs import AllOps

# https://docs.python.org/3/library/dis.html
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
    'BINARY_SUBSCR': operator.getitem,
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
    '==': operator.eq,
    '!=': operator.ne,
    '>': operator.gt,
    '>=': operator.ge,
    'in': operator.contains,
    'not in': lambda x, col: not operator.contains(x, col),
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
JUMP_OPS = {
    'JUMP_ABSOLUTE',
    'JUMP_FORWARD',
    'JUMP_IF_FALSE_OR_POP',
    'JUMP_IF_TRUE_OR_POP',
    'POP_JUMP_IF_FALSE',
    'POP_JUMP_IF_TRUE',
}
