
from functools import lru_cache
from typing import Union, Tuple, Sequence, Optional

from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIOs.hwIOStruct import HwIO_to_HdlType
from hwt.hwIOs.std import HwIOBramPort_noClk
from hwt.math import log2ceil
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statementsRead import HlsReadAddressed
from hwtHls.frontend.ast.statementsWrite import HlsWriteAddressed
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.llvm.llvmIr import LoadInst, Register
from hwtHls.llvm.llvmIr import MachineInstr
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidExternData
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi4Lite import Axi4Lite, Axi4Lite_addr
from hwtLib.amba.constants import PROT_DEFAULT


class HlsReadAxi4Lite(HlsReadAddressed):

    def __init__(self,
            parentProxy: "Axi4LiteArrayProxy",
            parent:"HlsScope",
            src:Axi4Lite,
            index:RtlSignal,
            element_t:HdlType,
            isBlocking: bool):
        HlsReadAddressed.__init__(self, parent, src, index, element_t, isBlocking)
        self.parentProxy = parentProxy

    @lru_cache(maxsize=None, typed=True)
    def _getNativeInterfaceWordType(self) -> HdlType:
        i = self._src.r
        return HwIO_to_HdlType().apply(i, exclude=(i.valid, i.ready))

    @classmethod
    def _constructAddrWrite(cls,
            netlist: HlsNetlistCtx,
            mirToNetlist:HlsNetlistAnalysisPassMirToNetlist,
            parent: ArchElement,
            mbSync:MachineBasicBlockMeta,
            addr: Axi4Lite_addr,
            addrVal: HlsNetNodeOutAny,
            offsetWidth: int,
            prot: Union[int, HlsNetNodeOutAny],
            cond:Union[int, HlsNetNodeOutAny]):

        if isinstance(prot, int):
            prot = parent.builder.buildConst(addr.prot._dtype.from_py(prot))

        aVal = parent.builder.buildConcat(HBits(offsetWidth).from_py(0), addrVal, prot)

        aNode = HlsNetNodeWrite(netlist, addr)
        parent.addNode(aNode)
        aVal.connectHlsIn(aNode._inputs[0])

        mirToNetlist._addExtraCond(aNode, cond, None)
        mirToNetlist._addSkipWhen_n(aNode, cond, None)
        mbSync.addOrderedNode(aNode)
        return aNode

    @staticmethod
    def _connectUsingExternalDataDep(n0: HlsNetNode, n1: HlsNetNode):
        """
        :note: used to mark that the IO operations do have data dependency and
            we can rely on it when resolving implementation of data thread synchronization.
        """
        eddo = n0._addOutput(HVoidExternData, "externalDataDep")
        eddi = n1._addInput("externalDataDep")
        eddo.connectHlsIn(eddi)

    @classmethod
    def _translateMirToNetlist(cls,
            representativeReadStm: "HlsReadAxi4Lite",
            mirToNetlist:HlsNetlistAnalysisPassMirToNetlist,
            mbMeta:MachineBasicBlockMeta,
            instr:LoadInst,
            srcIo:Axi4Lite,
            index:Union[int, HlsNetNodeOutAny],
            cond: Optional[HlsNetNodeOutAny],
            instrDstReg:Register) -> Sequence[HlsNetNode]:

        if not representativeReadStm._isBlocking:
            raise NotImplementedError()

        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        proxy:Axi4LiteArrayProxy = representativeReadStm.parentProxy
        assert isinstance(srcIo, Axi4Lite), srcIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", srcIo, instr)

        _cond = cond  # mbMeta.syncTracker.resolveControlOutput(cond)
        aNode = cls._constructAddrWrite(netlist, mirToNetlist, mbMeta.parentElement,
                                        mbMeta, srcIo.ar, index, proxy.offsetWidth, PROT_DEFAULT, _cond)
        if proxy.LATENCY_AR_TO_R:
            mbMeta.addOrderingDelay(proxy.LATENCY_AR_TO_R)
        else:
            _cond = mbMeta.parentElement.buildAndOptional(_cond, aNode.getReadyNB())

        rNode = HlsNetNodeRead(netlist, srcIo.r)
        mbMeta.parentElement.addNode(rNode)
        mbMeta.addOrderedNode(rNode)
        HlsReadAxi4Lite._connectUsingExternalDataDep(aNode, rNode)

        mirToNetlist._addExtraCond(rNode, _cond, None)
        mirToNetlist._addSkipWhen_n(rNode, _cond, None)
        rDataO = rNode._portDataOut

        rWordWidth = representativeReadStm._getNativeInterfaceWordType().bit_length()
        nativeWordWidth = proxy.nativeType.element_t.bit_length()
        if rWordWidth < nativeWordWidth:
            # the read data is larger because pointer representing IO is pointing to a larger word
            # because write is using larger word and this must be the same pointer for reads and writes
            # :note: The next node which uses data output should be the slice to correct width.
            builder = mbMeta.parentElement.builder
            padding = builder.buildConst(HBits(nativeWordWidth - rWordWidth).from_py(None))
            rDataO = builder.buildConcat(rDataO, padding)
        else:
            assert rWordWidth == nativeWordWidth

        valCache.add(mbMeta.block, instrDstReg, rDataO, True)

        return [aNode, rNode]


class HlsWriteAxi4Lite(HlsWriteAddressed):

    def __init__(self,
            parentProxy: "Axi4LiteArrayProxy",
            parent:"HlsScope",
            src:Union[SsaValue, HConst],
            dst:Union[HwIOBramPort_noClk, Tuple[HwIOBramPort_noClk]],
            index:Union[SsaValue, RtlSignal, HConst],
            element_t:HdlType,
            mayBecomeFlushable=False):
        HlsWriteAddressed.__init__(self, parent, src, dst, index, element_t, mayBecomeFlushable)
        self.parentProxy = parentProxy

    @lru_cache(maxsize=None, typed=True)
    def _getNativeInterfaceWordType(self) -> HdlType:
        i = self.dst.w
        return HwIO_to_HdlType().apply(i, exclude=(i.valid, i.ready))

    @classmethod
    def _translateMirToNetlist(cls,
            representativeWriteStm: "HlsWriteAxi4Lite",
            mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
            mbMeta: MachineBasicBlockMeta,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: Axi4Lite,
            index: Union[int, HlsNetNodeOutAny],
            cond: Optional[HlsNetNodeOutAny]) -> Sequence[HlsNetNode]:
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(dstIo, Axi4Lite), dstIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", dstIo, instr)
        _cond = cond
        #_cond = mbMeta.syncTracker.resolveControlOutput(cond)
        proxy:Axi4LiteArrayProxy = representativeWriteStm.parentProxy
        aNode = HlsReadAxi4Lite._constructAddrWrite(
            netlist, mirToNetlist, mbMeta.parentElement, mbMeta, dstIo.aw, index,
            proxy.offsetWidth, PROT_DEFAULT, _cond)

        if proxy.LATENCY_AW_TO_W:
            mbMeta.addOrderingDelay(proxy.LATENCY_AW_TO_W)
        else:
            _cond = mbMeta.parentElement.builder.buildAndOptional(_cond, aNode.getReadyNB())

        wNode = HlsNetNodeWrite(netlist, dstIo.w)
        mbMeta.parentElement.addNode(wNode)
        HlsReadAxi4Lite._connectUsingExternalDataDep(aNode, wNode)
        assert srcVal._dtype.bit_length() == proxy.wWordT.bit_length(), (dstIo, srcVal._dtype, dstIo.DATA_WIDTH)
        srcVal.connectHlsIn(wNode._inputs[0])

        mirToNetlist._addExtraCond(wNode, _cond, None)
        mirToNetlist._addSkipWhen_n(wNode, _cond, None)
        mbMeta.addOrderedNode(wNode)
        if proxy.LATENCY_W_TO_B:
            mbMeta.addOrderingDelay(proxy.LATENCY_W_TO_B)
        else:
            _cond = mbMeta.parentElement.buildAndOptional(_cond, aNode.getReadyNB())

        bNode = HlsNetNodeRead(netlist, dstIo.b)
        mbMeta.parentElement.addNode(bNode)
        HlsReadAxi4Lite._connectUsingExternalDataDep(wNode, bNode)

        mirToNetlist._addExtraCond(bNode, _cond, None)
        mirToNetlist._addSkipWhen_n(bNode, _cond, None)
        mbMeta.addOrderedNode(bNode)

        return [aNode, wNode, bNode]


class Axi4LiteArrayProxy(IoProxyAddressed):
    """
    :ivar indexT: HdlType for index in to access data behind this proxy.

    :note: Latencies are specified in clock cycle ticks. 1 means in next clock cycle after clock cycle where previous transaction happen.
    :ivar LATENCY_AR_TO_R: Clock cycles until data starts arriving after transaction on AR channel.
    :ivar LATENCY_AW_TO_W: Clock cycles it takes until data write channel will start accepting data after transaction on AW channel.
    :ivar LATENCY_W_TO_B: Clock cycles it takes for write response (B) after last word is written on W channel.
    :ivar LATENCY_B_TO_R: Specifies how many clock cycles are required for written data to update read transaction to same address.
        (If the read data from same address which was just written starts arriving after this latency they are guaranteed to be just written data.)
    """

    def __init__(self, hls:"HlsScope", interface:Axi4Lite):
        indexWidth = interface.ADDR_WIDTH - log2ceil(interface.DATA_WIDTH // 8 - 1)
        if interface.HAS_R:
            rWordT = HwIO_to_HdlType().apply(interface.r, exclude=(interface.r.valid, interface.r.ready))
            nativeType = rWordT[int(2 ** indexWidth)]
            dataWordT = interface.r.data._dtype
        else:
            rWordT = None

        if interface.HAS_W:
            wWordT = HwIO_to_HdlType().apply(interface.w, exclude=(interface.w.valid, interface.w.ready))
            nativeType = wWordT[int(2 ** indexWidth)]
            dataWordT = interface.w.data._dtype

        else:
            wWordT = None

        offsetWidth = log2ceil(interface.DATA_WIDTH // 8 - 1)
        assert indexWidth > 1, (interface.ADDR_WIDTH, indexWidth, "Address is of insufficient size because", interface.DATA_WIDTH, offsetWidth)
        IoProxyAddressed.__init__(self, hls, interface, nativeType)
        self.indexT = HBits(indexWidth)
        self.offsetWidth = offsetWidth
        self.rWordT = rWordT
        self.wWordT = wWordT
        self.dataWordT = dataWordT
        self.LATENCY_AR_TO_R = 1
        self.LATENCY_AW_TO_W = 0
        self.LATENCY_W_TO_B = 1
        self.LATENCY_B_TO_R = 1

    READ_CLS = HlsReadAxi4Lite
    WRITE_CLS = HlsWriteAxi4Lite
