from typing import Callable

from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.typingFuture import override


class SsaPassRunFn(SsaPass):
    """
    A simple pass which just runs a predefined function.
    """

    def __init__(self, fnToRun: Callable[["SsaPassRunFn", HlsAstToSsa], None]):
        self.fnToRun = fnToRun
    
    @override
    def runOnSsaModuleImpl(self, toSsa:"HlsAstToSsa"):
        self.fnToRun(self, toSsa)
