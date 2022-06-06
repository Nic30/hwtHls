from typing import Union, Optional, Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.llvm.llvmIr import  MachineBasicBlock
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes, \
    HlsNetNodeOutLazy


class MachineBasicBlockSyncContainer():
    """
    :ivar block: a MachineBasicBlock for which this container holds an information
    :ivar blockEn: control flow enable input (some netlist node output)
    :note: blockEn is not RTL like enable signal, it is flag which synchronizes execution of threads.
    :ivar orderingIn: ordering input which is used to keep order of IO operations
    :ivar orderingOut: ordering port from last ordered node in this block
    :ivar needsControl: This block needs the control channel on the input for its functionality.
    :ivar needsStarter: This block requires a provider of initial sync token for its functionality.
    :ivar uselessControlBackedgesFrom: set of block which do have backedge to this block and which is not required
        (because loop body does not need to wait on previous iteration)
    :note: If the control backedge is useless it does not imply that the control is useless it may be still required
        if there are multiple threads.
    """

    def __init__(self,
                 block: MachineBasicBlock,
                 blockEn: Optional[HlsNetNodeOutAny],
                 orderingIn: Optional[HlsNetNodeOutAny]):
        self.block = block
        self.needsStarter = False
        self.needsControl = False
        self.blockEn = blockEn
        self.orderingIn = orderingIn
        self.orderingOut = orderingIn
        self.uselessControlBackedgesFrom: Set[MachineBasicBlock] = set() 

    def isInitOnly(self):
        return not self.nodes and self.needsStarter
        
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

    def __repr__(self):
        return f"<{self.__class__.__name__} block={self.block.getName().str():s},{' needsStarter,' if self.needsStarter else ''}{' needsControl,' if self.needsControl else ''} blockEn={self.blockEn}, orderingIn={self.orderingIn}, orderingOUt={self.orderingOut}>"
        