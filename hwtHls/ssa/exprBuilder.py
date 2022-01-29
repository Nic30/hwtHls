from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.value import SsaValue
from typing import Optional, Union, List
from hwt.hdl.value import HValue


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

    def __init__(self, block:SsaBasicBlock, possition: Optional[int]=None):
        self.block = block
        self.possition = possition
        # [todo] operator cache

    def _unaryOp(self, o: Union[SsaValue, HValue], operator: OpDefinition) -> SsaValue:
        res = operator._evalFn(o.origin if o.origin is not None else o._dtype.from_py(None))
        if isinstance(o, HValue):
            return res

        instr = SsaInstr(self.block.ctx, res._dtype, operator, [o, ], origin=res)
        self._insertInstr(instr)
        return instr

    def _insertInstr(self, instr):
        pos = self.possition
        b = self.block
        if pos is None:
            b.appendInstruction(instr)
        else:
            b.insertInstruction(pos, instr)
            self.possition += 1

    def unaryOp(self, o: Union[SsaValue, HValue], operator: OpDefinition) -> SsaExprBuilderProxy:
        return self.var(self._unaryOp(o.var, operator))

    def _binaryOp(self, o0: Union[SsaValue, HValue], operator: OpDefinition, o1: Union[SsaValue, HValue]) -> SsaValue:
        is_o0_value = isinstance(o0, HValue)
        is_o1_value = isinstance(o1, HValue)
        res = operator._evalFn(
            o0 if is_o0_value else o0.origin if o0.origin is not None else o0._dtype.from_py(None),
            o1 if is_o1_value else o1.origin if o1.origin is not None else o1._dtype.from_py(None))
        if is_o0_value and is_o1_value:
            return res

        instr = SsaInstr(self.block.ctx, res._dtype, operator, [o0, o1])
        self._insertInstr(instr)
        return instr

    def binaryOp(self, o0: Union[SsaValue, HValue], operator: OpDefinition, o1: SsaValue) -> SsaExprBuilderProxy:
        return self.var(self._binaryOp(o0.var, operator, o1.var))

    def var(self, v: SsaValue):
        return SsaExprBuilderProxy(self, v)

    def insertBlocks(self, branchConditions: List[Optional[SsaValue]]):
        pos = self.possition
        b = self.block
        blocks = [SsaBasicBlock(b.ctx, f"{b.label:s}_br{i}") for i in range(len(branchConditions))]
        
        if pos is None or pos + 1 == len(b.body) and not b.successors.targets:
            # can directly append the blocks
            raise NotImplementedError()
            sequel = None
        else:
            # must spot a sequel block, copy all instructions after this position and move all successors from original block
            sequel = SsaBasicBlock(b.ctx, b.label + "_sequel")
            if pos is not None:
                for instr in b.body[pos + 1:]:
                    instr.block = None
                    sequel.appendInstruction(instr)
                del b.body[pos + 1:]

            for c, t in b.successors.targets:
                t: SsaBasicBlock
                t.predecessors.remove(b)
                sequel.successors.addTarget(c, t)

            b.successors.targets.clear()
            for c, t in zip(branchConditions, blocks):
                b.successors.addTarget(c, t)
                t.successors.addTarget(None, sequel)

        return blocks, sequel
