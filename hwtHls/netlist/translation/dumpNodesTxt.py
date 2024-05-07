from io import StringIO
from typing import Sequence

from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.platform.fileUtils import OutputStreamGetter


class HlsNetlistPassDumpNodesTxt(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @classmethod
    def _printNodes(cls, indent:str, nodeIterator:Sequence[HlsNetNode], out: StringIO):
        # :note: sort is to improve readability
        for n in sorted(nodeIterator, key=lambda n: n._id):
            n: HlsNetNode
            out.write(f"{indent:s}{n}\n")
            if isinstance(n, HlsNetNodeAggregate):
                cls._printNodes(indent + "  ", n._subNodes, out)

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        out, doClose = self.outStreamGetter(netlist.label)
        try:
            self._printNodes("", netlist.iterAllNodes(), out)
            out.write("\n")
        finally:
            if doClose:
                out.close()

