from hwtHls.llvm.llvmIr import MachineBasicBlock


class BranchOutLabel():
    """
    A label used in :class:`MirToHwtHlsNetlistOpCache` as a key for value which is 1 if the control is passed from src to dst.
    """

    def __init__(self, dst: MachineBasicBlock):
        self.dst = dst

    def __hash__(self):
        return hash((self.__class__, self.dst))

    def __eq__(self, other):
        return type(self) is type(other) and self.dst == other.dst
