from typing import Generator

from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn


class HlsNetNodeOrderable(HlsNetNode):

    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        """
        Iterate input ports which are used for ordering between HlsNetNodeOrderable instances
        """
        raise NotImplementedError(
            "Override this method in derived class", self)

    def getOrderingOutPort(self) -> HlsNetNodeOut:
        """
        Get output port used for ordering between HlsNetNodeOrderable instances.
        """
        raise NotImplementedError(
            "Override this method in derived class", self)
