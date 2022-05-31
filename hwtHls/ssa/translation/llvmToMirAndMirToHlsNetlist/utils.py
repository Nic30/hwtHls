from typing import Union, Optional

from hwtHls.llvm.llvmIr import  MachineBasicBlock
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes, \
    HlsNetNodeOutLazy


class MachineBasicBlockSyncContainer():
    """
    :ivar block: a MachineBasicBlock for which this container holds an information
    :ivar blockEn: control flow enable input (some netlist node output)
    :ivar orderingIn: ordering input which is used to keep order of IO operations
    :ivar OrderingOut: ordering port from last ordered node in this block
    """

    def __init__(self,
                 block: MachineBasicBlock,
                 blockEn: Optional[HlsNetNodeOutAny],
                 orderingIn: Optional[HlsNetNodeOutAny]):
        self.block = block
        self.blockEn = blockEn
        self.orderingIn = orderingIn
        self.orderingOut = orderingIn 

    def addOrderedNode(self, n: Union[HlsNetNodeRead, HlsNetNodeWrite], atEnd=True):
        i = n._add_input()
        if atEnd:
            link_hls_nodes(self.orderingOut, i)
            self.orderingOut = n.getOrderingOutPort()
        else:
            curI = self.orderingIn
            assert isinstance(curI, HlsNetNodeOutLazy), curI
            curI: HlsNetNodeOutLazy
            curI.replace_driver(n.getOrderingOutPort())
            self.orderingIn = i
            

