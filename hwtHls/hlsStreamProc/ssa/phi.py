from typing import Tuple, Union, List

from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.tmpVariable import TmpVariable


class SsaPhi():
    """
    A function from SSA normal form which select the value of variable based on prevous basic block
    """

    def __init__(self, parent: "SsaBasicBlock", dst: TmpVariable,
                 *operands: Tuple[Union[RtlSignalBase, HValue, TmpVariable, 'SsaPhi'], "SsaBasicBlock"]):
        self.block = parent
        assert isinstance(dst, TmpVariable)
        self.dst = dst
        assert isinstance(dst, RtlSignalBase), dst
        self.operands = operands
        self.block.phis.append(self)
        self.users: UniqList[SsaPhi, "SsaInstrBranch", "SsaInstr", "HlsStreamProcWrite"] = UniqList()
        for (_, src_block) in operands:
            assert src_block in parent.predecessors

    def replaceUseBy(self, v: "SsaPhi"):
        for u in self.users:
            u.replaceInput(self, v)

    def appendOperand(self,
                      val: Union["SsaPhi", RtlSignalBase, HValue],
                      predecessor_block: "SsaBasicBlock"):
        new_op = (val, predecessor_block)
        if new_op in self.operands:
            return
        self.operands = (*self.operands, new_op)
        if isinstance(val, SsaPhi):
            val.users.append(self)

    def replacePredecessorBlockByMany(self,
                                      predecessor_block: "SsaBasicBlock",
                                      new_predecessor_blocks: List["SsaBasicBlock"]):
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
        return f"<{self.__class__.__name__:s} {self.dst}>"
