
from typing import Union, Literal, List, Optional, Sequence, Callable

from hwt.constants import NOT_SPECIFIED
from hwt.constants import WRITE, READ
from hwt.hdl.const import HConst
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.std import HwIOBramPort_noClk, HwIOSignal
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ioProxyAddressed import IoProxyAddressed
from hwtHls.frontend.ioUtils import ANY_SCALAR_INT_VALUE
from hwtHls.frontend.pyBytecode import hlsLowLevel
from hwtHls.frontend.statementsRead import HlsReadAddressed
from hwtHls.frontend.statementsWrite import HlsWriteAddressed
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup, \
    isInstanceOfInterfacePort, getFirstInterfaceInstance
from hwtHls.llvm.llvmIr import Register, MachineInstr, Value, HwtHlsIoMetadata
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering, HVoidData
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.memoryAllocationMeta import MemoryAllocationMeta
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, \
    HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readIndexed import HlsNetNodeReadIndexed
from hwtHls.netlist.nodes.schedulableNode import OutputMinUseTimeGetter
from hwtHls.netlist.nodes.writeIndexed import HlsNetNodeWriteIndexed
from hwtHls.netlist.scheduler.clk_math import epsilon, indexOfClkPeriod, \
    beginOfNextClk
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtLib.handshaked.streamNode import ValidReadyTuple
from ipCorePackager.constants import INTF_DIRECTION

AnyBramPort = Union[HwIOBramPort_noClk, BankedPortGroup[HwIOBramPort_noClk], MultiPortGroup[HwIOBramPort_noClk], MemoryAllocationMeta]


class HlsNetNodeWriteBramCmd(HlsNetNodeWriteIndexed):
    """
    A netlist node which is used to represent read or write command to/from BRAM port.
    """
    _PORT_ATTR_NAMES = HlsNetNodeWriteIndexed._PORT_ATTR_NAMES + ["_portDataOut"]

    def __init__(self, netlist:"HlsNetlistCtx",
                 ioProxy: "IoProxyBram",
                 dst: Optional[AnyBramPort],
                 cmd: Literal[READ, WRITE],
                 dtype:Optional[HBits]=None,
                 hasR: Optional[bool]=None,
                 hasW: Optional[bool]=None,
                 mayBecomeFlushable=False,
                 name=None):
        self.dst = dst
        if dst is None:
            assert dtype is not None
            assert hasR is not None
            assert hasW is not None
        else:
            _dst = self._getNominaInterface()
            if hasR is None:
                hasR = _dst.HAS_R
            if hasW is None:
                hasW = _dst.HAS_W

        HlsNetNodeWriteIndexed.__init__(self, netlist, ioProxy, dst, mayBecomeFlushable=mayBecomeFlushable,
                                        addSrcPort=hasW, name=name)
        self._rtlUseValid = True  # en is form of valid
        assert cmd is READ or cmd is WRITE, cmd
        self.cmd = cmd

        self._portDataOut: Optional[HlsNetNodeOut] = None
        if hasR:
            if dtype is None:
                _dst = self._getNominaInterface()
                dtype = _dst.dout._dtype
            self._portDataOut = self._addOutput(dtype, "dout")

        if cmd == READ:
            assert hasR, dst
            # set write data to None
        else:
            assert cmd == WRITE, cmd
            assert hasW, dst

    @override
    def _removeOutput(self, index:int):
        dout = self._portDataOut
        if dout is not None and dout.out_i == index:
            self._portDataOut = None
        return HlsNetNodeWriteIndexed._removeOutput(self, index)

    def _getNominaInterface(self):
        return getFirstInterfaceInstance(self.dst)

    @override
    def scheduleAlapCompaction(self, endOfLastClk: int,
                               outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                               excludeNode: Optional[Callable[[HlsNetNode], bool]]):
        return HlsNetNodeWriteIndexed.scheduleAlapCompaction(self, endOfLastClk, outputMinUseTimeGetter, excludeNode)

    @override
    def resolveRealization(self):
        netlist = self.netlist
        ffdelay = netlist.platform.get_op_realization(ResourceFF, None, 1, 1, netlist.realTimeClkPeriod).inputWireDelay * 2
        isRead = self.cmd is READ
        re = OpRealizationMeta(
            inputWireDelay=ffdelay,
            inputClkTickOffset=0,
            outputWireDelay=epsilon if isRead else 0,
            outputClkTickOffset=(1, *(0 for _ in range(len(self._outputs) - 1))) if isRead else 0
        )
        self.assignRealization(re)

    @classmethod
    def _extractDout(cls, port: AnyBramPort):
        if isinstance(port, (MultiPortGroup, BankedPortGroup)):
            return port.__class__(cls._extractDout(_port) for _port in port)
        else:
            return port.dout

    @override
    def splitOnClkWindows(self):
        """
        Keep command/write part in this node and extract out data read port if it is in later clock window
        """
        if self.isMulticlock:
            _dst = self._getNominaInterface()
            if _dst.HAS_R:
                readDataIo = self._extractDout(self.dst)

                dNode = HlsNetNodeReadBramData(self.netlist, self.ioProxy, readDataIo, _dst.dout._dtype, name=self.name)
                self._extractReadPortsToSeparateNode(dNode)
                yield dNode

    def _extractReadPortsToSeparateNode(self, dNode: "HlsNetNodeReadBramData"):
        dNode.assignRealization(OpRealizationMeta(0, 0, 0, 0, True))
        dOut = self._portDataOut
        dTime = self.scheduledOut[dOut.out_i]
        dNode._setScheduleZeroTimeSingleClock(dTime)
        self.parent.addNode(dNode)
        clkIndex = indexOfClkPeriod(dTime, self.netlist.normalizedClkPeriod)
        self.parent._addNodeIntoScheduled(clkIndex, dNode, allowNewClockWindow=True)

        builder: HlsNetlistBuilder = self.getHlsNetlistBuilder()
        builder.replaceOutput(dOut, dNode._portDataOut, True)
        self._removeOutput(dOut.out_i)
        nextClkBegin = beginOfNextClk(self.scheduledZero, self.netlist.normalizedClkPeriod)
        for i, t in zip(self._inputs, self.scheduledIn):
            assert t < nextClkBegin, i
        for o, t in zip(self._outputs, self.scheduledOut):
            assert t < nextClkBegin, (o, t, nextClkBegin)

        self.isMulticlock = False

    def _rtlAlloc(self, allocator: "ArchElement", cmd: Literal[READ, WRITE], ram: HwIOBramPort_noClk) -> List[HdlStatement]:
        """
        Instantiate command write operation on RTL level
        """
        assert not self._isRtlAllocated, self
        for sync, t in zip(self.dependsOn, self.scheduledIn):
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only datapath
            if sync._dtype != HVoidOrdering:
                allocator.rtlAllocHlsNetNodeOutInTime(sync, t)

        assert not isinstance(ram, (MultiPortGroup, BankedPortGroup)), (self, ram,
            "If this was an operation with a group of ports the individual ports should have already been assigned")
        en = ram.en
        if en._sig._nop_val is NOT_SPECIFIED:
            en._sig._nop_val = en._sig._dtype.from_py(0)
        if ram.HAS_W:
            # we can still does not have to be present, it can be replaced by just en on write only ports
            we = getattr(ram, "we", None)
            if we is not None and we._sig._nop_val is NOT_SPECIFIED:
                we._sig._nop_val = we._sig._dtype.from_py(0)

        addrInPort = self.indexes[0]
        addr = self.dependsOn[addrInPort.in_i]

        hasWData = self._portSrc is not None
        if hasWData:
            wData = self.dependsOn[self._portSrc.in_i]
            key = (ram, addr, wData)
        else:
            key = (ram, addr)

        if self._dataVoidOut is not None:
            HlsNetNodeReadIndexed._rtlAllocDataVoidOut(self, allocator)
        if hasWData:
            _wData = allocator.rtlAllocHlsNetNodeOutInTime(wData, self.scheduledIn[0])
        _addr = allocator.rtlAllocHlsNetNodeOutInTime(addr, self.scheduledIn[addrInPort.in_i])

        rtlObj = [
            # [todo] llvm MIR lefts bits which are sliced out
            ram.addr(_addr.data)
            if ram.addr._dtype.bit_length() == _addr.data._dtype.bit_length() else
            ram.addr(_addr.data[ram.ADDR_WIDTH:])
        ]
        if ram.HAS_W:
            if hasWData:
                if ram.HAS_BE:
                    rtlObj.append(ram.din(_wData.data[ram.DATA_WIDTH:]))
                    rtlObj.append(ram.we(_wData.data[:ram.DATA_WIDTH:]))
                else:
                    rtlObj.append(ram.din(_wData.data))
            if not (hasWData and ram.HAS_BE):
                we = getattr(ram, "we", None)
                if we is not None:
                    rtlObj.append(ram.we(0 if cmd is READ else 1))

        allocator.netNodeToRtl[key] = rtlObj
        if self._portDataOut is not None:
            assert ram.HAS_R, self
            allocator.rtlRegisterOutputRtlSignal(self._portDataOut, ram.dout, False, False, False)

        clkI = indexOfClkPeriod(self.scheduledIn[addrInPort.in_i], allocator.netlist.normalizedClkPeriod)
        allocator._rtlAllocDatapathIo(ram, self, ram.en, allocator.connections[clkI], rtlObj)
        self._isRtlAllocated = True

        return rtlObj

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> List[HdlStatement]:
        ram: HwIOBramPort_noClk = self.dst
        # [0] - data, [1] - addr, [2:] control dependencies
        assert len(self.dependsOn) >= 2, self.dependsOn
        return self._rtlAlloc(allocator, self.cmd, ram)

    def __repr__(self, minify=False):
        src = self.dependsOn[0]
        dstName = None if self.dst is None else self._getInterfaceName(self.dst)
        if dstName is None:
            dstName = "None"
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.cmd} {dstName:s}>"
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.cmd} {dstName:s}{HlsNetNodeReadIndexed._strFormatIndexes(self.indexes)} <- {src}>"


class HlsNetNodeReadBramData(HlsNetNodeRead):
    pass


class HlsReadBram(HlsReadAddressed):

    def __init__(self,
                 ioProxy: "IoProxyBram",
                 src:AnyBramPort,
                 index:ANY_SCALAR_INT_VALUE,
                 element_t:HdlType,
                 isBlocking:bool,
                 isVolatile:bool,
                 hwIOName: Optional[str]=None):

        if isinstance(src, MultiPortGroup):
            _src = MultiPortGroup(i for i in src if i.HAS_R)
            if len(_src) != len(src):
                src = _src  # reuse original object if all have HAS_R
            if len(src) == 1:
                src = src[0]
            else:
                assert src
        elif isinstance(src, BankedPortGroup):
            raise NotImplementedError()
        else:
            assert src.HAS_R
        HlsReadAddressed.__init__(self, ioProxy, src, index, element_t, isBlocking, isVolatile, hwIOName=hwIOName)

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name")
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {self._name:s}[{self.operands[0]}], {t}>"


class HlsWriteBram(HlsWriteAddressed):

    def __init__(self,
            ioProxy: "IoProxyBram",
            src:Union[Value, RtlSignal, HConst],
            dst:AnyBramPort,
            index:Union[Value, RtlSignal, HConst],
            element_t:HdlType,
            isVolatile:bool,
            mayBecomeFlushable=True):

        if isinstance(dst, MultiPortGroup):
            _dst = MultiPortGroup(i for i in dst if i.HAS_W)
            if len(_dst) != len(dst):
                dst = _dst  # resuse original object if all have HAS_W
            if len(dst) == 1:
                dst = dst[0]
            else:
                assert dst
        elif isinstance(dst, BankedPortGroup):
            raise NotImplementedError(dst)
        else:
            assert isinstance(dst, HwIOBramPort_noClk), dst
            assert dst.HAS_W, dst

        HlsWriteAddressed.__init__(self, ioProxy, src, dst, index, element_t, isVolatile, mayBecomeFlushable=mayBecomeFlushable)


class IoProxyBram(IoProxyAddressed):

    def __init__(self, hls:"HlsScope", interface:AnyBramPort, dtype:Optional[HdlType]=None):
        if isinstance(interface, MemoryAllocationMeta):
            addrType = HBits(log2ceil(interface.dtype.size))
        else:
            if isinstance(interface, (MultiPortGroup, BankedPortGroup)):
                i = interface[0]
            else:
                i = interface

            assert i._direction != INTF_DIRECTION.MASTER, (
                self.__class__, "this supports only slave interfaces,"
                " because this is intended for mapping of IO to HLS as an array", interface)

            assert isInstanceOfInterfacePort(i, HwIOBramPort_noClk), i
            assert i.HAS_W or i.HAS_R, ("Must have at least one (read/write)", interface)
            addrType = i.addr._dtype

        IoProxyAddressed.__init__(self, hls, interface, dtype=dtype)
        self.indexT = addrType

    READ_CLS = HlsReadBram
    WRITE_CLS = HlsWriteBram

    @override
    @hlsLowLevel
    def write(self, index: Union[AnyHBitsValue], data: AnyHBitsValue, mask=NOT_SPECIFIED, isVolatile:bool=True, mayBecomeFlushable=True) -> HlsWriteAddressed:
        if self.interface.HAS_BE:
            assert mask is not None
            data = mask._concat(data)

        return self.WRITE_CLS(self,
                              data,
                              self.interface,
                              index,
                              self.getDataTypeOfNativeWrite(),
                              isVolatile=isVolatile,
                              mayBecomeFlushable=mayBecomeFlushable
                              )

    @override
    def getDataWordType(self):
        dtype = self._nativeDataWordTy
        if dtype is None:
            i = getFirstInterfaceInstance(self.interface)
            if i.HAS_W:
                dtype = i.din._dtype
            else:
                assert i.HAS_R, i
                dtype = i.dout._dtype
            self._nativeDataWordTy = dtype
        return dtype

    @override
    def getDataTypeOfNativeWrite(self) -> HdlType:
        dtype = self._nativeWriteTy
        if dtype is None:
            i = getFirstInterfaceInstance(self.interface)
            if not i.HAS_W:
                dtype = HVoidData
            else:
                dtype = i.din._dtype
                if i.HAS_BE:
                    dtype = HStruct(
                        (dtype, "data"),
                        (HBits(dtype.bit_length() // 8), "mask")
                    )

            self._nativeWriteTy = dtype
        return dtype

    @override
    def getDataTypeOfNativeRead(self) -> HdlType:
        dtype = self._nativeReadTy
        if dtype is None:
            i = getFirstInterfaceInstance(self.interface)
            if not i.HAS_R:
                dtype = HVoidData
            else:
                dtype = i.dout._dtype

            self._nativeReadTy = dtype
        return dtype

    @override
    def _translateMirToNetlist_HWTFPGA_CLOAD(self,
                               mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                               mbMeta: MachineBasicBlockMeta,
                               instr: MachineInstr,
                               srcIo: AnyBramPort,
                               srcIoMd: HwtHlsIoMetadata,
                               index: Union[int, HlsNetNodeOutAny],
                               cond: Optional[HlsNetNodeOutAny],
                               instrDstReg: Register) -> Sequence[HlsNetNode]:
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, HwIOBramPort_noClk) or (isinstance(srcIo, MultiPortGroup) and isinstance(srcIo[0], HwIOBramPort_noClk)), srcIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", srcIo, instr)

        n = HlsNetNodeWriteBramCmd(netlist, self, srcIo, READ)
        mbMeta.parentElement.addNode(n)
        mbMeta.addOrderedNode(n)

        _io = n._getNominaInterface()
        if _io.HAS_W:
            xWrData = HlsNetNodeConst(netlist, _io.dout._dtype.from_py(None))
            mbMeta.parentElement.addNode(xWrData)
            xWrData._outputs[0].connectHlsIn(n._inputs[0])
        index.connectHlsIn(n.indexes[0])

        mirToNetlist._addExtraCond(n, cond, None)
        mirToNetlist._addSkipWhen_n(n, cond, None)

        valCache.add(mbMeta.block, instrDstReg, n._portDataOut, True)
        return [n, ]

    @override
    def _translateMirToNetlist_HWTFPGA_CSTORE(self,
            mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
            mbMeta: MachineBasicBlockMeta,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: AnyBramPort,
            dstIoMd: HwtHlsIoMetadata,
            index: Union[int, HlsNetNodeOutAny],
            cond: Optional[HlsNetNodeOutAny],
            bufferCapacity: Optional[int]) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`~.IoProxy._translateMirToNetlist_HWTFPGA_CLOAD`
        """
        assert bufferCapacity == bufferCapacity, (dstIo, bufferCapacity)
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        isInstanceOfInterfacePort(dstIo, HwIOBramPort_noClk)
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", dstIo, instr)

        n = HlsNetNodeWriteBramCmd(netlist, self, dstIo, WRITE)
        mbMeta.parentElement.addNode(n)
        srcVal.connectHlsIn(n._portSrc)
        index.connectHlsIn(n.indexes[0])

        # _cond = mbMeta.syncTracker.resolveControlOutput(cond)
        _cond = cond
        mirToNetlist._addExtraCond(n, _cond, None)
        mirToNetlist._addSkipWhen_n(n, _cond, None)
        mbMeta.addOrderedNode(n)
        return [n, ]

    @override
    @classmethod
    def _getRtlSyncSignals(cls,
                hwIO: Union[HwIOBramPort_noClk, HwIOSignal],
                formatAsValidReadyTuple: bool=False,
                ) -> Union[ValidReadyTuple, tuple[Union[RtlSignal, Literal[1]], Union[RtlSignal, Literal[1]]]]:
        if isinstance(hwIO, HwIOBramPort_noClk):
            if formatAsValidReadyTuple:
                return (hwIO.en, 1)
            else:
                return (hwIO.en,)
        elif isinstance(hwIO, HwIOSignal):
            # case of direct read of dout
            if formatAsValidReadyTuple:
                return (1, 1)
            else:
                return ()
        else:
            raise NotImplementedError(hwIO)
