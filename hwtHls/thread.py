from typing import Optional, Callable, List

from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.scheduler.resourceList import SchedulingResourceConstraints
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hdlConvertorAst.translate.common.name_scope import NameScope


class HlsThreadDoesNotUseSsa(Exception):
    pass


class HlsThread():
    """
    A container of a thread which will be compiled later.
    """

    def __init__(self, hls: "HlsScope", resourceConstraints: Optional[SchedulingResourceConstraints]):
        self.hls = hls
        self.toLlvm: Optional[ToLlvmIrTranslator] = None
        if resourceConstraints is None:
            resourceConstraints = {}
        self.resourceConstraints = resourceConstraints
        self.netlist: Optional[HlsNetlistCtx] = None
        self.netlistCallbacks: List[Callable[["HlsScope", HlsThread]]] = []
        self.archNetlistCallbacks: List[Callable[["HlsScope", HlsThread]]] = []
        self._label: Optional[str] = None

    def debugCopyConfig(self, p: DefaultHlsPlatform):
        """
        Copy debugging config from HlsPlatform object before any other work is performed.
        """
        if self.toLlvm is not None:
            self.toLlvm.namePrefix = self.getNamePrefix()

    def getLabel(self) -> str:
        if self._label is not None:
            return self._label
        i = self.hls._threads.index(self)
        ns: NameScope = self.hls.parentHwModule._target_platform._debug.nameScope
        self._label = ns.checked_name(f"t{i:d}", self)
        return self._label

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
            hls.parentHwModule, hls.freq, self.hls.parentHwModule._getDefaultName() + "_" + self.getLabel(),
            self.resourceConstraints,
            namePrefix=self.getNamePrefix(),
            platform=hls.parentHwModule._target_platform)
        platform.runSsaToNetlist(self.hls, self.toLlvm, self.netlist)
        return self.netlist
