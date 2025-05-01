
from typing import Optional

from hwt.hdl.types.array import HArray
from hwt.serializer.resourceAnalyzer.resourceTypes import RtlResourceType


class MemoryAllocationMeta(RtlResourceType):
    """
    This class represents record about memory which should be constructed later in compilation.
    This is a symbolic reference and it is yet to be chosen how many port, which latency
    and which physical resource will be used to realize this memory.  
    
    :note: it is not a HlsNetNode because it would create complex cycles during scheduling.
        Significantly limiting compilation speed.
    
    :ivar dataOfComponentGenerator: property where ComponentGenerator may store temporary data
    """

    def __init__(self, name:str, dtype: HArray, initValue: Optional[list[Optional[int]]]):
        self.name = name
        self._name = name  # for getSignalName
        self.dtype = dtype
        self.initValue = initValue
        self.users: list["HlsNetNodeWriteMemoryAllocationCmd", "HlsNetNodeReadMemoryAllocationReadData"] = []
        self.dataOfComponentGenerator = None

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.name}>"
