
from functools import lru_cache
from typing import Union, Tuple

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.std import BramPort_withoutClk
from hwt.interfaces.structIntf import Interface_to_HdlType
from hwt.math import log2ceil
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statementsRead import HlsReadAddressed
from hwtHls.frontend.ast.statementsWrite import HlsWriteAddressed
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.llvm.llvmIr import LoadInst, Register
from hwtHls.llvm.llvmIr import MachineInstr
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HVoidExternData
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.opCache import MirToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MachineBasicBlockSyncContainer
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
        return Interface_to_HdlType().apply(i, exclude=(i.valid, i.ready))

    @classmethod
    def _constructAddrWrite(cls,
            netlist: HlsNetlistCtx,
            mirToNetlist:HlsNetlistAnalysisPassMirToNetlist,
            mbSync:MachineBasicBlockSyncContainer,
            addr: Axi4Lite_addr,
            addrVal: HlsNetNodeOutAny,
            offsetWidth: int,
            prot: Union[int, HlsNetNodeOutAny],
            cond:HlsNetNodeOutAny):
        if isinstance(prot, int):
            prot = netlist.builder.buildConst(addr.prot._dtype.from_py(prot))
        aVal = netlist.builder.buildConcatVariadic((Bits(offsetWidth).from_py(0), addrVal, prot))
        aNode = HlsNetNodeWrite(netlist, NOT_SPECIFIED, addr)
        link_hls_nodes(aVal, aNode._inputs[0])

        mirToNetlist._addExtraCond(aNode, cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(aNode, cond, mbSync.blockEn)
        mbSync.addOrderedNode(aNode)
        mirToNetlist.outputs.append(aNode)
        return aNode

    @staticmethod
    def _connectUsingExternalDataDep(n0: HlsNetNode, n1: HlsNetNode):
        """
        :note: used to mark that the IO operations do have data dependency and
            we can rely on it when resolving implementation of data thread synchronization.
        """
        eddo = n0._addOutput(HVoidExternData, "externalDataDep")
        eddi = n1._addInput("externalDataDep")
        link_hls_nodes(eddo, eddi)
        
    @classmethod
    def _translateMirToNetlist(cls,
            representativeReadStm: "HlsReadAxi4Lite",
            mirToNetlist:HlsNetlistAnalysisPassMirToNetlist,
            mbSync:MachineBasicBlockSyncContainer,
            instr:LoadInst,
            srcIo:Axi4Lite,
            index:Union[int, HlsNetNodeOutAny],
            cond:HlsNetNodeOutAny,
            instrDstReg:Register):
    
        valCache: MirToHwtHlsNetlistOpCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        proxy:Axi4LiteArrayProxy = representativeReadStm.parentProxy
        assert isinstance(srcIo, Axi4Lite), srcIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", srcIo, instr)

        aNode = cls._constructAddrWrite(netlist, mirToNetlist, mbSync, srcIo.ar, index, proxy.offsetWidth, PROT_DEFAULT, cond)
        if proxy.LATENCY_AR_TO_R:
            mbSync.addOrderingDelay(proxy.LATENCY_AR_TO_R)

        rNode = HlsNetNodeRead(netlist, srcIo.r)
        HlsReadAxi4Lite._connectUsingExternalDataDep(aNode, rNode)

        mirToNetlist._addExtraCond(rNode, cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(rNode, cond, mbSync.blockEn)
        mbSync.addOrderedNode(rNode)
        mirToNetlist.inputs.append(rNode)
        rDataO = rNode._outputs[0]
        
        rWordWidth = representativeReadStm._getNativeInterfaceWordType().bit_length()
        nativeWordWidth = proxy.nativeType.element_t.bit_length()
        if rWordWidth < nativeWordWidth:
            # the read data is larger because pointer representing IO is pointing to a larger word
            # because write is using larger word and this must be the same pointer for reads and writes
            # :note: The next node which uses data output should be the slice to correct width.
            padding = netlist.builder.buildConst(Bits(nativeWordWidth - rWordWidth).from_py(None))
            rDataO = netlist.builder.buildConcatVariadic((rDataO, padding))
        else:
            assert rWordWidth == nativeWordWidth
            
        valCache.add(mbSync.block, instrDstReg, rDataO, True)


class HlsWriteAxi4Lite(HlsWriteAddressed):

    def __init__(self,
            parentProxy: "Axi4LiteArrayProxy",
            parent:"HlsScope",
            src:Union[SsaValue, RtlSignal, HValue],
            dst:Union[BramPort_withoutClk, Tuple[BramPort_withoutClk]],
            index:Union[SsaValue, RtlSignal, HValue],
            element_t:HdlType):
        HlsWriteAddressed.__init__(self, parent, src, dst, index, element_t)
        self.parentProxy = parentProxy
    
    @lru_cache(maxsize=None, typed=True)
    def _getNativeInterfaceWordType(self) -> HdlType:
        i = self.dst.w
        return Interface_to_HdlType().apply(i, exclude=(i.valid, i.ready))
    
    @classmethod
    def _translateMirToNetlist(cls,
            representativeWriteStm: "HlsWriteAxi4Lite",
            mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
            mbSync: MachineBasicBlockSyncContainer,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: Axi4Lite,
            index: Union[int, HlsNetNodeOutAny],
            cond: HlsNetNodeOutAny):
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(dstIo, Axi4Lite), dstIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", dstIo, instr)
        proxy:Axi4LiteArrayProxy = representativeWriteStm.parentProxy
        aNode = HlsReadAxi4Lite._constructAddrWrite(
            netlist, mirToNetlist, mbSync, dstIo.aw, index,
            proxy.offsetWidth, PROT_DEFAULT, cond)
        
        if proxy.LATENCY_AW_TO_W:
            mbSync.addOrderingDelay(proxy.LATENCY_AW_TO_W)
        wNode = HlsNetNodeWrite(netlist, NOT_SPECIFIED, dstIo.w)
        HlsReadAxi4Lite._connectUsingExternalDataDep(aNode, wNode)
        assert srcVal._dtype.bit_length() == proxy.wWordT.bit_length(), (dstIo, srcVal._dtype, dstIo.DATA_WIDTH) 
        link_hls_nodes(srcVal, wNode._inputs[0])
        
        mirToNetlist._addExtraCond(wNode, cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(wNode, cond, mbSync.blockEn)
        mbSync.addOrderedNode(wNode)
        mirToNetlist.outputs.append(wNode)
        if proxy.LATENCY_W_TO_B:
            mbSync.addOrderingDelay(proxy.LATENCY_W_TO_B)
        
        bNode = HlsNetNodeRead(netlist, dstIo.b)
        HlsReadAxi4Lite._connectUsingExternalDataDep(wNode, bNode)        

        mirToNetlist._addExtraCond(bNode, cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(bNode, cond, mbSync.blockEn)
        mbSync.addOrderedNode(bNode)
        mirToNetlist.inputs.append(bNode)


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
            rWordT = Interface_to_HdlType().apply(interface.r, exclude=(interface.r.valid, interface.r.ready))
            nativeType = rWordT[int(2 ** indexWidth)]
            dataWordT = interface.r.data._dtype
        else:
            rWordT = None

        if interface.HAS_W:
            wWordT = Interface_to_HdlType().apply(interface.w, exclude=(interface.w.valid, interface.w.ready))
            nativeType = wWordT[int(2 ** indexWidth)]
            dataWordT = interface.w.data._dtype
        
        else:
            wWordT = None

        offsetWidth = log2ceil(interface.DATA_WIDTH // 8 - 1)
        assert indexWidth > 1, (interface.ADDR_WIDTH, indexWidth, "Address is of insufficient size because", interface.DATA_WIDTH, offsetWidth)
        IoProxyAddressed.__init__(self, hls, interface, nativeType)
        self.indexT = Bits(indexWidth)
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
