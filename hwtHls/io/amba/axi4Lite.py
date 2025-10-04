
from typing import Union, Sequence, Optional, Type as TypingType, Literal

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import offsetof
from hwt.hdl.types.structValBase import HStructConstBase
from hwt.hwIOs.hwIOStruct import HwIO_to_HdlType
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ioProxyAddressed import IoProxyAddressed
from hwtHls.frontend.pyBytecode import hlsLowLevel
from hwtHls.frontend.statementsRead import HlsReadAddressed
from hwtHls.frontend.statementsWrite import HlsWriteAddressed
from hwtHls.llvm.llvmIr import Register, MachineInstr, MetadataIoAxiMM, IoLowerAxiMMPass, MDTuple, \
    APInt, HwtHlsIoMetadata, MetadataAsMDString, MemoryOrdering
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidExternData, HVoidData
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtLib.amba.axi4Lite import Axi4Lite, Axi4Lite_addr, Axi4Lite_r, Axi4Lite_w, \
    Axi4Lite_b
from hwtLib.amba.axi_common import Axi_hs
from hwtLib.amba.constants import PROT_DEFAULT, RESP_OKAY
from hwtLib.handshaked.streamNode import ValidReadyTuple


def _MDTupleGetLastString(md: MDTuple) -> str:
    return MetadataAsMDString(md.getOperand(md.getNumOperands() - 1).get()).getString().str()


class HlsReadAxi4Lite(HlsReadAddressed):
    pass


class HlsWriteAxi4Lite(HlsWriteAddressed):
    pass


class IoProxyAxi4Lite(IoProxyAddressed):
    """
    :ivar indexT: HdlType for index in to access data behind this proxy.

    :note: Latencies are specified in clock cycle ticks. 1 means in next clock cycle after clock cycle where previous transaction happen.
    :ivar LATENCY_AR_TO_R: Clock cycles until data starts arriving after transaction on AR channel.
    :ivar LATENCY_AW_TO_W: Clock cycles it takes until data write channel will start accepting data after transaction on AW channel.
    :ivar LATENCY_W_TO_B: Clock cycles it takes for write response (B) after last word is written on W channel.
    :ivar LATENCY_B_TO_R: Specifies how many clock cycles are required for written data to update read transaction to same address.
        (If the read data from same address which was just written starts arriving after this latency they are guaranteed to be just written data.)
    """

    READ_CLS = HlsReadAxi4Lite
    WRITE_CLS = HlsWriteAxi4Lite

    def __init__(self, hls:"HlsScope", interface: Axi4Lite,
                 LATENCY_AR_TO_R=1,
                 LATENCY_AW_TO_W=0,
                 LATENCY_W_TO_B=1,
                 LATENCY_B_TO_R=1,
                 memOrdering=MemoryOrdering.MEMORDERING_MUST_WAIT_FOR_WRITE_CONFIRM):
        indexWidth = interface.ADDR_WIDTH - log2ceil(interface.DATA_WIDTH // 8 - 1)
        if interface.HAS_R:
            _nativeReadTy = self._getTypeOfAxiChannel(interface.r)
            nativeType = _nativeReadTy[int(2 ** indexWidth)]
            dataWordT = interface.r.data._dtype
        else:
            _nativeReadTy = None

        if interface.HAS_W:
            _nativeWriteTy = self._getTypeOfAxiChannel(interface.w)
            nativeType = _nativeWriteTy[int(2 ** indexWidth)]
            dataWordT = interface.w.data._dtype

        else:
            _nativeWriteTy = None

        offsetWidth = log2ceil(interface.DATA_WIDTH // 8 - 1)
        assert indexWidth > 1, (interface.ADDR_WIDTH, indexWidth, "Address is of insufficient size because", interface.DATA_WIDTH, offsetWidth)
        IoProxyAddressed.__init__(self, hls, interface, nativeType)
        self.indexT = HBits(indexWidth)
        self.offsetWidth = offsetWidth
        self._nativeReadTy = _nativeReadTy
        self._nativeWriteTy = _nativeWriteTy
        self.dataWordT = dataWordT
        self.LATENCY_AR_TO_R = LATENCY_AR_TO_R
        self.LATENCY_AW_TO_W = LATENCY_AW_TO_W
        self.LATENCY_W_TO_B = LATENCY_W_TO_B
        self.LATENCY_B_TO_R = LATENCY_B_TO_R
        self.memOrdering = memOrdering
        platform = hls.parentHwModule._target_platform
        platform.installLlvmIoLowerPass(IoLowerAxiMMPass)

    @override
    def getDataWordType(self):
        dtype = self._nativeDataWordTy
        if dtype is None:
            i = self.interface
            if i.HAS_R:
                dtype = i.r.data._dtype
            else:
                assert i.HAS_W, i
                dtype = i.w.data._dtype
            self._nativeDataWordTy = dtype
        return dtype

    @override
    def getDataTypeOfNativeRead(self):
        if self._nativeReadTy is None:
            if self.interface.HAS_R:
                self._nativeReadTy = self._getTypeOfAxiChannel(self.interface.r)
            else:
                self._nativeReadTy = HVoidData
        return self._nativeReadTy

    @override
    def getDataTypeOfNativeWrite(self):
        if self._nativeWriteTy is None:
            if self.interface.HAS_W:
                self._nativeWriteTy = self._getTypeOfAxiChannel(self.interface.w)
            else:
                self._nativeWriteTy = HVoidData
        return self._nativeWriteTy

    @staticmethod
    def _getTypeOfAxiChannel(c: Axi_hs):
        return HwIO_to_HdlType().apply(c, exclude=(c.ready, c.valid))

    @staticmethod
    def _HStructConstToAPInt(v: HStructConstBase, toLlvm: "ToLlvmIrTranslator") -> APInt:
        vFlat = v._reinterpret_cast(HBits(v._dtype.bit_length()))
        assert vFlat._is_full_valid(), "required because we can not create concat with undef for metadata"
        return toLlvm._translateExprHBitsConstToAPIntFullyDefined(vFlat)

    def _getLlvmIoProtocolMetadata(self, toLlvm: "ToLlvmIrTranslator") -> Optional[MDTuple]:
        # :see: doc in :class:`MetadataIoAxiMM`
        axi = self.interface
        toAPInt = self._HStructConstToAPInt
        if axi.HAS_R:
            arT = self._getTypeOfAxiChannel(axi.ar)
            rT = self._getTypeOfAxiChannel(axi.r)
            arDefault = arT.from_py({"addr": 0, "prot": PROT_DEFAULT})
            rDefault = rT.from_py({"data": 0, "resp": RESP_OKAY})
            arDefault = toAPInt(arDefault, toLlvm)
            rDefault = toAPInt(rDefault , toLlvm)
        else:
            arT = None
            rT = None
            arDefault = rDefault = APInt(1, 0)

        if axi.HAS_W:
            awT = self._getTypeOfAxiChannel(axi.aw)
            if axi.HAS_R:
                assert arT == awT, (arT, awT)
            wT = self._getTypeOfAxiChannel(axi.w)
            bT = self._getTypeOfAxiChannel(axi.b)
            awDefault = awT.from_py({"addr": 0, "prot": PROT_DEFAULT})
            wDefault = wT.from_py({"data": 0, "strb": 0})
            bDefault = bT.from_py({"resp": RESP_OKAY})
            awDefault = toAPInt(awDefault, toLlvm)
            wDefault = toAPInt(wDefault , toLlvm)
            bDefault = toAPInt(bDefault , toLlvm)
        else:
            awT = None
            wT = None
            awDefault = wDefault = bDefault = APInt(1, 0)

        aId = (0, 0)
        bId = (0, 0)
        rId = (0, 0)
        wId = (0, 0)
        aT = arT if axi.HAS_R else awT
        addr = (offsetof(aT, aT.field_by_name["addr"]), axi.ADDR_WIDTH)
        len_ = (0, 0)
        rData = (offsetof(rT, rT.field_by_name["data"]), axi.DATA_WIDTH) if axi.HAS_R else (0, 0)
        wData = (offsetof(wT, wT.field_by_name["data"]), axi.DATA_WIDTH) if axi.HAS_W else (0, 0)

        md = MetadataIoAxiMM(
            arDefault,
            rDefault,
            awDefault,
            wDefault,
            bDefault,
            aId,
            bId,
            rId,
            wId,
            addr,
            len_,
            rData,
            wData,
            (2 ** self.offsetWidth) * 8,
            self.LATENCY_AR_TO_R,
            self.LATENCY_AW_TO_W,
            self.LATENCY_W_TO_B,
            self.LATENCY_B_TO_R,
            self.memOrdering,
        )

        return md.toMetadata(toLlvm.ctx)

    @hlsLowLevel
    def read(self, index: Union[AnyHBitsValue], dtype: HdlType=None, isVolatile:bool=True) -> HlsReadAddressed:
        if dtype is not None:
            if dtype.bit_length() != self._nativeReadTy.field_by_name['data'].dtype.bit_length():
                raise NotImplementedError()

        return self.READ_CLS(self,
                              self.interface,
                              index,
                              self._nativeReadTy,
                              isBlocking=True,
                              isVolatile=isVolatile,
                              )

    @hlsLowLevel
    def write(self, index: Union[AnyHBitsValue], data: AnyHBitsValue, mask=NOT_SPECIFIED, isVolatile:bool=True, mayBecomeFlushable=True) -> HlsWriteAddressed:
        if data._dtype.bit_length() != self._nativeWriteTy.field_by_name['data'].dtype.bit_length():
            raise NotImplementedError(data._dtype, self._nativeWriteTy.field_by_name['data'].dtype)
        maskWidth = data._dtype.bit_length() // 8
        if mask is NOT_SPECIFIED:
            assert mask is not None
            maskTy = HBits(maskWidth)
            mask = maskTy.from_py(maskTy.all_mask())
        else:
            mask = HBits(maskWidth).from_py(mask)
        data = mask._concat(data)

        return self.WRITE_CLS(self,
                              data,
                              self.interface,
                              index,
                              self._nativeWriteTy,
                              isVolatile=isVolatile,
                              mayBecomeFlushable=mayBecomeFlushable
                              )

    def _constructAddrWrite(self,
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
        return self._constructAddrWriteRaw(netlist, mirToNetlist, parent, mbSync, addr, aVal, cond)

    def _constructAddrWriteRaw(self,
            netlist: HlsNetlistCtx,
            mirToNetlist:HlsNetlistAnalysisPassMirToNetlist,
            parent: ArchElement,
            mbSync: MachineBasicBlockMeta,
            addr: Axi4Lite_addr,
            addrVal: HlsNetNodeOutAny,
            cond:Union[int, HlsNetNodeOutAny]):

        aNode = HlsNetNodeWrite(netlist, self, addr)
        parent.addNode(aNode)
        addrVal.connectHlsIn(aNode._inputs[0])

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

    def _constructRNode(self,
                        mirToNetlist: HlsNetlistAnalysisPassMirToNetlist,
                        netlist: HlsNetlistCtx,
                        valCache: MirToHwtHlsNetlistValueCache,
                        mbMeta: MachineBasicBlockMeta,
                        srcIo: Axi4Lite_r,
                        _cond: Optional[HlsNetNodeOutAny],
                        instrDstReg: Register):
        rNode = HlsNetNodeRead(netlist, self, srcIo)
        mbMeta.parentElement.addNode(rNode)
        mbMeta.addOrderedNode(rNode)

        mirToNetlist._addExtraCond(rNode, _cond, None)
        mirToNetlist._addSkipWhen_n(rNode, _cond, None)
        rDataO = rNode._portDataOut

        rWordWidth = self.getDataTypeOfNativeRead().bit_length()
        wWordWidth = self.getDataTypeOfNativeWrite().bit_length()
        if rWordWidth < wWordWidth:
            # the read data is larger because pointer representing IO is pointing to a larger word
            # because write is using larger word and this must be the same pointer for reads and writes
            # :note: The next node which uses data output should be the slice to correct width.
            builder = mbMeta.parentElement.builder
            padding = builder.buildConst(HBits(wWordWidth - rWordWidth).from_py(None))
            rDataO = builder.buildConcat(rDataO, padding)
        else:
            assert not self.interface.HAS_W or rWordWidth == wWordWidth

        valCache.add(mbMeta.block, instrDstReg, rDataO, True)
        return rNode

    def _constructBNode(self, mirToNetlist: HlsNetlistAnalysisPassMirToNetlist,
                        netlist: HlsNetlistCtx,
                        mbMeta: MachineBasicBlockMeta,
                        dstIo: Axi4Lite_b,
                        _cond: Optional[HlsNetNodeOutAny]):
        bNode = HlsNetNodeRead(netlist, self, dstIo)
        mbMeta.parentElement.addNode(bNode)

        mirToNetlist._addExtraCond(bNode, _cond, None)
        mirToNetlist._addSkipWhen_n(bNode, _cond, None)
        mbMeta.addOrderedNode(bNode)
        return bNode

    def _translateMirToNetlist_HWTFPGA_CLOAD(self,
                               mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                               mbMeta: MachineBasicBlockMeta,
                               instr: MachineInstr,
                               srcIo: Axi4Lite,
                               srcIoMd: HwtHlsIoMetadata,
                               index: Union[int, HlsNetNodeOutAny],
                               cond: Optional[HlsNetNodeOutAny],
                               instrDstReg: Register) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`~.IoProxy._translateMirToNetlist_HWTFPGA_CLOAD`
        """
        assert self.hasBlockingRead is None or self.hasBlockingRead, self.interface

        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        if srcIoMd.ioPropertyPath is None:
            # the case that the access to this Axi4Lite was not lowered on LLVM IR level
            assert isinstance(srcIo, Axi4Lite), srcIo
            if isinstance(index, int):
                raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", srcIo, instr)

            _cond = cond  # mbMeta.syncTracker.resolveControlOutput(cond)
            aNode = self._constructAddrWrite(netlist, mirToNetlist, mbMeta.parentElement,
                                            mbMeta, srcIo.ar, index, self.offsetWidth, PROT_DEFAULT, _cond)
            if self.LATENCY_AR_TO_R:
                mbMeta.addOrderingDelay(self.LATENCY_AR_TO_R)
            else:
                _cond = mbMeta.parentElement.buildAndOptional(_cond, aNode.getReadyNB())

            rNode = self._constructRNode(mirToNetlist, netlist, valCache, mbMeta, srcIo.r, cond, instrDstReg)

            self._connectUsingExternalDataDep(aNode, rNode)
            return [aNode, rNode]
        else:
            # the case where Axi4Lite was lowered to access to individual channels
            channelName = _MDTupleGetLastString(srcIoMd.ioPropertyPath)
            assert index == 0, index
            if channelName == "ar" or channelName == "aw":
                raise NotImplementedError()
            elif channelName == "r":
                assert isinstance(srcIo, Axi4Lite_r), srcIo
                rNode = self._constructRNode(mirToNetlist, netlist, valCache, mbMeta, srcIo, cond, instrDstReg)
                return [rNode, ]
            elif channelName == "b":
                assert isinstance(srcIo, Axi4Lite_b), srcIo
                bNode = self._constructBNode(mirToNetlist, netlist, mbMeta, srcIo, cond)
                return [bNode, ]
            else:
                raise NotImplementedError(self.interface, channelName)

    def _constructWNode(self, mirToNetlist: HlsNetlistAnalysisPassMirToNetlist,
                        netlist: HlsNetlistCtx,
                        mbMeta: MachineBasicBlockMeta,
                        dstIo: Axi4Lite_w,
                        _cond: Optional[HlsNetNodeOutAny],
                        srcVal: HlsNetNodeOutAny):
        wNode = HlsNetNodeWrite(netlist, self, dstIo)
        mbMeta.parentElement.addNode(wNode)
        assert srcVal._dtype.bit_length() == self._nativeWriteTy.bit_length(), (dstIo, srcVal._dtype, dstIo.DATA_WIDTH)
        srcVal.connectHlsIn(wNode._inputs[0])

        mirToNetlist._addExtraCond(wNode, _cond, None)
        mirToNetlist._addSkipWhen_n(wNode, _cond, None)
        mbMeta.addOrderedNode(wNode)
        return wNode

    @override
    def _translateMirToNetlist_HWTFPGA_CSTORE(self,
            mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
            mbMeta: MachineBasicBlockMeta,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: Axi4Lite,
            dstIoMd: HwtHlsIoMetadata,
            index: Union[int, HlsNetNodeOutAny],
            cond: Optional[HlsNetNodeOutAny],
            bufferCapacity: Optional[int],
            writeNodeCls: TypingType[HlsNetNodeWrite]=HlsNetNodeWrite) -> Sequence[HlsNetNode]:
        assert not bufferCapacity
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        if dstIoMd.ioPropertyPath is None:
            # the case that the access to this Axi4Lite was not lowered on LLVM IR level
            assert isinstance(dstIo, Axi4Lite), dstIo
            if isinstance(index, int):
                raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", dstIo, instr)
            _cond = cond
            # _cond = mbMeta.syncTracker.resolveControlOutput(cond)
            aNode = self._constructAddrWrite(
                netlist, mirToNetlist, mbMeta.parentElement, mbMeta, dstIo.aw, index,
                self.offsetWidth, PROT_DEFAULT, _cond)

            if self.LATENCY_AW_TO_W:
                mbMeta.addOrderingDelay(self.LATENCY_AW_TO_W)
            else:
                _cond = mbMeta.parentElement.builder.buildAndOptional(_cond, aNode.getReadyNB())

            wNode = self._constructWNode(mirToNetlist, netlist, mbMeta, dstIo.w, cond, srcVal)
            self._connectUsingExternalDataDep(aNode, wNode)

            if self.LATENCY_W_TO_B:
                mbMeta.addOrderingDelay(self.LATENCY_W_TO_B)
            else:
                _cond = mbMeta.parentElement.buildAndOptional(_cond, aNode.getReadyNB())

            bNode = self._constructBNode(mirToNetlist, netlist, mbMeta, dstIo.b, cond)
            self._connectUsingExternalDataDep(wNode, bNode)

            return [aNode, wNode, bNode]
        else:
            # the case where Axi4Lite was lowered to access to individual channels
            channelName = _MDTupleGetLastString(dstIoMd.ioPropertyPath)
            assert index == 0, index
            if channelName == "aw" or channelName == "ar":
                aNode = self._constructAddrWriteRaw(
                netlist, mirToNetlist, mbMeta.parentElement, mbMeta, dstIo, srcVal, cond)
                return [aNode, ]
            elif channelName == "w":
                wNode = self._constructWNode(mirToNetlist, netlist, mbMeta, dstIo, cond, srcVal)
                return [wNode, ]
            elif channelName == "r":
                raise NotImplementedError(self.interface)
            elif channelName == "b":
                raise NotImplementedError(self.interface)
            else:
                raise NotImplementedError(self.interface, channelName)

    @override
    @classmethod
    def _getRtlSyncSignals(cls,
                hwIO: Union[Axi_hs, ValidReadyTuple],
                formatAsValidReadyTuple: bool=False,
                ) -> Union[ValidReadyTuple, tuple[Union[RtlSignal, Literal[1]], Union[RtlSignal, Literal[1]]]]:
        if isinstance(hwIO, Axi_hs):
            return (hwIO.valid, hwIO.ready)
        else:
            assert isinstance(hwIO, tuple) and len(hwIO) == 2
            return hwIO

