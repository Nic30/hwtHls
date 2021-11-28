from typing import Callable

from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa


class SsaPassRunFn():
    """
    A simple pass which just runs a predefined function.
    """

    def __init__(self, fnToRun: Callable[[AstToSsa], None]):
        self.fnToRun = fnToRun

    def apply(self, to_ssa: AstToSsa):
        self.fnToRun(to_ssa)
