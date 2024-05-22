from collections import namedtuple
from typing import List, Tuple, Optional, Union

from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.const import HConst
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.value import SsaValue
from hwtHls.ssa.codeLocation import CodeLocation


class ConditionBlockTuple(namedtuple('ConditionBlockTuple', ['condition', 'dstBlock', 'meta'])):

    def __new__(cls, condition: Optional[SsaValue], dstBlock: "SsaBasicBlock", meta):
        return super(ConditionBlockTuple, cls).__new__(cls, condition, dstBlock, meta)


class SsaInstrBranch():

    def __init__(self, parent: "SsaBasicBlock"):
        self.parent = parent
        self.targets: List[ConditionBlockTuple] = []
        self.codeLocation: Optional[CodeLocation] = None

    def addTarget(self, cond: Optional[SsaValue], target: "SsaBasicBlock", meta=None):
        t = ConditionBlockTuple(cond, target, meta)
        self.targets.append(t)
        assert self.parent not in target.predecessors, (self.parent, target, target.predecessors)
        target.predecessors.append(self.parent)
        if cond is not None:
            cond.users.append(self)
        return t

    def replaceInput(self, orig_expr: SsaValue, new_expr: Union[SsaValue, HConst]):
        assert isinstance(new_expr, (SsaValue, HConst)), (self, orig_expr, new_expr)
        assert self in orig_expr.users
        self.targets = [
            ConditionBlockTuple(new_expr if o is orig_expr else o, t, meta)
            for o, t, meta in self.targets
        ]
        orig_expr.users.remove(self)
        if isinstance(new_expr, SsaValue):
            new_expr.users.append(self)

    def replaceTargetBlock(self, orig_block:"SsaBasicBlock", new_block:"SsaBasicBlock"):
        for i, (c, b, meta) in enumerate(self.targets):
            if b is orig_block:
                self.targets[i] = ConditionBlockTuple(c, new_block, meta)

    def __len__(self):
        return len(self.targets)

    def iterBlocks(self):
        for b in self.targets:
            yield b.dstBlock

    def __repr__(self):
        targets = [(None if c is None else c._name, b.label) for c, b, _ in self.targets]
        return f"<{self.__class__.__name__} {targets}>"


OP_ASSIGN = HOperatorDef(lambda x: x, allowsAssignTo=True, idStr="ASSIGN")


class SsaInstr(SsaValue):

    def __init__(self,
                 ctx: SsaContext,
                 dtype: HdlType,
                 operator: HOperatorDef,
                 operands: Tuple[Union[SsaValue, HConst], ...],
                 name: str=None,
                 origin=None):
        super(SsaInstr, self).__init__(ctx, dtype, name, origin)
        self.block: Optional["SsaBasicBlock"] = None
        self.operator = operator
        self.operands = operands
        self.codeLocation: Optional[CodeLocation] = None
        assert isinstance(operands, (tuple, list)), operands
        for op in operands:
            if isinstance(op, SsaValue):
                assert op.block is not None, (op, "Must not construct instruction with operands which are not in SSA")
                op.users.append(self)
            else:
                assert isinstance(op, HConst), op
        self.metadata: Optional[List["_PyBytecodePragma"]] = None

    def iterInputs(self):
        return self.operands

    def replaceInput(self, orig_expr: SsaValue, new_expr: Union[SsaValue, HConst]):
        assert isinstance(new_expr, (SsaValue, HConst)), (self, orig_expr, new_expr)
        assert orig_expr in self.operands
        self.operands = tuple(
            new_expr if o is orig_expr else o
            for o in self.operands
        )
        orig_expr.users.remove(self)
        if isinstance(new_expr, SsaValue):
            new_expr.users.append(self)

    def replaceBy(self, replacement: Union[SsaValue, HConst]):
        assert replacement._dtype.bit_length() == self._dtype.bit_length(), ("Must have same type", self, replacement, self._dtype, replacement._dtype)
        for u in tuple(self.users):
            u.replaceInput(self, replacement)

    def __repr__(self):
        _src = ", ".join(s._name if isinstance(s, SsaInstr) else repr(s) for s in self.operands)
        if self.operator is OP_ASSIGN:
            return f"{self._name:s} = {_src:s}"
        else:
            return f"{self._name:s} = {self.operator.id:s} {_src:s}"

