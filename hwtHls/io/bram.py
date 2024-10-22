
from typing import Union, Literal, List, Optional, Sequence, Callable

from hwt.constants import NOT_SPECIFIED
from hwt.constants import WRITE, READ
from hwt.hdl.const import HConst
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIOs.std import HwIOBramPort_noClk
from hwt.pyUtils.typingFuture import override
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statementsRead import HlsReadAddressed
from hwtHls.frontend.ast.statementsWrite import HlsWriteAddressed
from hwtHls.frontend.ast.utils import ANY_SCALAR_INT_VALUE
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup, \
    isInstanceOfInterfacePort, getFirstInterfaceInstance
from hwtHls.llvm.llvmIr import LoadInst, Register
from hwtHls.llvm.llvmIr import MachineInstr
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.const import HlsNetNodeConst
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
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.ssa.value import SsaValue

AnyBramPort = Union[HwIOBramPort_noClk, BankedPortGroup[HwIOBramPort_noClk], MultiPortGroup[HwIOBramPort_noClk]]


class HlsNetNodeWriteBramCmd(HlsNetNodeWriteIndexed):
    """
    A netlist node which is used to represent read or write command to/from BRAM port.
    """
    _PORT_ATTR_NAMES = HlsNetNodeWriteIndexed._PORT_ATTR_NAMES + ["_portDataOut"]

    def __init__(self, netlist:"HlsNetlistCtx",
                 dst:AnyBramPort,
                 cmd: Union[Literal[READ], Literal[WRITE]]):
        self.dst = dst
        _dst = self._getNominaInterface()

        HlsNetNodeWriteIndexed.__init__(self, netlist, dst, addSrcPort=_dst.HAS_W)
        self._rtlUseValid = True  # en is form of valid
        assert cmd is READ or cmd is WRITE, cmd
        self.cmd = cmd

        self._portDataOut: Optional[HlsNetNodeOut] = None
        if _dst.HAS_R:
            self._portDataOut = self._addOutput(_dst.dout._dtype, "dout")

        if cmd == READ:
            assert _dst.HAS_R, dst
            # set write data to None

        elif cmd == WRITE:
            assert _dst.HAS_W, dst

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
        Keep write part in this node and extract out data write port 
        """
        if self.isMulticlock:
            _dst = self._getNominaInterface()
            if _dst.HAS_R:
                readDataIo = self._extractDout(self.dst)

                dOut = self._portDataOut
                dNode = HlsNetNodeReadBramData(self.netlist, readDataIo, _dst.dout._dtype, name=self.name)
                dNode.assignRealization(OpRealizationMeta(0, 0, 0, 0, True))
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
                    assert t < nextClkBegin, o
                self.isMulticlock = False

                yield dNode

    @override
    def getAllocatedRTL(self, allocator:"ArchElement"):
        assert self._isRtlAllocated, self
        wData = self.dependsOn[self._portSrc.in_i]
        addr = self.dependsOn[self.indexes[0].in_i]
        ram: HwIOBramPort_noClk = self.dst
        key = (ram, addr, wData)
        return allocator.netNodeToRtl[key]

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> List[HdlStatement]:
        """
        Instantiate write operation on RTL level
        """
        assert not self._isRtlAllocated, self
        assert len(self.dependsOn) >= 2, self.dependsOn
        # [0] - data, [1] - addr, [2:] control dependencies
        for sync, t in zip(self.dependsOn[1:], self.scheduledIn[1:]):
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only datapath
            if sync._dtype != HVoidOrdering:
                allocator.rtlAllocHlsNetNodeOutInTime(sync, t)

        ram: HwIOBramPort_noClk = self.dst
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
        _addr = allocator.rtlAllocHlsNetNodeOutInTime(addr, self.scheduledIn[1])

        rtlObj = [
            # [todo] llvm MIR lefts bits which are sliced out
            ram.addr(_addr.data[ram.ADDR_WIDTH:])
        ]
        if ram.HAS_W:
            if ram.HAS_BE:
                raise NotImplementedError()
            if hasWData:
                rtlObj.append(ram.din(_wData.data))
            we = getattr(ram, "we", None)
            if we is not None:
                rtlObj.append(ram.we(0 if self.cmd is READ else 1))

        allocator.netNodeToRtl[key] = rtlObj
        if self._portDataOut is not None:
            assert ram.HAS_R, self
            allocator.rtlRegisterOutputRtlSignal(self._portDataOut, ram.dout, False, False, False)

        clkI = indexOfClkPeriod(self.scheduledIn[addrInPort.in_i], allocator.netlist.normalizedClkPeriod)
        allocator.rtlAllocDatapathWrite(self, ram.en, allocator.connections[clkI], rtlObj)

        self._isRtlAllocated = True
        return rtlObj

    def __repr__(self, minify=False):
        src = self.dependsOn[0]
        dstName = self._getInterfaceName(self.dst)
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.cmd} {dstName}>"
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.cmd} {dstName}{HlsNetNodeReadIndexed._strFormatIndexes(self.indexes)} <- {src}>"


class HlsNetNodeReadBramData(HlsNetNodeRead):
    pass


class HlsReadBram(HlsReadAddressed):

    def __init__(self,
                 parentProxy: "BramArrayProxy",
            parent:"HlsScope",
            src:AnyBramPort,
            index:ANY_SCALAR_INT_VALUE,
            element_t:HdlType,
            isBlocking:bool,
            hwIOName: Optional[str]=None):

        if isinstance(src, MultiPortGroup):
            src = MultiPortGroup(i for i in src if i.HAS_R)
            if len(src) == 1:
                src = src[0]
            else:
                assert src
        elif isinstance(src, BankedPortGroup):
            raise NotImplementedError()
        else:
            assert src.HAS_R

        HlsReadAddressed.__init__(self, parent, src, index, element_t, isBlocking, hwIOName=hwIOName)
        self.parentProxy = parentProxy

    def _getNativeInterfaceWordType(self) -> HdlType:
        src = getFirstInterfaceInstance(self._src)
        return src.dout._dtype

    @override
    @classmethod
    def _translateMirToNetlist(cls,
            representativeReadStm: "HlsReadBram",
            mirToNetlist:HlsNetlistAnalysisPassMirToNetlist,
            mbMeta:MachineBasicBlockMeta,
            instr:LoadInst,
            srcIo:AnyBramPort,
            index:Union[int, HlsNetNodeOutAny],
            cond: Optional[HlsNetNodeOutAny],
            instrDstReg:Register) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`hwtHls.frontend.ast.statementsRead.HlsRead._translateMirToNetlist`
        """
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, HwIOBramPort_noClk) or (isinstance(srcIo, MultiPortGroup) and isinstance(srcIo[0], HwIOBramPort_noClk)), srcIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", srcIo, instr)

        n = HlsNetNodeWriteBramCmd(netlist, srcIo, READ)
        mbMeta.parentElement.addNode(n)
        mbMeta.addOrderedNode(n)

        _io = n._getNominaInterface()
        if _io.HAS_W:
            xWrData = HlsNetNodeConst(netlist, _io.dout._dtype.from_py(None))
            mbMeta.parentElement.addNode(xWrData)
            xWrData._outputs[0].connectHlsIn(n._inputs[0])
        index.connectHlsIn(n.indexes[0])
        _cond = cond
        # _cond = mbMeta.syncTracker.resolveControlOutput(cond)
        mirToNetlist._addExtraCond(n, _cond, None)
        mirToNetlist._addSkipWhen_n(n, _cond, None)

        valCache.add(mbMeta.block, instrDstReg, n._portDataOut, True)
        return [n, ]

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name")
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {self._name:s}[{self.operands[0]}], {t}>"


class HlsWriteBram(HlsWriteAddressed):

    def __init__(self,
            parentProxy: "BramArrayProxy",
            parent:"HlsScope",
            src:Union[SsaValue, RtlSignal, HConst],
            dst:AnyBramPort,
            index:Union[SsaValue, RtlSignal, HConst],
            element_t:HdlType,
            mayBecomeFlushable=True):

        if isinstance(dst, MultiPortGroup):
            dst = MultiPortGroup(i for i in dst if i.HAS_W)
            if len(dst) == 1:
                dst = dst[0]
            else:
                assert dst
        elif isinstance(dst, BankedPortGroup):
            raise NotImplementedError(dst)
        else:
            assert isinstance(dst, HwIOBramPort_noClk), dst
            assert dst.HAS_W, dst

        HlsWriteAddressed.__init__(self, parent, src, dst, index, element_t, mayBecomeFlushable=mayBecomeFlushable)
        self.parentProxy = parentProxy

    def _getNativeInterfaceWordType(self) -> HdlType:
        dst = getFirstInterfaceInstance(self.dst)
        return dst.din._dtype

    @override
    @classmethod
    def _translateMirToNetlist(cls,
            representativeWriteStm: "HlsWrite",
            mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
            mbMeta: MachineBasicBlockMeta,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: AnyBramPort,
            index: Union[int, HlsNetNodeOutAny],
            cond: Optional[HlsNetNodeOutAny],) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`hwtHls.frontend.ast.statementsRead.HlsRead._translateMirToNetlist`
        """
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        isInstanceOfInterfacePort(dstIo, HwIOBramPort_noClk)
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", dstIo, instr)

        n = HlsNetNodeWriteBramCmd(netlist, dstIo, WRITE)
        mbMeta.parentElement.addNode(n)
        srcVal.connectHlsIn(n._portSrc)
        index.connectHlsIn(n.indexes[0])

        # _cond = mbMeta.syncTracker.resolveControlOutput(cond)
        _cond = cond
        mirToNetlist._addExtraCond(n, _cond, None)
        mirToNetlist._addSkipWhen_n(n, _cond, None)
        mbMeta.addOrderedNode(n)
        return [n, ]


class BramArrayProxy(IoProxyAddressed):

    def __init__(self, hls:"HlsScope", interface:AnyBramPort):
        if isinstance(interface, (MultiPortGroup, BankedPortGroup)):
            i = interface[0]
        else:
            i = interface
        assert isInstanceOfInterfacePort(i, HwIOBramPort_noClk), i
        if i.HAS_W:
            if i.HAS_BE:
                raise NotImplementedError()
            wordType = i.din._dtype

        else:
            assert i.HAS_R, ("Must have at least one (read/write)", interface)
            wordType = i.dout._dtype

        nativeType = wordType[int(2 ** i.ADDR_WIDTH)]
        IoProxyAddressed.__init__(self, hls, interface, nativeType)
        self.rWordT = self.wWordT = wordType
        self.indexT = i.addr._dtype

    READ_CLS = HlsReadBram
    WRITE_CLS = HlsWriteBram
