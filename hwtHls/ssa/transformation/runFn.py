from typing import Callable

from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.transformation.ssaPass import SsaPass


class SsaPassRunFn(SsaPass):
    """
    A simple pass which just runs a predefined function.
    """

    def __init__(self, fnToRun: Callable[["HlsStreamProc", AstToSsa], None]):
        self.fnToRun = fnToRun

    def apply(self, hls: "HlsStreamProc", to_ssa: AstToSsa):
        self.fnToRun(hls, to_ssa)
