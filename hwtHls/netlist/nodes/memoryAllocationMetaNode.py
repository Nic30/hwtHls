from typing import Optional, Tuple, List, Union, Literal

from hwt.constants import READ, WRITE
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.io.bram import HlsNetNodeWriteBramCmd, HlsNetNodeReadBramData
from hwtHls.netlist.nodes.memoryAllocationMeta import MemoryAllocationMeta
from hwtHls.netlist.nodes.readIndexed import HlsNetNodeReadIndexed


class HlsNetNodeWriteMemoryAllocationCmd(HlsNetNodeWriteBramCmd):
    """
    Read or write from/to memory which is now represented just by MemoryAllocationMeta.
    :note: This node writes request to memory and may contain port with returned data if the read
        latency is 0.
    """

    def __init__(self, netlist:"HlsNetlistCtx",
                 ioProxy: "IoProxyBram",
                 src: MemoryAllocationMeta,
                 cmd: Literal[READ, WRITE],
                 dtype: HdlType,
                 mayBecomeFlushable=True,
                 name:Optional[str]=None):
        assert isinstance(src, MemoryAllocationMeta), src
        HlsNetNodeWriteBramCmd.__init__(self, netlist, ioProxy, src, cmd,
                                        dtype=dtype,
                                        hasR=cmd is READ,
                                        hasW=cmd is WRITE,
                                        mayBecomeFlushable=mayBecomeFlushable, name=name)
        src.users.append(self)
        # self._portSrc = None  # for compatibility with HlsNetNodeWriteBramCmd

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
    def splitOnClkWindows(self):
        """
        Keep command/write part in this node and extract out data read port if it is in later clock window
        """
        if self.isMulticlock:
            if self.cmd is READ:
                dtype = self._portDataOut._dtype
                dNode = HlsNetNodeReadMemoryAllocationReadData(
                    self.netlist,
                    self.ioProxy,
                    self.dst,
                    self,
                    dtype,
                    name=self.name)
                dNode._rtlUseReady = False
                dNode._rtlUseValid = False
                self._extractReadPortsToSeparateNode(dNode)
                self.parent._addNodeIntoScheduled(dNode.scheduledZero // self.netlist.normalizedClkPeriod, dNode)
                return True
            else:
                assert self.cmd is WRITE, self

        return False

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        return self.netlist.platform._componentGenerators[MemoryAllocationMeta].rtlAllocOfNode(allocator, self)

# class HlsNetNodeWriteMemoryAllocationCmd(HlsNetNodeWriteBramCmd):
#    pass


class HlsNetNodeReadMemoryAllocationReadData(HlsNetNodeReadBramData):

    def __init__(self, netlist: "HlsNetlistCtx",
                 ioProxy: "IoProxyBram",
                 src: MemoryAllocationMeta,
                 cmdNode: HlsNetNodeWriteMemoryAllocationCmd,
                 dtype: Optional[HdlType]=None,
                 name:Optional[str]=None):
        super().__init__(netlist, ioProxy, None, dtype, name=name, addPortDataOut=True)
        self.src = src
        self.cmdNode = cmdNode

    def getRtlDataSig(self):
        meta: "ComponentGeneratorMemoryMeta" = self.src.dataOfComponentGenerator
        return meta.rtlInstance.port[self.src.users.index(self.cmdNode)].dout

# class HlsNetNodeWriteMemoryAllocation(HlsNetNodeWriteIndexed):
#    """
#    Write to memory which is now represented just by MemoryAllocationMeta
#    """
#
#    def __init__(self, netlist:"HlsNetlistCtx", dst:MemoryAllocationMeta,
#                 mayBecomeFlushable=False,
#                 name:Optional[str]=None,
#                 addSrcPort=True):
#        HlsNetNodeWriteIndexed.__init__(self, netlist, dst,
#                                 mayBecomeFlushable=mayBecomeFlushable,
#                                 name=name,
#                                 addSrcPort=addSrcPort)
#        dst.users.append(self)
#        self._portDataOut = None  # for compatibility with HlsNetNodeWriteBramCmd
#        self._rtlUseValid = True
#
#    @override
#    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
#        y, isNew = HlsNetNodeWriteIndexed.clone(self, memo, keepTopPortsConnected)
#        if isNew:
#            self.dst.users.append(y)
#
#        return y, isNew
#
#    @override
#    def markAsRemoved(self):
#        HlsNetNodeWriteIndexed.markAsRemoved(self)
#        self.dst.users.remove(self)
#
#    @override
#    def rtlAlloc(self, allocator: "ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
#        return self.netlist.platform._componentGenerators[MemoryAllocationMeta].rtlAllocOfNode(allocator, self)

