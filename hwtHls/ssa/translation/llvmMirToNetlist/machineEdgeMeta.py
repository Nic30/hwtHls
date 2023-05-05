from enum import Enum
from typing import Union, Optional, List, Tuple

from hwtHls.llvm.llvmIr import MachineBasicBlock, Register
from hwtHls.netlist.nodes.ports import HlsNetNodeOut


class MachineLoopId():

    def __init__(self, headerBlockNum:int, depth:int):
        self.headerBlockNum = headerBlockNum
        self.depth = depth

    def __hash__(self):
        return hash((self.headerBlockNum, self.depth))

    def __eq__(self, other):
        return isinstance(other, MachineLoopId) and \
            self.headerBlockNum == other.headerBlockNum and \
            self.depth == other.depth

    def __repr__(self):
        return f"bb{self.headerBlockNum:d}.l{self.depth}"


MachineEdge = Tuple[MachineBasicBlock, MachineBasicBlock]


class MACHINE_EDGE_TYPE(Enum):
    NORMAL = 0  # an edge with no special meaning, inlined to circuit as is
    RESET = 1  # an edge which source will be used to generate reset values (this edge will ot physically exist in circuit)
    FORWARD = 2  # a normal edge which has to have explicit channel because destination needs to have separate control
    BACKWARD = 3  # an edge which should be implemented as backward channel because its direction is opposite to main pipeline direction
    DISCARDED = 4  # an edge which will not exists in architecutre because it was decided that the synchronization which this edge implements is useless


class MachineEdgeMeta():
    """
    A container for an information about the edge in Control Flow Graph

    :ivar inlineRstDataToEdge: an edge where values comming on this edge should be inlide as a initialization of the buffers to implement loop in circuit.
    :ivar reuseDataAsControl: the optional register which datachannel should be used to implement this control edge
    :ivar enteringLoops: loops which are entered if this control follows this edge
    :ivar reenteringLoops: loops which are reentered if this control follows this edge
    :ivar exitingLoops: loops which are exited if this control follows this edge
    :ivar buffers: A list of tuples (liveIn var register or block, output of buffer read object)
    :ivar buffersForLoopExit: A list of tuples (machine bb edge, output of buffer read object) for each buffer which is used to signalize loop parent loop about exit
        (dst in edge is a loop header)
    """

    def __init__(self, srcBlock: MachineBasicBlock, dstBlock: MachineBasicBlock, etype: MACHINE_EDGE_TYPE):
        self.srcBlock = srcBlock
        self.dstBlock = dstBlock
        self.etype = etype
        self.inlineRstDataToEdge: Optional[MachineEdge] = None
        self.reuseDataAsControl: Optional[Register] = None
        self.enteringLoops: List[MachineLoopId] = []
        self.reenteringLoops: List[MachineLoopId] = []
        self.exitingLoops: List[MachineLoopId] = []
        # output if from node of type  Union[HlsNetNodeReadBackedge, HlsNetNodeLoopDataRead]
        # MachineEdge can be only the (self.srcBlock, self.dstBlock)
        self.buffers: List[Tuple[Union[Register, MachineEdge], HlsNetNodeOut]] = []
        self.buffersForLoopExit: List[Tuple[MachineEdge, HlsNetNodeOut]] = []

    def getBufferForReg(self, dReg: Union[Register, MachineEdge]) -> HlsNetNodeOut:
        assert self.etype != MACHINE_EDGE_TYPE.DISCARDED, self
        for reg, r in self.buffers:
            if reg.__class__ is dReg.__class__ and reg == dReg:
                return r

        raise AssertionError("Can not find buffer for ",
                             ('r', dReg.virtRegIndex()) if isinstance(dReg, Register) else (dReg[0].getNumber(), '->', dReg[1].getNumber()),
                             "for bb", self.srcBlock.getNumber(), " -> bb", self.dstBlock.getNumber())

    def __repr__(self):
        return (
            f"<{self.__class__.__name__:s} {self.srcBlock.getNumber():d}->{self.dstBlock.getNumber():d} "
            f"{self.etype.name:s}{'' if self.reuseDataAsControl is None else f' reuseDataAsControl={self.reuseDataAsControl}'}"
            f"{'' if self.inlineRstDataToEdge is None else f' inlineRstDataToEdge=({self.inlineRstDataToEdge[0].getNumber():d}, {self.inlineRstDataToEdge[1].getNumber()})'}"
            f"{'' if not self.enteringLoops else f' enteringLoops={self.enteringLoops}'}"
            f"{'' if not self.reenteringLoops else f' reenteringLoops={self.reenteringLoops}'}"
            f"{'' if not self.exitingLoops else f' exitingLoops={self.exitingLoops}'}>")
