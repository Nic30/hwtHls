from typing import Union, Optional

from hwtHls.llvm.llvmIr import  MachineBasicBlock
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes, \
    HlsNetNodeOutLazy


class MachineBasicBlockSyncContainer():
    """
    This class is used as container for information about how control should be implemented in the block.
    
    :ivar block: a MachineBasicBlock for which this container holds an information
    :ivar blockEn: control flow enable input (some netlist node output)
    :note: blockEn is not RTL like enable signal, it is flag which synchronizes execution of threads.
    :ivar orderingIn: ordering input which is used to keep order of IO operations
    :ivar orderingOut: ordering port from last ordered node in this block
    :ivar needsControl: This block needs the control channel on the input for its functionality.
    :ivar needsStarter: This block requires a provider of initial sync token for its functionality.
    :ivar rstPredeccessor: This block requires extraction of rst values for variables modified by PHIs, rstPredeccessor is a block
        which is executed only once during program lifetime and the values coming from it are safe to extract as a hardware memory reset values.
    #:ivar uselessControlBackedgesFrom: set of block which do have backedge to this block and which is not required
    #    (because loop body does not need to wait on previous iteration)
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
        self.rstPredeccessor: Optional[MachineBasicBlock] = None 
        self.blockEn = blockEn
        self.orderingIn = orderingIn
        self.orderingOut = orderingIn
        # self.uselessControlBackedgesFrom: Set[MachineBasicBlock] = set() 

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
        return (f"<{self.__class__.__name__} block={self.block.getName().str():s},"
                f"{' needsStarter,' if self.needsStarter else ''}"
                f"{' needsControl,' if self.needsControl else ''}"
                f" blockEn={self.blockEn}, orderingIn={self.orderingIn}, orderingOut={self.orderingOut}>")
        
