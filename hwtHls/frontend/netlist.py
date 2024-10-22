from typing import Callable, Optional

from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.thread import HlsThread, HlsThreadDoesNotUseSsa
from hwtHls.netlist.scheduler.resourceList import SchedulingResourceConstraints, \
    initSchedulingResourceConstraintsFromIO
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class HlsThreadFromNetlist(HlsThread):
    """
    A thread which is described using function which directly generates HlsNetlist.
    """

    def __init__(self, hls: HlsScope, netlistConstructor: Callable[[HlsNetlistCtx], None], resourceConstraints:Optional[SchedulingResourceConstraints]=None):
        super(HlsThreadFromNetlist, self).__init__(hls, resourceConstraints)
        self.netlistConstructor = netlistConstructor

    def getLabel(self) -> str:
        i = self.hls._threads.index(self)
        return f"t{i:d}_{self.netlistConstructor.__name__:s}"

    def compileToSsa(self):
        raise HlsThreadDoesNotUseSsa()

    def compileToNetlist(self, platform:DefaultHlsPlatform):
        hls = self.hls
        namePrefix = self.hls.namePrefix
        if len(self.hls._threads) > 1:
            i = self.hls._threads.index(self)
            namePrefix = f"{self.hls.namePrefix}t{i:d}_"
        netlist = self.netlist = HlsNetlistCtx(hls.parentHwModule, hls.freq,
                                            self.getLabel(),
                                            self.resourceConstraints,
                                            namePrefix=namePrefix)
        self.builder:HlsNetlistBuilder = netlist.builder
        self.netlistConstructor(netlist)
        ioResources = []
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if isinstance(n, (HlsNetNodeRead, HlsNetNodeWrite)):
                schedResT = n.getSchedulingResourceType()
                if schedResT is not None:
                    ioResources.append(schedResT)
        initSchedulingResourceConstraintsFromIO(self.resourceConstraints, ioResources)
        return netlist
