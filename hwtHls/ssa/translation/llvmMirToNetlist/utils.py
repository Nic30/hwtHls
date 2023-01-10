from typing import Union, Optional, List, Tuple, Set

from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineLoop, Register
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge, \
    HlsNetNodeWriteControlBackwardEdge
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.orderable import HOrderingVoidT
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes, \
    HlsNetNodeOutLazy
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.opCache import MirToHwtHlsNetlistOpCache


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
    :ivar backedgeBuffers: A list of tuples (liveIn var register, src machine basic block, buffer read object)
    #:ivar uselessOrderingFrom: a set of source block from where the propagation of ordering should be cancelled
    #    (The ordering of operations between this and destination block will be based only on data dependencies.)
    :note: Ordering is typically useless if all instructions in block are in same dataflow graph.
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
        self.backedgeBuffers: List[Tuple[Register, MachineBasicBlock, HlsNetNodeReadBackwardEdge]] = []
        # self.uselessOrderingFrom: Set[MachineBasicBlock] = set() 
        # self.uselessControlBackedgesFrom: Set[MachineBasicBlock] = set() 

    def addOrderedNodeForControlWrite(self, n: HlsNetNodeWriteControlBackwardEdge, dstBlokSync: "MachineBasicBlockSyncContainer"):
        # if self.block in dstBlokSync.uselessOrderingFrom:
        #    i = n._addInput("orderingIn")
        #    link_hls_nodes(n.associated_read.getOrderingOutPort(), i)
        #    self.orderingOut = n.getOrderingOutPort()
        # else:
        self.addOrderedNode(n)

    def addOrderedNode(self, n: Union[HlsNetNodeRead, HlsNetNodeWrite], atEnd=True):
        i = n._addInput("orderingIn")
        if atEnd:
            link_hls_nodes(self.orderingOut, i)
            self.orderingOut = n.getOrderingOutPort()
        else:
            curI = self.orderingIn
            assert isinstance(curI, HlsNetNodeOutLazy), curI
            curI: HlsNetNodeOutLazy
            curI.replaceDriverObj(n.getOrderingOutPort())
            self.orderingIn = i

    def addOrderingDelay(self, clkTicks: int):
        assert clkTicks > 0, clkTicks
        oo = self.orderingOut
        assert oo is not None
        if isinstance(oo, HlsNetNodeOutLazy):
            netlist: HlsNetlistCtx = oo.netlist
        else:
            netlist: HlsNetlistCtx = oo.obj.netlist

        n = HlsNetNodeDelayClkTick(netlist, clkTicks, HOrderingVoidT)
        netlist.nodes.append(n)
        link_hls_nodes(oo, n._inputs[0])
        self.orderingOut = n._outputs[0]
        
    def __repr__(self):
        return (f"<{self.__class__.__name__} block={self.block.getName().str():s},"
                f"{' needsStarter,' if self.needsStarter else ''}"
                f"{' needsControl,' if self.needsControl else ''}"
                f" blockEn={self.blockEn}, orderingIn={self.orderingIn}, orderingOut={self.orderingOut}>")


class LiveInMuxMeta():
    
    def __init__(self):
        self.values: List[Tuple[HlsNetNodeOutAny, HlsNetNodeOutAny]] = []


def getTopLoopForBlock(mb: MachineBasicBlock, loop: MachineLoop) -> MachineLoop:
    loop: MachineLoop
    topLoop = loop
    while True:
        p: Optional[MachineLoop] = topLoop.getParentLoop()
        if p and p.getHeader() == mb:
            topLoop = loop
        else:
            break
    return topLoop


def HlsNetNodeExplicitSyncInsertBehindLazyOut(netlist: "HlsNetlistCtx",
                                              valCache: MirToHwtHlsNetlistOpCache,
                                              var: HlsNetNodeOutLazy):
    """
    Prepend the synchronization to an operation output representing variable.
    """
    assert isinstance(var, HlsNetNodeOutLazy), var
    self = HlsNetNodeExplicitSync(netlist, var._dtype)
    netlist.nodes.append(self)
    assert len(var.keys_of_self_in_cache) == 1, "Implemented only for case where the input var was not propagated anywhere"

    # add original var as valCache unresolvedBlockInputs
    k = var.keys_of_self_in_cache[0]
    block, reg = k
    o = self._outputs[0]
    # copy endpoints of var to newly generated sync node 
    valCache._replaceOutOnInputOfBlock(block, reg, var, k, o)
    var.replaced_by = None  # reset because we will still use the object
    
    # put original lazy out back to cache so once
    # we resolve input we replace the input to this control and not the explicit sync which we just created
    valCache._moveLazyOutToUnresolvedBlockInputs(block, reg, var, k)
    valCache._toHlsCache[k] = o
    
    # connect original var to the input of sync node
    link_hls_nodes(var, self._inputs[0])
    
    return self