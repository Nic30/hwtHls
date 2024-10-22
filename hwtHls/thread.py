from typing import Optional, Callable, List

from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.netlist.scheduler.resourceList import SchedulingResourceConstraints


class HlsThreadDoesNotUseSsa(Exception):
    pass


class HlsThread():
    """
    A container of a thread which will be compiled later.
    """

    def __init__(self, hls: "HlsScope", resourceConstraints: Optional[SchedulingResourceConstraints]):
        self.hls = hls
        self.toSsa: Optional[HlsAstToSsa] = None
        if resourceConstraints is None:
            resourceConstraints = {}
        self.resourceConstraints = resourceConstraints
        self.netlist: Optional[HlsNetlistCtx] = None
        self.netlistCallbacks: List[Callable[["HlsScope", HlsThread]]] = []
        self.archNetlistCallbacks: List[Callable[["HlsScope", HlsThread]]] = []

    def debugCopyConfig(self, p: DefaultHlsPlatform):
        """
        Copy debugging config from HlsPlatform object before any other work is performed.
        """
        if self.toSsa is not None:
            self.toSsa.namePrefix = self.getNamePrefix()

    def getLabel(self) -> str:
        i = self.hls._threads.index(self)
        return f"t{i:d}"

    def getNamePrefix(self):
        namePrefix = self.hls.namePrefix
        if len(self.hls._threads) > 1:
            i = self.hls._threads.index(self)
            namePrefix = f"{self.hls.namePrefix}t{i:d}_"
        return namePrefix

    def compileToSsa(self):
        raise NotImplementedError("Must be implemented in child class", self)

    def compileToNetlist(self, platform: DefaultHlsPlatform):
        hls = self.hls
        self.netlist = HlsNetlistCtx(
            hls.parentHwModule, hls.freq, self.getLabel(),
            self.resourceConstraints,
            namePrefix=self.getNamePrefix(),
            platform=hls.parentHwModule._target_platform)
        platform.runSsaToNetlist(self.hls, self.toSsa, self.netlist)
        return self.netlist
