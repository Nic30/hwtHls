from typing import Callable

from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.thread import HlsThread, HlsThreadDoesNotUseSsa


class HlsThreadFromNetlist(HlsThread):
    """
    A thread which is described using function which directly generates HlsNetlist.
    """

    def __init__(self, hls: HlsScope, netlistConstructor: Callable[[HlsNetlistCtx], None]):
        super(HlsThreadFromNetlist, self).__init__(hls)
        self.netlistConstructor = netlistConstructor

    def getLabel(self) -> str:
        i = self.hls._threads.index(self)
        return f"t{i:d}_{self.netlistConstructor.__name__:s}"

    def compileToSsa(self):
        raise HlsThreadDoesNotUseSsa()
    
    def compileToNetlist(self, platform:DefaultHlsPlatform):
        hls = self.hls
        netlist = self.toHw = HlsNetlistCtx(hls.parentUnit, hls.freq, self.getLabel())
        self.builder = HlsNetlistBuilder(netlist)
        netlist._setBuilder(self.builder)
        self.netlistConstructor(netlist)
        return netlist