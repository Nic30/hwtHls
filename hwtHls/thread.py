from typing import Optional

from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.netlist.context import HlsNetlistCtx


class HlsThread():
    """
    A container of a thread which will be compiled later.
    """

    def __init__(self, hls: "HlsScope"):
        self.hls = hls
        self.toSsa: Optional[HlsAstToSsa] = None
        self.toHw: Optional[HlsNetlistCtx] = None

    def getLabel(self) -> str:
        i = self.hls._threads.index(self)
        return f"t{i:d}"

    def compileToSsa(self):
        raise NotImplementedError("Must be implemented in child class", self)

