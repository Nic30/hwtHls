from typing import Tuple, Union, List, Optional

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.value import SsaValue

class SsaPhi(SsaInstr):
    """
    A function from SSA normal form which select the value of variable based on prevous basic block
    """

    def __init__(self,
                 ctx: SsaContext, dtype: HdlType, name:Optional[str]=None, origin=None):
        super(SsaPhi, self).__init__(ctx, dtype, AllOps.TERNARY, (), name=name, origin=origin)
        self.block: Optional["SsaBasicBlock"] = None
        self.operands:Tuple[Union[HValue, SsaValue], "SsaBasicBlock"] = ()
        self.replacedBy: Optional[Union[SsaValue, HValue]] = None

    def replaceInput(self, orig_expr: SsaValue, new_expr: Union[SsaValue, HValue]):
        if isinstance(new_expr, SsaValue):
            assert new_expr.block is not None, (self, new_expr, "Operand must be somewhere in SSA first")
            new_expr.users.append(self)
        
        somethingReplaced = False
        ops = []
        for (c, b) in self.operands:
            if c is orig_expr:
                somethingReplaced = True
                c = new_expr
            ops.append((c, b))

        assert somethingReplaced, (self, orig_expr, new_expr)
        self.operands = tuple(ops)

    def replaceUseBy(self, v: Union[SsaValue, RtlSignalBase, HValue]):
        if isinstance(v, SsaValue):
            assert v.block is not None, (self, v, "Operand must be somewhere in SSA first")
        for u in tuple(self.users):
            u.replaceInput(self, v)
        self.replacedBy = v
        self.users.clear()
        

    def appendOperand(self,
                      val: Union[SsaValue, RtlSignalBase, HValue],
                      predecessor_block: "SsaBasicBlock"):
        assert self.replacedBy is None
        new_op = (val, predecessor_block)
        if new_op in self.operands:
            return
        if isinstance(val, SsaValue):
            assert val.block is not None
            val.users.append(self)
        self.operands = (*self.operands, new_op)


    def replacePredecessorBlockByMany(self,
                                      predecessor_block: "SsaBasicBlock",
                                      new_predecessor_blocks: List["SsaBasicBlock"]):
        assert self.replacedBy is None
        operands = []
        for (val, b) in self.operands:
            if b is predecessor_block:
                for new_b in new_predecessor_blocks:
                    assert new_b in self.block.predecessors, (new_b, self.block.predecessors)
                    new_op = (val, new_b)
                    if new_op not in operands:
                        operands.append(new_op)
            else:
                new_op = (val, b)
                assert b in self.block.predecessors, (b, self.block.predecessors)
                if new_op not in operands:
                    operands.append(new_op)

        self.operands = tuple(operands)

    def __repr__(self):
        origin = self.origin
        return f"<{self.__class__.__name__:s} {self._name} {origin.name + ' ' if origin is not None else ''}{'deleted' if self.replacedBy is not None else ''}>"
