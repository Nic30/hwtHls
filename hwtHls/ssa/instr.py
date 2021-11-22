from typing import List, Tuple, Optional, Union

from hwt.hdl.operatorDefs import OpDefinition
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.value import SsaValue


class SsaInstrBranch():

    def __init__(self, parent: "SsaBasicBlock"):
        self.parent = parent
        self.targets: List[Tuple[Optional[SsaValue], "SsaBasicBlock"]] = []

    def addTarget(self, cond: Optional[SsaValue], target: "SsaBasicBlock"):
        self.targets.append((cond, target))
        assert self.parent not in target.predecessors
        target.predecessors.append(self.parent)
        if cond is not None:
            cond.users.append(self)

    def replaceTargetBlock(self, orig_block:"SsaBasicBlock", new_block:"SsaBasicBlock"):
        for i, (c, b) in enumerate(self.targets):
            if b is orig_block:
                self.targets[i] = (c, new_block)

    def __len__(self):
        return len(self.targets)

    def iter_blocks(self):
        for (_, t) in self.targets:
            yield t

    def __repr__(self):
        targets = [(None if c is None else c._name, b.label) for c, b in self.targets]
        return f"<{self.__class__.__name__} {targets}>"


class OperatorAssign(OpDefinition):
    pass


OP_ASSIGN = OperatorAssign(lambda x: x, allowsAssignTo=True)
OP_ASSIGN.id = "ASSIGN"


class SsaInstr(SsaValue):

    def __init__(self,
                 ctx: SsaContext,
                 dtype: HdlType,
                 operator: Union[OpDefinition],
                 operands: Tuple[Union[SsaValue, HValue], ...],
                 name: str=None,
                 origin=None):
        super(SsaInstr, self).__init__(ctx, dtype, name, origin)
        self.block: Optional["SsaBasicBlock"] = None
        self.operator = operator
        self.operands = operands
        assert isinstance(operands, (tuple, list)), operands
        for op in operands:
            if isinstance(op, SsaValue):
                op.users.append(self)
            else:
                assert isinstance(op, HValue), op

    def iterInputs(self):
        return self.operands

    def replaceInput(self, orig_expr: SsaValue, new_expr: Union[SsaValue, HValue]):
        assert isinstance(new_expr, (SsaValue, HValue)), new_expr
        assert orig_expr in self.operands
        self.operands = tuple(
            new_expr if o is orig_expr else o
            for o in self.operands
        )
        orig_expr.users.remove(self)
        if isinstance(new_expr, SsaValue):
            new_expr.users.append(self)

    def __repr__(self):
        _src = ", ".join(s._name if isinstance(s, SsaInstr) else repr(s) for s in self.operands)
        if self.operator is OP_ASSIGN:
            return f"{self._name:s} = {_src:s}"
        else:
            return f"{self._name:s} = {self.operator.id:s} {_src:s}"

