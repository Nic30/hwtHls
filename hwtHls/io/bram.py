
from typing import Union, Literal, List, Optional, Generator, Sequence

from hwt.hdl.constants import WRITE, READ
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.std import BramPort_withoutClk
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statementsRead import HlsReadAddressed
from hwtHls.frontend.ast.statementsWrite import HlsWriteAddressed
from hwtHls.frontend.ast.utils import ANY_SCALAR_INT_VALUE
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup, \
    isInstanceOfInterfacePort, getFirstInterfaceInstance
from hwtHls.llvm.llvmIr import LoadInst, Register
from hwtHls.llvm.llvmIr import MachineInstr
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNodePartRef, HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes, \
    HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeReadIndexed
from hwtHls.netlist.nodes.schedulableNode import OutputMinUseTimeGetter
from hwtHls.netlist.nodes.write import HlsNetNodeWriteIndexed
from hwtHls.netlist.scheduler.clk_math import epsilon, indexOfClkPeriod
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.ssa.translation.llvmMirToNetlist.insideOfBlockSyncTracker import InsideOfBlockSyncTracker
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.ssa.value import SsaValue
from hwtHls.typingFuture import override


AnyBramPort = Union[BramPort_withoutClk, BankedPortGroup[BramPort_withoutClk], MultiPortGroup[BramPort_withoutClk]]


class HlsNetNodeWriteBramCmd(HlsNetNodeWriteIndexed):
    """
    A netlist node which is used to represent read or write command to/from BRAM port.
    """

    def __init__(self, netlist:"HlsNetlistCtx",
                 dst:AnyBramPort,
                 cmd: Union[Literal[READ], Literal[WRITE]]):
        HlsNetNodeWriteIndexed.__init__(self, netlist, dst)
        assert cmd is READ or cmd is WRITE, cmd
        self.cmd = cmd
        if isinstance(dst, BankedPortGroup):
            self.maxIosPerClk = len(dst)
        elif isinstance(dst, MultiPortGroup):
            self.maxIosPerClk = len(dst)

        _dst = self._getNominaInterface()
        if _dst.HAS_R:
            self._addOutput(_dst.dout._dtype, "dout")

        if cmd == READ:
            assert _dst.HAS_R, dst
            # set write data to None
            xWrData = HlsNetNodeConst(netlist, _dst.dout._dtype.from_py(None))
            netlist.nodes.append(xWrData)
            link_hls_nodes(xWrData._outputs[0], self._inputs[0])

        elif cmd == WRITE:
            assert _dst.HAS_W, dst

    def _getNominaInterface(self):
        return getFirstInterfaceInstance(self.dst)

    @override
    def scheduleAlapCompaction(self, endOfLastClk: int, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]):
        return HlsNetNodeWriteIndexed.scheduleAlapCompaction(self, endOfLastClk, outputMinUseTimeGetter)

    @override
    def resolveRealization(self):
        netlist = self.netlist
        ffdelay = netlist.platform.get_op_realization(ResourceFF, 1, 1, netlist.realTimeClkPeriod).inputWireDelay * 2
        isRead = self.cmd is READ
        re = OpRealizationMeta(
            inputWireDelay=ffdelay,
            inputClkTickOffset=0,
            outputWireDelay=epsilon if isRead else 0,
            outputClkTickOffset=(1, *(0 for _ in range(len(self._outputs) - 1))) if isRead else 0
        )
        self.assignRealization(re)

    def allocateRtlInstance(self, allocator: "ArchElement") -> List[HdlStatement]:
        """
        Instantiate write operation on RTL level
        """
        assert len(self.dependsOn) >= 2, self.dependsOn
        # [0] - data, [1] - addr, [2:] control dependencies
        for sync, t in zip(self.dependsOn[1:], self.scheduledIn[1:]):
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only datapath
            if sync._dtype != HVoidOrdering:
                allocator.instantiateHlsNetNodeOutInTime(sync, t)

        ram: BramPort_withoutClk = self.dst
        assert not isinstance(ram, tuple), (self, ram, "If this was an operation with a group of ports the individual ports should have already been assigned")
        en = ram.en
        if en._sig._nop_val is NOT_SPECIFIED:
            en._sig._nop_val = en._sig._dtype.from_py(0)
        if ram.HAS_W:
            # we can still does not have to be present, it can be replaced by just en on write only ports
            we = getattr(ram, "we", None)
            if we is not None and we._sig._nop_val is NOT_SPECIFIED:
                we._sig._nop_val = we._sig._dtype.from_py(0)

        wData = self.dependsOn[0]
        addr = self.dependsOn[1]
        key = (ram, addr, wData)
        try:
            # skip instantiation of writes in the same mux
            return allocator.netNodeToRtl[key]
        except KeyError:
            pass

        if self._dataVoidOut is not None:
            HlsNetNodeReadIndexed._allocateRtlInstanceDataVoidOut(self, allocator)

        _wData = allocator.instantiateHlsNetNodeOutInTime(wData, self.scheduledIn[0])
        _addr = allocator.instantiateHlsNetNodeOutInTime(addr, self.scheduledIn[1])

        rtlObj = []
        # [todo] llvm MIR lefts bits which are sliced out
        rtlObj.append(ram.addr(_addr.data[ram.ADDR_WIDTH:]))
        if ram.HAS_W:
            if ram.HAS_BE:
                raise NotImplementedError()
            rtlObj.append(ram.din(_wData.data))
            we = getattr(ram, "we", None)
            if we is not None:
                rtlObj.append(ram.we(0 if self.cmd is READ else 1))

        allocator.netNodeToRtl[key] = rtlObj
        if ram.HAS_R:
            allocator.netNodeToRtl[self._outputs[0]] = TimeIndependentRtlResource(ram.dout, self.scheduledOut[0], allocator, False)

        return rtlObj

    def createSubNodeRefrenceFromPorts(self, beginTime: int, endTime: int,
                                       inputs: List[HlsNetNodeIn], outputs: List[HlsNetNodeOut]) -> Optional['HlsNetNodeWriteBramCmdPartRef']:
        """
        :see: :meth:`~.HlsNetNode.partsComplement`
        """
        assert inputs or outputs, self
        cmdTime = self.scheduledIn[0]

        if beginTime <= cmdTime and cmdTime <= endTime:
            isDataReadPart = False
            t = cmdTime

        else:
            dataReadTime = self.scheduledOut[0]
            if beginTime <= dataReadTime and dataReadTime <= endTime:
                isDataReadPart = True
                t = dataReadTime
            else:
                return None

        return HlsNetNodeWriteBramCmdPartRef(self.netlist, self, isDataReadPart, t)

    def partsComplement(self, otherParts: List["HlsNetNodeWriteBramCmdPartRef"]) -> Generator["HlsNetNodeWriteBramCmdPartRef", None, None]:
        """
        :see: :meth:`~.HlsNetNode.partsComplement`
        """
        partCnt = len(otherParts)
        assert partCnt <= 2, otherParts
        assert partCnt > 0, otherParts
        if partCnt == 2:
            return
        else:
            p: HlsNetNodeWriteBramCmdPartRef = otherParts[0]
            assert p.parentNode is self, (self, p)
            yield HlsNetNodeWriteBramCmdPartRef(self.netlist, self, not p.isDataReadPart, self.scheduledZero if p.isDataReadPart else self.scheduledOut[0])

    def __repr__(self, minify=False):
        src = self.dependsOn[0]
        dstName = self._getInterfaceName(self.dst)
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.cmd} {dstName}>"
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.cmd} {dstName}{HlsNetNodeReadIndexed._strFormatIndexes(self.indexes)} <- {src}>"


class HlsNetNodeWriteBramCmdPartRef(HlsNetNodePartRef):

    def __init__(self, netlist:"HlsNetlistCtx", parentNode:HlsNetNodeWriteBramCmd, isDataReadPart: bool, scheduledZero:int, name:str=None):
        HlsNetNodePartRef.__init__(self, netlist, parentNode, name=name)
        self.isDataReadPart = isDataReadPart
        self.scheduledZero = scheduledZero

    def allocateRtlInstance(self, allocator: "ArchElement"):
        return self.parentNode.allocateRtlInstance(allocator)

    def iterChildReads(self):
        return
        yield

    def iterChildWrites(self):
        if not self.isDataReadPart:
            yield self.parentNode
        return

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} for {'data' if self.isDataReadPart else 'cmd'} {self.parentNode}>"


class HlsReadBram(HlsReadAddressed):

    def __init__(self,
                 parentProxy: "BramArrayProxy",
            parent:"HlsScope",
            src:AnyBramPort,
            index:ANY_SCALAR_INT_VALUE,
            element_t:HdlType,
            isBlocking:bool,
            intfName: Optional[str]=None):

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

        HlsReadAddressed.__init__(self, parent, src, index, element_t, isBlocking, intfName=intfName)
        self.parentProxy = parentProxy

    def _getNativeInterfaceWordType(self) -> HdlType:
        src = getFirstInterfaceInstance(self._src)
        return src.dout._dtype

    @override
    @classmethod
    def _translateMirToNetlist(cls,
            representativeReadStm: "HlsReadBram",
            mirToNetlist:HlsNetlistAnalysisPassMirToNetlist,
            syncTracker: InsideOfBlockSyncTracker,
            mbSync:MachineBasicBlockMeta,
            instr:LoadInst,
            srcIo:AnyBramPort,
            index:Union[int, HlsNetNodeOutAny],
            cond:HlsNetNodeOutAny,
            instrDstReg:Register) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`hwtHls.frontend.ast.statementsRead.HlsRead._translateMirToNetlist`
        """
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, BramPort_withoutClk) or (isinstance(srcIo, MultiPortGroup) and isinstance(srcIo[0], BramPort_withoutClk)), srcIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", srcIo, instr)

        n = HlsNetNodeWriteBramCmd(netlist, srcIo, READ)
        link_hls_nodes(index, n.indexes[0])

        _cond = syncTracker.resolveControlOutput(cond)
        mirToNetlist._addExtraCond(n, _cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(n, _cond, mbSync.blockEn)
        mbSync.addOrderedNode(n)
        mirToNetlist.outputs.append(n)
        valCache.add(mbSync.block, instrDstReg, n._outputs[0], True)
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
            src:Union[SsaValue, RtlSignal, HValue],
            dst:AnyBramPort,
            index:Union[SsaValue, RtlSignal, HValue],
            element_t:HdlType):

        if isinstance(dst, MultiPortGroup):
            dst = MultiPortGroup(i for i in dst if i.HAS_W)
            if len(dst) == 1:
                dst = dst[0]
            else:
                assert dst
        elif isinstance(dst, BankedPortGroup):
            raise NotImplementedError(dst)
        else:
            assert isinstance(dst, BramPort_withoutClk), dst
            assert dst.HAS_W, dst

        HlsWriteAddressed.__init__(self, parent, src, dst, index, element_t)
        self.parentProxy = parentProxy

    def _getNativeInterfaceWordType(self) -> HdlType:
        dst = getFirstInterfaceInstance(self.dst)
        return dst.din._dtype

    @override
    @classmethod
    def _translateMirToNetlist(cls,
            representativeWriteStm: "HlsWrite",
            mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
            syncTracker: InsideOfBlockSyncTracker,
            mbSync: MachineBasicBlockMeta,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: AnyBramPort,
            index: Union[int, HlsNetNodeOutAny],
            cond: Union[int, HlsNetNodeOutAny]) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`hwtHls.frontend.ast.statementsRead.HlsRead._translateMirToNetlist`
        """
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isInstanceOfInterfacePort(dstIo, BramPort_withoutClk), dstIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", dstIo, instr)

        n = HlsNetNodeWriteBramCmd(netlist, dstIo, WRITE)
        link_hls_nodes(srcVal, n._inputs[0])
        link_hls_nodes(index, n.indexes[0])

        _cond = syncTracker.resolveControlOutput(cond)
        mirToNetlist._addExtraCond(n, _cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(n, _cond, mbSync.blockEn)
        mbSync.addOrderedNode(n)
        mirToNetlist.outputs.append(n)
        return [n, ]


class BramArrayProxy(IoProxyAddressed):

    def __init__(self, hls:"HlsScope", interface:AnyBramPort):
        if isinstance(interface, (MultiPortGroup, BankedPortGroup)):
            i = interface[0]
        else:
            i = interface
        assert isInstanceOfInterfacePort(i, BramPort_withoutClk), i
        if i.HAS_W:
            if i.HAS_BE:
                raise NotImplementedError()
            wordType = i.din._dtype

        else:
            assert i.HAS_R, ("Must have atleast one (read/write)", interface)
            wordType = i.dout._dtype

        nativeType = wordType[int(2 ** i.ADDR_WIDTH)]
        IoProxyAddressed.__init__(self, hls, interface, nativeType)
        self.rWordT = self.wWordT = wordType
        self.indexT = i.addr._dtype

    READ_CLS = HlsReadBram
    WRITE_CLS = HlsWriteBram
