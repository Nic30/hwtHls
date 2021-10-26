from typing import List

from hwtHls.hlsStreamProc.ssa.instr import SsaInstrBranch, SsaInstr
from hwtHls.hlsStreamProc.ssa.phi import SsaPhi
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead, HlsStreamProcWrite


class SsaBasicBlock():
    """
    Basic Block from Static Single Assignment (SSA) normal form of code.

    :ivar label: label for debug purposes
    :ivar predecessors: list of block from where the control flow can go to this block
    :ivar phis: list of phi functions which are selecting a value for a variable based on predecessor block
    :ivar body: statements of this block
    :ivar successors: an object to keep track of jumps from this block
    :ivar origns: list of objects which contributed to existence of this object
    """

    def __init__(self, label:str):
        self.label = label
        self.predecessors: List[SsaBasicBlock] = []
        self.phis: List[SsaPhi] = []
        self.body: List[SsaInstr, HlsStreamProcRead, HlsStreamProcWrite] = []
        self.successors = SsaInstrBranch(self)
        self.origins = []

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.label:s}>"
