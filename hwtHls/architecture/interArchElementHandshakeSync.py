from typing import Optional, Union, Dict, List, Tuple

from hwt.interfaces.std import HandshakeSync
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from ipCorePackager.constants import DIRECTION


class InterArchElementHandshakeSync(HandshakeSync):
    """
    :ivar data: list of tuples (src, dst) which are synchronized by this interface 
    """

    def __init__(self,
                 clkIndex: int,
                 srcElm: "AllocatorArchitecturalElement",
                 dstElm: "AllocatorArchitecturalElement",
                 masterDir=DIRECTION.OUT, hdl_name:Optional[Union[str, Dict[str, str]]]=None, loadConfig=True):
        HandshakeSync.__init__(self, masterDir=masterDir, hdl_name=hdl_name, loadConfig=loadConfig)
        self.clkIndex = clkIndex
        self.srcElm = srcElm
        self.dstElm = dstElm
        self.data: List[Tuple[TimeIndependentRtlResourceItem, TimeIndependentRtlResourceItem]] = []

