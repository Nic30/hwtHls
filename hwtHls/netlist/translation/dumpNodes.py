from io import StringIO

from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.platform.fileUtils import OutputStreamGetter


class HlsNetlistPassDumpNodes(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @staticmethod
    def _printThreads(netlist: HlsNetlistCtx, out: StringIO):
        # :note: we first collect the nodes to have them always in deterministic order
        for n in sorted(netlist.iterAllNodes(), key=lambda n: n._id):
            n: HlsNetNode
            out.write(f"{n}\n")
        out.write("\n")

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        out, doClose = self.outStreamGetter(netlist.label)
        try:
            self._printThreads(netlist, out)
        finally:
            if doClose:
                out.close()

