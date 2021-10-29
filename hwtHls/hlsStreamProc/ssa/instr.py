from typing import List, Tuple, Optional, Union

from hwt.hdl.operatorDefs import OpDefinition
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.hlsStreamProc.ssa.phi import SsaPhi
from hwtHls.tmpVariable import HlsTmpVariable


class SsaInstrBranch():

    def __init__(self, parent: "SsaBasicBlock"):
        self.parent = parent
        self.targets: List[Tuple[Optional[RtlSignal], "SsaBasicBlock"]] = []

    def addTarget(self, cond: Optional[RtlSignal], target: "SsaBasicBlock"):
        self.targets.append((cond, target))
        target.predecessors.append(self.parent)
        if isinstance(cond, SsaPhi):
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
        return f"<{self.__class__.__name__} {self.targets}>"


ValOrVal = Union[HlsTmpVariable, RtlSignal, HValue, SsaPhi]


class SsaInstr():

    def __init__(self,
                 dst: Union[RtlSignal, HlsTmpVariable],
                 src: Union[ValOrVal,
                            Tuple[OpDefinition, List[ValOrVal]]
                ]):
        assert isinstance(dst, RtlSignalBase), dst
        self.dst = dst
        self.src = src
        if isinstance(src, SsaPhi):
            src.users.append(self)
        elif isinstance(src, tuple):
            for op in src[1]:
                if isinstance(op, SsaPhi):
                    op.users.append(self)

    def iterInputs(self):
        src = self.src
        if isinstance(src, tuple):
            yield from src[1]
        else:
            yield src

    def replaceInput(self, orig_expr: SsaPhi, new_expr: Union[SsaPhi, HValue]):
        src = self.src
        if orig_expr is src:
            orig_expr.users.remove(self)
            self.src = new_expr
            if isinstance(new_expr, SsaPhi):
                new_expr.users.append(self)
        else:
            assert orig_expr in src[1]
            self.src = (src[0], tuple(new_expr if o is orig_expr else o for o in src[1]))
            orig_expr.users.remove(self)
            if isinstance(new_expr, SsaPhi):
                new_expr.users.append(self)

    def __repr__(self):
        dst = self.dst
        src = self.src
        if isinstance(src, (HlsTmpVariable, RtlSignal, HValue, SsaPhi)):
            return f"{dst} = {src}"
        else:
            _src = ", ".join(repr(s) for s in src[1])
            return f"{dst} = {src[0].id:s} {_src:s}"

