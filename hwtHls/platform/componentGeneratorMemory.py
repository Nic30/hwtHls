from enum import Enum
import math
from typing import Union, List, Optional

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.typingFuture import override
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF
from hwtHls.netlist.nodes.memoryAllocationMeta import HlsNetNodeReadMemoryAllocation, \
    HlsNetNodeWriteMemoryAllocation, MemoryAllocationMeta
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import epsilon
from hwtHls.platform.componentGenerator import ComponentGenerator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwt.hdl.statements.statement import HdlStatement
from hwt.hwModule import HwModule
from hwt.mainBases import RtlSignalBase
from hwtLib.mem.ram import RamSingleClock
from hwtHls.netlist.nodes.readIndexed import HlsNetNodeReadIndexed
from hwtHls.netlist.nodes.writeIndexed import HlsNetNodeWriteIndexed
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtLib.mem.ramXor import RamXorSingleClock
from hwt.constants import WRITE, READ
from hwt.math import log2ceil
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.io.bram import HlsNetNodeWriteBramCmd
from itertools import chain


class ComponentGeneratorMemoryAllocationImplementationType(Enum):
    DISTMEM = "DISTMEM"
    DISTMEM_LVT = "DISTMEM_LVT"
    BRAM = "BRAM"
    BRAM_XOR = "BRAM_XOR"


class ComponentGeneratorMemoryMeta():
    """
    :ivar rtlMemSignal: RtlSignal instance if the ROM was inlined into main circuit code
    :ivar rtlInstance: instance of HwModule which is implementing this memory
    """

    def __init__(self, implementation: ComponentGeneratorMemoryAllocationImplementationType, readPortCnt: int, writePortCnt: int):
        self.implementation = implementation
        self.readPortCnt = readPortCnt
        self.writePortCnt = writePortCnt
        self.rtlMemSignal: Optional[RtlSignalBase] = None
        self.rtlInstance: Optional[HwModule] = None


class ComponentGeneratorMemory(ComponentGenerator):
    """
    This provides scheduling info for memories which were requested from HLS side
    and user did not specify any concrete memory instance/port.

    Depending on available LUT sizes and BRAM sizes pick the best fitting memory.
    """

    @override
    def resolveRealizationOfNode(self, node:Union[HlsNetNodeReadMemoryAllocation,
                                                  HlsNetNodeWriteMemoryAllocation]):
        platform:"VirtualHlsPlatform" = self.platform
        rPortCnt = 0
        wPortCnt = 0
        isRead = isinstance(node, HlsNetNodeRead)
        mem: MemoryAllocationMeta = node.src if isRead else node.dst
        for ioNode in mem.users:
            if isinstance(ioNode, HlsNetNodeRead):
                rPortCnt += 1
            else:
                assert isinstance(ioNode, HlsNetNodeWrite), ioNode
                wPortCnt += 1

        # https://docs.amd.com/v/u/en-US/ug474_7Series_CLB
        lutInputBits = platform.get_lut_inputs_max()
        assert rPortCnt > 0, node
        items = mem.dtype.size
        smallestBram = platform._BRAM_GEOMETRIES[0][0]
        largestBram = platform._BRAM_GEOMETRIES[-1][0]
        # having multiple read ports generates memories in parallel (resource consumption grows linearly, the delay is the same)
        # having multiple write ports requires special care:
        # * BRAMs are natively true dual port memories
        # * XOR, LVT, multipumped, banked and similar multiport memory implementations
        #   are used to build a more memory ported memories from memories available.
        #   https://doi.org/10.1145/2145694.2145730
        #   https://doi.org/10.1145/2629629
        #   https://tomverbeure.github.io/2019/08/03/Multiport-Memories.html
        netlist = node.netlist
        realTimeClkPeriod = netlist.realTimeClkPeriod
        lutDelay = platform.get_op_realization(HwtOps.AND, None, 1, 2, realTimeClkPeriod).inputWireDelay
        if not isinstance(lutDelay, (int, float)):
            lutDelay = lutDelay[0]
        assert lutDelay > 0
        bramDelay = netlist.platform.get_op_realization(ResourceFF, None, 1, 1, realTimeClkPeriod).inputWireDelay * 2

        inputWireDelay = 0
        outputWireDelay = 0
        rLatency = 0

        if wPortCnt > 0:
            # RAM
            assert lutInputBits > 2  # (1b for WA, 1b for data in)
            # e.g. 32 for LUT-7
            itemsPerLUT = 1 << (lutInputBits - 2)
            if items < smallestBram // 2:
                # use distmem (LUT)
                depthOfLutTree = math.ceil(math.log(items, itemsPerLUT))
                if wPortCnt <= 1:
                    impl = ComponentGeneratorMemoryAllocationImplementationType.DISTMEM
                    inputWireDelay = depthOfLutTree * lutDelay

                else:
                    # use LVT (Live Value Table Multi-Port RAM), add delay of output mux and register array
                    impl = ComponentGeneratorMemoryAllocationImplementationType.DISTMEM_LVT
                    liveArrayDelay = platform.get_op_realization(HwtOps.TERNARY, None, 1, items, realTimeClkPeriod)
                    outMuxDelay = platform.get_op_realization(HwtOps.TERNARY, None, 1, wPortCnt, realTimeClkPeriod)
                    inputWireDelay = depthOfLutTree * lutDelay + liveArrayDelay + outMuxDelay
            else:
                # implement using bram
                # :see: :class:`hwtLib.mem.ramXor.RamXorSingleClock`
                if wPortCnt <= 1:
                    # native true dualport ram
                    impl = ComponentGeneratorMemoryAllocationImplementationType.BRAM
                    rLatency = 1
                    inputWireDelay = bramDelay
                    outputWireDelay = epsilon
                else:
                    # XOR memory
                    impl = ComponentGeneratorMemoryAllocationImplementationType.BRAM_XOR
                    rLatency = wPortCnt - 1
                    outputWireDelay = lutDelay  # final XOR
        else:
            # ROM
            assert isRead, node
            assert lutInputBits > 1
            itemsPerLUT = 1 << (lutInputBits - 1)
            if items < smallestBram // 2:
                # implement using distmem
                depthOfLutTree = math.ceil(math.log(items, itemsPerLUT))
                impl = ComponentGeneratorMemoryAllocationImplementationType.DISTMEM

            else:
                # implement using bram
                inputWireDelay = bramDelay,
                rLatency = 1
                outputWireDelay = epsilon
                impl = ComponentGeneratorMemoryAllocationImplementationType.BRAM
                if items > largestBram:
                    bramGroups = math.ceil(items / largestBram)
                    outputWireDelay += platform.get_op_realization(HwtOps.TERNARY, None, 1, bramGroups, realTimeClkPeriod)

        mem.dataOfComponentGenerator = ComponentGeneratorMemoryMeta(impl, rPortCnt, wPortCnt)

        # assign realization to all users of this memory
        rRealization = None
        wRealization = None
        for memUser in mem.users:
            memUser:Union[HlsNetNodeReadMemoryAllocation,
                          HlsNetNodeWriteMemoryAllocation]
            if isinstance(memUser, HlsNetNodeRead):
                if rRealization is None:
                    rRealization = OpRealizationMeta(
                        inputWireDelay=inputWireDelay,
                        inputClkTickOffset=0,
                        outputWireDelay=outputWireDelay,
                        outputClkTickOffset=(rLatency, *(0 for _ in range(len(memUser._outputs) - 1)))
                    )
                memUser.assignRealization(rRealization)
            else:
                if wRealization is None:
                    wRealization = OpRealizationMeta(
                        inputWireDelay=inputWireDelay,
                        inputClkTickOffset=0,
                        outputWireDelay=0,
                        outputClkTickOffset=0
                    )
                memUser.assignRealization(wRealization)

    @override
    def rtlAllocOfNode(self, allocator: "ArchElement",
                       node: Union[HlsNetNodeReadMemoryAllocation,
                                   HlsNetNodeWriteMemoryAllocation]) -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        isRead = isinstance(node, HlsNetNodeRead)
        mem = node.src if isRead else node.dst
        mem: MemoryAllocationMeta
        meta:ComponentGeneratorMemoryMeta = mem.dataOfComponentGenerator
        netlist: HlsNetlistCtx = node.netlist
        if meta.rtlInstance is None and meta.rtlMemSignal is None:
            # the memory is not allocated yet
            if meta.writePortCnt == 0 and all(t == 0  for t in chain(node.inputClkTickOffset, node.outputClkTickOffset)):
                # inline this memory as a constant signal
                assert mem.initValue is not None, mem
                s = allocator._sig(mem.name, mem.dtype, def_val=mem.initValue)
                s._const = True
                meta.rtlMemSignal = s
            else:
                if meta.implementation == ComponentGeneratorMemoryAllocationImplementationType.DISTMEM:
                    memInst = RamSingleClock()
                    memInst.READ_LATENCY = 0

                elif meta.implementation == ComponentGeneratorMemoryAllocationImplementationType.DISTMEM_LVT:
                    raise NotImplementedError()
                elif meta.implementation == ComponentGeneratorMemoryAllocationImplementationType.BRAM:
                    memInst = RamSingleClock()
                    memInst.READ_LATENCY = 1
                elif meta.implementation == ComponentGeneratorMemoryAllocationImplementationType.BRAM_XOR:
                    memInst = RamXorSingleClock()
                else:
                    raise NotImplementedError(meta.implementation)
                memInst.PORT_CNT = tuple(READ if isinstance(u, HlsNetNodeRead) else WRITE for u in mem.users)
                memInst.ADDR_WIDTH = log2ceil(mem.dtype.size)
                memInst.DATA_WIDTH = mem.dtype.element_t.bit_length()
                memInst.INIT_DATA = tuple(mem.initValue)
                compBuilder = AbstractComponentBuilder(netlist.parentHwModule, None, netlist.namePrefix)
                name = compBuilder._findSuitableName(mem.name, firstWithoutCntrSuffix=True)
                setattr(netlist.parentHwModule, name, memInst)
                compBuilder._propagateClkRstn(memInst)
                meta.rtlInstance = memInst

        if meta.rtlInstance is not None:
            memRtl: RamSingleClock = meta.rtlInstance
            ioPort = memRtl.port[mem.users.index(node)]
            if isRead:
                return HlsNetNodeWriteBramCmd._rtlAlloc(node, allocator, READ, ioPort)
            else:
                return HlsNetNodeWriteBramCmd._rtlAlloc(node, allocator, WRITE, ioPort)

        elif meta.rtlMemSignal is not None:
            assert isRead, (node, "This should be used inly in the case of small ROM")
            assert not node._rtlUseValid, node
            assert not node._rtlUseReady, node
            for sync, time in zip(node.dependsOn, node.scheduledIn):
                if HdlType_isVoid(sync._dtype):
                    continue
                assert isinstance(sync, HlsNetNodeOut), (node, node.dependsOn)
                # prepare sync inputs but do not connect it because we do not implement synchronization
                # in this step we are building only data path
                allocator.rtlAllocHlsNetNodeOutInTime(sync, time)

            addrInPort = node.indexes[0]
            addr = node.dependsOn[addrInPort.in_i]
            r_out = node._portDataOut
            _addr = allocator.rtlAllocHlsNetNodeOutInTime(addr, node.scheduledIn[addrInPort.in_i])
            # [todo] llvm MIR lefts bits which are sliced out
            ADDR_WIDTH = log2ceil(mem.dtype.size)
            dataRtl = meta.rtlMemSignal[_addr.data[ADDR_WIDTH:]]

            _data = allocator.rtlRegisterOutputRtlSignal(r_out, dataRtl, False, False, False)
            return _data
        else:
            raise NotImplementedError(node, meta)
