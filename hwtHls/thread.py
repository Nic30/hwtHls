from typing import Optional, Callable, List

from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.platform.platform import DefaultHlsPlatform


class HlsThreadDoesNotUseSsa(Exception):
    pass


class HlsThread():
    """
    A container of a thread which will be compiled later.
    """

    def __init__(self, hls: "HlsScope"):
        self.hls = hls
        self.toSsa: Optional[HlsAstToSsa] = None
        self.toHw: Optional[HlsNetlistCtx] = None
        self.netlistCallbacks: List[Callable[["HlsScope", HlsThread]]] = []
    
    def debugCopyConfig(self, p: DefaultHlsPlatform):
        """
        Copy debugging config from HlsPlatform object before any other work is performed.
        """
        pass

    def getLabel(self) -> str:
        i = self.hls._threads.index(self)
        return f"t{i:d}"

    def compileToSsa(self):
        raise NotImplementedError("Must be implemented in child class", self)

    def compileToNetlist(self, platform: DefaultHlsPlatform):
        self.toHw = platform.runSsaToNetlist(self.hls, self.toSsa)
        return self.toHw
