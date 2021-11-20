from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.value import SsaValue


class SsaExprBuilderProxy():

    def __init__(self, parent:"SsaExprBuilder", var: SsaValue):
        self.parent = parent
        self.var = var

    def _normalize(self, other):
        if not isinstance(other, SsaValue):
            raise NotImplementedError()
        return other

    def __add__(self, other):
        return self.parent.binaryOp(self, AllOps.ADD, self._normalize(other))

    def __sub__(self, other):
        return self.parent.binaryOp(self, AllOps.SUB, self._normalize(other))

    def __mul__(self, other):
        return self.parent.binaryOp(self, AllOps.MUL, self._normalize(other))

    def __floordiv__(self, other):
        return self.parent.binaryOp(self, AllOps.DIV, self._normalize(other))

    def __and__(self, other):
        return self.parent.binaryOp(self, AllOps.AND, self._normalize(other))

    def __or__(self, other):
        return self.parent.binaryOp(self, AllOps.OR, self._normalize(other))

    def __xor__(self, other):
        return self.parent.binaryOp(self, AllOps.XOR, self._normalize(other))

    def __eq__(self, other):
        return self.parent.binaryOp(self, AllOps.EQ, self._normalize(other))

    def __ne__(self, other):
        return self.parent.binaryOp(self, AllOps.NE, self._normalize(other))

    def __gt__(self, other):
        return self.parent.binaryOp(self, AllOps.GT, self._normalize(other))

    def __ge__(self, other):
        return self.parent.binaryOp(self, AllOps.GE, self._normalize(other))

    def __lt__(self, other):
        return self.parent.binaryOp(self, AllOps.LT, self._normalize(other))

    def __le__(self, other):
        return self.parent.binaryOp(self, AllOps.LE, self._normalize(other))

    def __invert__(self):
        return self.parent.unaryOp(self, AllOps.NOT)

    def __neg__(self):
        return self.parent.binaryOp(self, AllOps.MINUS_UNARY)

    def __getitem__(self, key):
        return self.parent.binaryOp(self, AllOps.INDEX, self._normalize(key))


class SsaExprBuilder():

    def __init__(self, block:SsaBasicBlock):
        self.block = block
        # [todo] operator cache

    def _unaryOp(self, o: SsaValue, operator: OpDefinition) -> SsaValue:
        res = operator._evalFn(o.origin)
        instr = SsaInstr(self.block.ctx, res._dtype, operator, [o, ], origin=res)
        self.block.body.append(instr)
        return instr

    def unaryOp(self, o: SsaValue, operator: OpDefinition) -> SsaExprBuilderProxy:
        return self.var(self._unaryOp(o.var, operator))

    def _binaryOp(self, o0: SsaValue, operator: OpDefinition, o1: SsaValue) -> SsaValue:
        res = operator._evalFn(o0.origin, o1.origin)
        instr = SsaInstr(self.block.ctx, res._dtype, operator, [o0, o1])
        self.block.body.append(instr)
        return instr

    def binaryOp(self, o0: SsaValue, operator: OpDefinition, o1: SsaValue) -> SsaExprBuilderProxy:
        return self.var(self._binaryOp(o0.var, operator, o1.var))

    def var(self, v: SsaValue):
        return SsaExprBuilderProxy(self, v)

