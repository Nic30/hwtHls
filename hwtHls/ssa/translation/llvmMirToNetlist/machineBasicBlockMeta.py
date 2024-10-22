from typing import Union, Optional, Literal, Dict, Set

from hwtHls.llvm.llvmIr import MachineBasicBlock, Register
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.aggregatedLoop import HlsNetNodeAggregateLoop
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, \
    HlsNetNodeOutLazy
from hwtHls.netlist.nodes.portsUtils import HlsNetNodeOutLazy_replace, \
    HlsNetNodeOutLazy_replaceThisInUsers
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
#from hwtHls.ssa.translation.llvmMirToNetlist.insideOfBlockSyncTracker import InsideOfBlockSyncTracker


class ADD_ORDERING_PREPEND:

    def __init__(self):
        raise AssertionError("This class is constant and is not intended for instantiation")


class MachineBasicBlockMeta():
    """
    This class is used as container for information about how control should be implemented in the block.

    :ivar block: a MachineBasicBlock for which this container holds an information
    :ivar constLiveOuts: set of liveout registers which are known to have constant value
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
    
    :ivar parentElement: parent netlist node where this block content should be materialized
    """

    def __init__(self,
                 block: MachineBasicBlock,
                 constLiveOuts: Set[Register],
                 blockEn: Optional[HlsNetNodeOutAny],
                 orderingIn: Optional[HlsNetNodeOutAny]):
        self.block = block
        self.constLiveOuts = constLiveOuts
        self.blockEn = blockEn
        self.needsStarter = False
        self.needsControl = False
        # self.useDataAsControl: Optional[Dict[MachineBasicBlock, Register]] = None
        self.rstPredeccessor: Optional[MachineBasicBlock] = None
        self.orderingIn = orderingIn
        self.orderingOut = orderingIn

        self.isLoopHeader: bool = False
        self.isLoopHeaderOfFreeRunning: bool = False
        self.isLoopAsyncPrequel: bool = False
        self.loopStatusNode: Optional[HlsNetNodeLoopStatus] = None
        self.parentElement: Union[ArchElement, HlsNetNodeAggregateLoop, None] = None
        # self.uselessOrderingFrom: Set[MachineBasicBlock] = set()
        # self.uselessControlBackedgesFrom: Set[MachineBasicBlock] = set()
        #self.syncTracker = InsideOfBlockSyncTracker(blockEn, None)
        self.translatedBranchConditions: Dict[Register, HlsNetNodeOutAny] = {}

    def assignParentElement(self, elm: Union[ArchElement, HlsNetNodeAggregateLoop]):
        self.parentElement = elm
        #self.syncTracker.builder = elm.builder

    def addOrderedNodeForControlWrite(self, n: HlsNetNodeWriteBackedge, dstBlokSync: "MachineBasicBlockMeta"):
        # if self.block in dstBlokSync.uselessOrderingFrom:
        #    i = n._addInput("orderingIn")
        #    n.associatedRead.getOrderingOutPort().connectHlsIn(i)
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
            HlsNetNodeOutLazy_replaceThisInUsers(curI, n.getOrderingOutPort())
            curI.connectHlsIn(i)

        elif atEnd:
            self.orderingOut.connectHlsIn(i)
            self.orderingOut = n.getOrderingOutPort()
        else:
            curI = self.orderingIn
            assert isinstance(curI, HlsNetNodeOutLazy), curI
            curI: HlsNetNodeOutLazy
            HlsNetNodeOutLazy_replace(curI, n.getOrderingOutPort())
            self.orderingIn = i

    def addOrderingDelay(self, clkTicks: int):
        assert clkTicks > 0, clkTicks
        oo = self.orderingOut
        assert oo is not None
        if isinstance(oo, HlsNetNodeOutLazy):
            raise NotImplementedError()
        else:
            netlist: HlsNetlistCtx = oo.obj.netlist
            parent = oo.obj.getParent()

        n = HlsNetNodeDelayClkTick(netlist, HVoidOrdering, clkTicks)
        parent.addNode(n)
        oo.connectHlsIn(n._inputs[0])
        self.orderingOut = n._outputs[0]

    def __repr__(self):
        return f"<{self.__class__.__name__} bb{self.block.getNumber()}.{self.block.getName().str():s}>"

