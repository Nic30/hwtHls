# from hwtHls.netlist.nodes.io import HlsRead, HlsWrite
from typing import Union, Dict, List

from hwt.synthesizer.interface import Interface
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass


class HlsNetlistAnalysisPassDiscoverIo(HlsNetlistAnalysisPass):

    def __init__(self, hls: "HlsPipeline"):
        HlsNetlistAnalysisPass.__init__(self, hls)
        self.io_by_interface: Dict[Interface, List[Union["HlsRead", "HlsWrite"]]] = {}
    
    def run(self):
        assert not self.io_by_interface
        io_by_interface = self.io_by_interface
        for op in self.hls.inputs:
            op: "HlsRead"
            op_list = io_by_interface.get(op.src, None)
            if op_list  is None:
                op_list = io_by_interface[op.src] = []
            op_list.append(op)
        
        for op in self.hls.outputs:
            op: "HlsWrite"
            op_list = io_by_interface.get(op.dst, None)
            if op_list  is None:
                op_list = io_by_interface[op.dst] = []
            op_list.append(op)

