from enum import Enum
import math
from typing import Union, List, Optional

from hwt.constants import WRITE, READ
from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.statements.statement import HdlStatement
from hwt.hwModule import HwModule
from hwt.mainBases import RtlSignalBase
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF,\
    ResourceRAM
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.io.bram import HlsNetNodeWriteBramCmd
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.memoryAllocationMeta import  MemoryAllocationMeta
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.scheduler.clk_math import epsilon
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from hwtLib.mem.ram import RamSingleClock
from hwtLib.mem.ramXor import RamXorSingleClock
from hwtHls.netlist.nodes.memoryAllocationMetaNode import HlsNetNodeReadMemoryAllocationReadData, \
    HlsNetNodeWriteMemoryAllocationCmd


class ComponentGeneratorMemoryAllocationImplementationType(Enum):
    DISTMEM_INLINED = "DISTMEM_INLINED" # inlined as an array in HDL
    DISTMEM = "DISTMEM"
    DISTMEM_LVT = "DISTMEM_LVT" # distmem with Live Value Table (type of multi write port memory)
    BRAM = "BRAM"
    BRAM_XOR = "BRAM_XOR" # Bram with XOR implementation of multi write port memory


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


MEM_ALOCATION_NODE = Union[HlsNetNodeReadMemoryAllocationReadData,
                                                  HlsNetNodeWriteMemoryAllocationCmd]


class ComponentGeneratorMemory(ComponentGenerator):
    """
    This provides scheduling info for memories which were requested from HLS side
    and user did not specify any concrete memory instance/port.

    Depending on available LUT sizes and BRAM sizes pick the best fitting memory.
    """

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeWriteMemoryAllocationCmd):
        platform:"VirtualHlsPlatform" = self.platform
        rPortCnt = 0
        wPortCnt = 0
        isRead = node.cmd is READ
        mem: MemoryAllocationMeta = node.dst
        for ioNode in mem.users:
            assert isinstance(ioNode, HlsNetNodeWriteMemoryAllocationCmd), ioNode
            ioNode: HlsNetNodeWriteMemoryAllocationCmd
            if ioNode.cmd is READ:
                rPortCnt += 1
            else:
                assert ioNode.cmd is WRITE, ioNode
                wPortCnt += 1

        # https://docs.amd.com/v/u/en-US/ug474_7Series_CLB
        lutInputBits = platform.get_lut_inputs_max()
        assert rPortCnt > 0, ("local memories which are never read should have already been removed", node)
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
        bramDelay = netlist.platform.get_op_realization(ResourceRAM, None, 1, 1, realTimeClkPeriod)
        ffDelay = netlist.platform.get_op_realization(ResourceFF, None, 1, 1, realTimeClkPeriod)

        inputWireDelay = ffDelay.inputWireDelay
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
                if wPortCnt == 1:
                    impl = ComponentGeneratorMemoryAllocationImplementationType.DISTMEM
                    inputWireDelay = depthOfLutTree * lutDelay

                else:
                    assert wPortCnt > 1, wPortCnt
                    # use LVT (Live Value Table Multi-Port RAM), add delay of output mux and register array
                    impl = ComponentGeneratorMemoryAllocationImplementationType.DISTMEM_LVT
                    liveArrayDelay = platform.get_op_realization(HwtOps.TERNARY, None, 1, items, realTimeClkPeriod)
                    outMuxDelay = platform.get_op_realization(HwtOps.TERNARY, None, 1, wPortCnt, realTimeClkPeriod)
                    inputWireDelay = depthOfLutTree * lutDelay + liveArrayDelay + outMuxDelay
            else:
                # implement using bram
                # :see: :class:`hwtLib.mem.ramXor.RamXorSingleClock`
                inputWireDelay = bramDelay.inputWireDelay
                if wPortCnt <= 1:
                    # native true dualport ram
                    impl = ComponentGeneratorMemoryAllocationImplementationType.BRAM
                    rLatency = 1
                    outputWireDelay = bramDelay.outputWireDelay + epsilon
                else:
                    # XOR memory
                    impl = ComponentGeneratorMemoryAllocationImplementationType.BRAM_XOR
                    rLatency = wPortCnt - 1
                    outputWireDelay = bramDelay.outputWireDelay + lutDelay  # final XOR
        else:
            # ROM
            assert isRead, node
            assert lutInputBits > 1
            itemsPerLUT = 1 << (lutInputBits - 1)
            if items < smallestBram // 2:
                # implement using distmem
                depthOfLutTree = math.ceil(math.log(items, itemsPerLUT))
                impl = ComponentGeneratorMemoryAllocationImplementationType.DISTMEM_INLINED

            else:
                # implement using bram
                inputWireDelay = bramDelay.inputWireDelay
                rLatency = 1
                outputWireDelay = bramDelay.outputWireDelay + epsilon
                impl = ComponentGeneratorMemoryAllocationImplementationType.BRAM
                if items > largestBram:
                    bramGroups = math.ceil(items / largestBram)
                    # [todo] there are column connections which can have lower delay
                    outputWireDelay += platform.get_op_realization(HwtOps.TERNARY, None, 1, bramGroups, realTimeClkPeriod).inputWireDelay
            

        mem.dataOfComponentGenerator = ComponentGeneratorMemoryMeta(impl, rPortCnt, wPortCnt)

        # assign realization to all users of this memory
        rRealization = None
        wRealization = None
        meta:ComponentGeneratorMemoryMeta = mem.dataOfComponentGenerator  
        for memUser in mem.users:
            memUser:MEM_ALOCATION_NODE
            if memUser.cmd == READ:
                if rRealization is None:
                    rRealization = OpRealizationMeta(
                        inputWireDelay=inputWireDelay,
                        inputClkTickOffset=0,
                        outputWireDelay=outputWireDelay,
                        outputClkTickOffset=(rLatency, *(0 for _ in range(len(memUser._outputs) - 1)))
                    )
                memUser.assignRealization(rRealization)
                if impl == ComponentGeneratorMemoryAllocationImplementationType.DISTMEM_INLINED:
                    memUser._rtlUseValid = False # do not use "bramport.en" for inlined ROMs
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
                       node: MEM_ALOCATION_NODE) -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        isRead = node.cmd is READ
        mem: MemoryAllocationMeta = node.dst
        meta:ComponentGeneratorMemoryMeta = mem.dataOfComponentGenerator
        netlist: HlsNetlistCtx = node.netlist
        if meta.rtlInstance is None and meta.rtlMemSignal is None:
            # the memory is not allocated yet
            if meta.implementation == ComponentGeneratorMemoryAllocationImplementationType.DISTMEM_INLINED:
                # inline this memory as a constant signal
                assert mem.initValue is not None, mem
                assert not node._rtlUseValid, node
                assert not node._rtlUseReady, node
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
                memInst.PORT_CNT = tuple(u.cmd for u in mem.users)
                memInst.ADDR_WIDTH = log2ceil(mem.dtype.size)
                memInst.DATA_WIDTH = mem.dtype.element_t.bit_length()
                init = mem.initValue
                memInst.INIT_DATA = None if init is None else\
                                    init if isinstance(init, HConst) else\
                                    tuple(init)
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
            addSig = _addr.data
            curentAddrWidth = addSig._dtype.bit_length()
            if curentAddrWidth != ADDR_WIDTH:
                assert curentAddrWidth > 1
                addSig = _addr.data[ADDR_WIDTH:]
                
            dataRtl = meta.rtlMemSignal[addSig]

            _data = allocator.rtlRegisterOutputRtlSignal(r_out, dataRtl, False, False, False)
            return _data
        else:
            raise NotImplementedError(node, meta)
