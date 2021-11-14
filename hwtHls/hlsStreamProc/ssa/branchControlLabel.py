from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock
from ipCorePackager.constants import INTF_DIRECTION


class BranchControlLabel():
    """
    The label for and interface between two basic blocks wich passes the control tokens.
    To drive the control/program flow of the circuit.

    This interface may have a different implementation depending on a type of synchronization.
    And does not need to have a physical representation at all if control flow can be handled purely
    by presence of data.

    :note: INTF_DIRECTION.MASTER means that this is a label for an interface which outputs the sync. token to next block
    :note: INTF_DIRECTION.SLAVE means that this is a label for an interface which provides the sync. token from previous block
    """

    def __init__(self, src_block:SsaBasicBlock, dst_block:SsaBasicBlock, direction: INTF_DIRECTION):
        assert isinstance(direction, INTF_DIRECTION)
        self.src_block = src_block
        self.dst_block = dst_block
        self.direction = direction

    def __eq__(self, other):
        return (
            self.__class__ is other.__class__ and
            self.src_block is other.src_block and
            self.dst_block is other.dst_block and
            self.direction is other.direction
        )

    def __hash__(self):
        return hash((
            self.__class__,
            self.src_block,
            self.dst_block,
            self.direction
        ))

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.src_block.label:s} -> {self.dst_block.label:s} {self.direction.name}>"
