# from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from typing import Union, Dict, List

from hwt.synthesizer.interface import Interface
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass


class HlsNetlistAnalysisPassDiscoverIo(HlsNetlistAnalysisPass):

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.io_by_interface: Dict[Interface, List[Union["HlsNetNodeRead", "HlsNetNodeWrite"]]] = {}
    
    def run(self):
        assert not self.io_by_interface
        io_by_interface = self.io_by_interface
        for op in self.netlist.inputs:
            op: "HlsNetNodeRead"
            op_list = io_by_interface.get(op.src, None)
            if op_list  is None:
                op_list = io_by_interface[op.src] = []
            op_list.append(op)
        
        for op in self.netlist.outputs:
            op: "HlsNetNodeWrite"
            op_list = io_by_interface.get(op.dst, None)
            if op_list  is None:
                op_list = io_by_interface[op.dst] = []
            op_list.append(op)

