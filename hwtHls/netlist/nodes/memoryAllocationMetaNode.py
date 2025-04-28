from typing import Optional, Tuple, List, Union

from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.array import HArray
from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.typingFuture import override
from hwt.serializer.resourceAnalyzer.resourceTypes import RtlResourceType
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.readIndexed import HlsNetNodeReadIndexed
from hwtHls.netlist.nodes.writeIndexed import HlsNetNodeWriteIndexed


class MemoryAllocationMeta(RtlResourceType):
    """
    This class represents record about memory which should be constructed later in compilation.
    This is a symbolic reference and it is yet to be chosen how many port, which latency
    and which physical resource will be used to realize this memory.  
    
    :note: it is not a HlsNetNode because it would create complex cycles during scheduling.
        Significantly limiting compilation speed.
    
    :ivar dataOfComponentGenerator: property where ComponentGenerator may store temporary data
    """

    def __init__(self, name:str, dtype: HArray, initValue: Optional[List[Optional[int]]]):
        self.name = name
        self._name = name  # for getSignalName
        self.dtype = dtype
        self.initValue = initValue
        self.users: List[HlsNetNodeReadMemoryAllocation, HlsNetNodeWriteMemoryAllocation] = []
        self.dataOfComponentGenerator = None

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.name}>"


class HlsNetNodeReadMemoryAllocation(HlsNetNodeReadIndexed):
    """
    Read from memory which is now represented just by MemoryAllocationMeta
    """

    def __init__(self, netlist:"HlsNetlistCtx", src:MemoryAllocationMeta, dtype: HdlType, name:Optional[str]=None):
        HlsNetNodeReadIndexed.__init__(self, netlist, src, dtype=dtype, name=name)
        src.users.append(self)
        self._portSrc = None  # for compatibility with HlsNetNodeWriteBramCmd

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNodeReadIndexed.clone(self, memo, keepTopPortsConnected)
        if isNew:
            self.src.users.append(y)

        return y, isNew

    @override
    def resolveRealization(self):
        self.netlist.platform._componentGenerators[MemoryAllocationMeta].resolveRealizationOfNode(self)

    @override
    def markAsRemoved(self):
        HlsNetNodeReadIndexed.markAsRemoved(self)
        self.src.users.remove(self)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        return  self.netlist.platform._componentGenerators[MemoryAllocationMeta].rtlAllocOfNode(allocator, self)


class HlsNetNodeWriteMemoryAllocation(HlsNetNodeWriteIndexed):
    """
    Write to memory which is now represented just by MemoryAllocationMeta
    """

    def __init__(self, netlist:"HlsNetlistCtx", dst:MemoryAllocationMeta,
                 mayBecomeFlushable=False,
                 name:Optional[str]=None,
                 addSrcPort=True):
        HlsNetNodeWriteIndexed.__init__(self, netlist, dst,
                                 mayBecomeFlushable=mayBecomeFlushable,
                                 name=name,
                                 addSrcPort=addSrcPort)
        dst.users.append(self)
        self._portDataOut = None  # for compatibility with HlsNetNodeWriteBramCmd
        self._rtlUseValid = True

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNodeWriteIndexed.clone(self, memo, keepTopPortsConnected)
        if isNew:
            self.dst.users.append(y)

        return y, isNew

    @override
    def markAsRemoved(self):
        HlsNetNodeWriteIndexed.markAsRemoved(self)
        self.dst.users.remove(self)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        return self.netlist.platform._componentGenerators[MemoryAllocationMeta].rtlAllocOfNode(allocator, self)

