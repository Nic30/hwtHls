from typing import Union, Optional, Literal

from hwtHls.llvm.llvmIr import MachineBasicBlock
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes, \
    HlsNetNodeOutLazy
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class ADD_ORDERING_PREPEND:

    def __init__(self):
        raise AssertionError("This class is constant and is not intended for instantiation")


class MachineBasicBlockMeta():
    """
    This class is used as container for information about how control should be implemented in the block.

    :ivar block: a MachineBasicBlock for which this container holds an information
    :ivar blockEn: control flow enable input to this block
    :note: blockEn is not RTL like enable signal, it is flag which synchronizes execution of threads.
        It should never be in invalid state, 1 means that all values comming from selected predecessors
        are valid, except for values which were obtained by non blocking reads (which have explicit validNB signal).
    :ivar orderingIn: ordering input which is used to keep order of IO operations
    :ivar orderingOut: ordering port from last ordered node in this block
    :ivar needsControl: This block needs the control channel on the input for its functionality.
    :ivar needsStarter: This block requires a provider of initial sync token for its functionality.
    :ivar rstPredeccessor: This block requires extraction of rst values for variables modified by PHIs, rstPredeccessor is a block
        which is executed only once during program lifetime and the values coming from it are safe to extract as a hardware memory reset values.
    :note: If the control backedge is useless it does not imply that the control is useless it may be still required
        if there are multiple threads in relict of original loop.
    :note: Ordering is typically useless if all instructions in block are in same dataflow graph.


    :ivar isLoopHeader: True if this block is a header block of loop
    :ivar isLoopHeaderOfFreeRunning: True if the loop with this block as header does not require between
        iteration synchronization.
    :ivar loopDepths: a list of depths of loops which should be constructed in netlist

    #:note: if useDataAsControl is specified it must contain record for every predecessor except rstPredeccessor.
    #:ivar uselessControlBackedgesFrom: set of block which do have backedge to this block and which is not required
    #    (because loop body does not need to wait on previous iteration)
    #:ivar uselessOrderingFrom: a set of source block from where the propagation of ordering should be cancelled
    #    (The ordering of operations between this and destination block will be based only on data dependencies.)
    #:ivar loops: List of loop gates which are managing input of data and control to the loop body.
    #    The top loop is first.
    #:ivar useDataAsControl: Optional dictionary which specifies which data should be used as sync from each predecessor.
    """

    def __init__(self,
                 block: MachineBasicBlock,
                 blockEn: Optional[HlsNetNodeOutAny],
                 orderingIn: Optional[HlsNetNodeOutAny]):
        self.block = block
        self.needsStarter = False
        self.needsControl = False
        # self.useDataAsControl: Optional[Dict[MachineBasicBlock, Register]] = None
        self.rstPredeccessor: Optional[MachineBasicBlock] = None
        self.blockEn = blockEn
        self.orderingIn = orderingIn
        self.orderingOut = orderingIn

        self.isLoopHeader: bool = False
        self.isLoopHeaderOfFreeRunning: bool = False
        self.isLoopAsyncPrequel: bool = False
        self.loopStatusNode: Optional[HlsNetNodeLoopStatus] = None
        # self.uselessOrderingFrom: Set[MachineBasicBlock] = set()
        # self.uselessControlBackedgesFrom: Set[MachineBasicBlock] = set()

    def addOrderedNodeForControlWrite(self, n: HlsNetNodeWriteBackedge, dstBlokSync: "MachineBasicBlockMeta"):
        # if self.block in dstBlokSync.uselessOrderingFrom:
        #    i = n._addInput("orderingIn")
        #    link_hls_nodes(n.associatedRead.getOrderingOutPort(), i)
        #    self.orderingOut = n.getOrderingOutPort()
        # else:
        self.addOrderedNode(n)

    def addOrderedNode(self, n: Union[HlsNetNodeRead, HlsNetNodeWrite],
                       atEnd: Union[bool, Literal[ADD_ORDERING_PREPEND]]=True):
        i = n._addInput("orderingIn")
        if atEnd is ADD_ORDERING_PREPEND:
            curI = self.orderingIn
            assert isinstance(curI, HlsNetNodeOutLazy), curI
            curI: HlsNetNodeOutLazy
            curI.replaceThisInUsers(n.getOrderingOutPort())
            link_hls_nodes(curI, i)

        elif atEnd:
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

        n = HlsNetNodeDelayClkTick(netlist, clkTicks, HVoidOrdering)
        netlist.nodes.append(n)
        link_hls_nodes(oo, n._inputs[0])
        self.orderingOut = n._outputs[0]

    def __repr__(self):
        return f"<{self.__class__.__name__} bb{self.block.getNumber()}.{self.block.getName().str():s}>"

