from typing import Callable

from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.ssa.transformation.ssaPass import SsaPass


class SsaPassRunFn(SsaPass):
    """
    A simple pass which just runs a predefined function.
    """

    def __init__(self, fnToRun: Callable[["HlsScope", HlsAstToSsa], None]):
        self.fnToRun = fnToRun

    def apply(self, hls: "HlsScope", to_ssa: HlsAstToSsa):
        self.fnToRun(hls, to_ssa)
