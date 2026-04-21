from typing import Optional, Union, Type as TypingType, Sequence, Literal

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOArray import HwIOArray
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld, HwIO_to_HdlType, HwIOStruct
from hwt.hwIOs.std import HwIODataRdVld, HwIORdVldSync, HwIODataVld, HwIODataRd, \
    HwIOSignal, HwIOVldSync, HwIORdSync, HwIOBramPort_noClk
from hwt.mainBases import RtlSignalBase
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.hObjListUtils import HwIOArray_getHdlType
from hwtHls.frontend.ioProxy import IoProxy
from hwtHls.frontend.ioProxyScalarHlsNetlistAgent import HlsNetlistSimAgentScalarDriver, \
    HlsNetlistSimAgent, HlsNetlistSimAgentScalarMonitor
from hwtHls.frontend.statementsRead import HlsRead
from hwtHls.frontend.statementsWrite import HlsWrite
from hwtHls.io.portGroups import getFirstInterfaceInstance, MultiPortGroup, \
    BankedPortGroup
from hwtHls.llvm.llvmIr import MachineInstr, Register, HwtHlsIoMetadata
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidExternData
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtLib.amba.axi_common import Axi_hs
from hwtLib.handshaked.streamNode import ValidReadyTuple
from ipCorePackager.constants import INTF_DIRECTION


class IoProxyScalar(IoProxy):
    '''
    A default object which builds read/write statements for specified interface.
    
    :note: it is important that this is 1 class for loads and stores together
        as some IO like Axi4 may fall appart to individual channel operations
        and we need some object to construct the HlsNetlistNodes for interface.
        If this would be just for load the store to read address channel
        would not have an object to construct its node.
    '''

    def getNativeTypeOfHwIoWithoutSyncSignals(self, src: HwIO):
        if isinstance(src, MultiPortGroup):
            return self.getNativeTypeOfHwIoWithoutSyncSignals(src[0])

        if type(src) is HwIORdVldSync:
            return HVoidExternData
        dtype = getattr(src, "_dtype", None)
        if dtype is not None:
            return dtype
        dtype = getattr(src, "T", None)
        if dtype is not None:
            return dtype
        if isinstance(src, (HwIODataRdVld, HwIOStructRdVld, HwIORdVldSync, Axi_hs)):
            if hasattr(src, "data") and len(src._hwIOs) == 3:
                dtype = HwIO_to_HdlType().apply(src.data, exclude=(src.vld,))
            elif isinstance(src, HwIODataRdVld) and not hasattr(src, "_hwIOs"):
                # caase for forward declarations which do not have subsignals instantiated yet
                dtype = HBits(src.DATA_WIDTH)
            else:
                if isinstance(src, Axi_hs):
                    exclude = (src.ready, src.valid)
                else:
                    exclude = (src.rd, src.vld)
                dtype = HwIO_to_HdlType().apply(src, exclude=exclude)

        elif isinstance(src, HwIOVldSync):
            if hasattr(src, "data") and len(src._hwIOs) == 2:
                dtype = HwIO_to_HdlType().apply(src.data, exclude=(src.vld,))
            elif isinstance(src, HwIODataVld) and not hasattr(src, "_hwIOs"):
                # caase for forward declarations which do not have subsignals instantiated yet
                dtype = HBits(src.DATA_WIDTH)
            else:
                dtype = HwIO_to_HdlType().apply(src, exclude=(src.vld,))

        elif isinstance(src, HwIORdSync):
            if hasattr(src, "data") and len(src._hwIOs) == 2:
                dtype = HwIO_to_HdlType().apply(src.data, exclude=(src.rd,))
            elif isinstance(src, HwIODataRd) and not hasattr(src, "_hwIOs"):
                # caase for forward declarations which do not have subsignals instantiated yet
                dtype = HBits(src.DATA_WIDTH)
            else:
                dtype = HwIO_to_HdlType().apply(src, exclude=(src.rd,))

        elif isinstance(src, RtlSignal):
            assert src._rtlCtx is not self._rtlCtx, ("Read should be used only for IO, it is not required for HLS variables")
            dtype = src._dtype

        elif isinstance(src, (HwIOSignal, HwIOStruct)):
            dtype = src._dtype
        elif isinstance(src, HwIOArray):
            dtype = HwIOArray_getHdlType(src)
        else:
            raise NotImplementedError(src)

        if dtype.bit_length() == 0:
            # if there is no data, the dtype will be empty struct
            return HVoidExternData
        else:
            return dtype

    @override
    def getDataTypeOfNativeRead(self):
        """
        Get the HdlType of data returned from read of this HwIO
        """
        if self._nativeReadTy is not None:
            return self._nativeReadTy

        src = getFirstInterfaceInstance(self.interface)
        dtype = self.getNativeTypeOfHwIoWithoutSyncSignals(src)
        self._nativeReadTy = dtype
        return dtype

    def getDataTypeOfNativeWrite(self):
        if self._nativeWriteTy is not None:
            return self._nativeWriteTy

        dst = getFirstInterfaceInstance(self.interface)
        dtype = self.getNativeTypeOfHwIoWithoutSyncSignals(dst)
        self._nativeWriteTy = dtype
        return dtype

    @classmethod
    def _getHdlTypeOfValue(cls, v, suggestedType: Optional[HdlType]) -> HdlType:
        if isinstance(v, HwIOArray):
            return cls._getHdlTypeOfValue(v[0], suggestedType.element_t)[len(v)]
        else:
            return v._dtype

    def write(self, src, isVolatile=True, mayBecomeFlushable=True):
        dstTy = self.getDataTypeOfNativeWrite()
        if src is None or isinstance(src, int):
            src = dstTy.from_py(src)
            dtype = dstTy
        else:
            dtype = self._getHdlTypeOfValue(src, dstTy)
            assert dtype.bit_length() == dstTy.bit_length(), (
                "For a blocking write the width of src and dst must match", dtype, "->", dstTy, src, self.interface)

        dst = self.interface
        if isinstance(dst, HwIO):
            assert dst._direction != INTF_DIRECTION.MASTER, (dst, "Can not write to input")

        if self.mayBecomeFlushable is None:
            self.mayBecomeFlushable = mayBecomeFlushable
        else:
            assert self.mayBecomeFlushable == mayBecomeFlushable, (self.interface, "mayBecomeFlushable flag must be the same for all writes to same IO")

        return HlsWrite(self, src, dst, dtype, isVolatile, mayBecomeFlushable=mayBecomeFlushable)

    def read(self, blocking=True, isVolatile=True):
        assert isinstance(blocking, bool), blocking
        if isinstance(self.interface, HwIO):
            assert self.interface._direction != INTF_DIRECTION.SLAVE, (self.interface, "Can not read from output")

        if self.hasBlockingRead is None:
            self.hasBlockingRead = blocking
        else:
            assert self.hasBlockingRead == blocking, (self.hasBlockingRead, blocking, "Can not combine blocking and unblocking reads")
        return HlsRead(self, self.interface, self.getDataTypeOfNativeRead(), blocking, isVolatile)

    @override
    def _translateMirToNetlist_HWTFPGA_CLOAD(self,
                               mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
                               mbMeta: "MachineBasicBlockMeta",
                               instr: MachineInstr,
                               srcIo: Union[HwIO, RtlSignalBase],
                               srcIoMd: HwtHlsIoMetadata,
                               index: Union[int, HlsNetNodeOutAny],
                               cond: Optional[HlsNetNodeOutAny],
                               instrDstReg: Register,
                               readNodeCls: TypingType[HlsNetNodeRead]=HlsNetNodeRead) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`~.IoProxy._translateMirToNetlist_HWTFPGA_CLOAD`
        """
        assert self.interface is srcIo, (self, srcIo)
        dtype = self.getDataTypeOfNativeRead()
        isBlocking = True if self.hasBlockingRead is None else self.hasBlockingRead
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, (HwIO, RtlSignalBase, tuple, MultiPortGroup, BankedPortGroup)), srcIo
        assert isinstance(index, int) and index == 0, (srcIo, index, "Because this read is not addressed there should not be any index")

        if (isinstance(dtype, HBits) and dtype.signed is not None) or not dtype.isScalar():
            dtype = HBits(dtype.bit_length())

        mirExpectedWidth = mirToNetlist.mf.getRegInfo().getType(instrDstReg).getScalarSizeInBits()
        if isBlocking:
            assert mirExpectedWidth == max(1, dtype.bit_length()), (
                "Width of physical signals of IO must be what is expected from LLVM MIR", instrDstReg, mirExpectedWidth, dtype)
        else:
            assert mirExpectedWidth == max(1, dtype.bit_length() + 1), (
                "Width of physical signals of IO must be what is expected from LLVM MIR", instrDstReg, mirExpectedWidth, dtype)
        n: HlsNetNodeRead = readNodeCls(netlist,
                           self,
                           srcIo,
                           dtype=dtype,
                           name=f"ld_r{instr.getOperand(0).getReg().virtRegIndex():d}")
        assert n.ioProxy is self, n
        mbMeta.parentElement.addNode(n)
        if not isBlocking:
            n.setNonBlocking()

        mirToNetlist._addExtraCond(n, cond, mbMeta.blockEn)
        mirToNetlist._addSkipWhen_n(n, cond, mbMeta.blockEn)
        mbMeta.addOrderedNode(n)
        if isBlocking:
            o = n._portDataOut
            if dtype.bit_length() == 0:
                assert instr.getOperand(0).isDead(), (
                "This is read of void, i1 is used for compatibility with LLVM, there should not be any actual use of read data", instr)

        else:
            o = n.getRawValue()
            # if dtype.bit_length() == 0:
            #    assert n._portDataOut is None, n
            # if dtype.bit_length() == 0:
            #    # must extend because MIR represented void with 1b int and in HlsNetlist there is void
            #    #b: HlsNetlistBuilder = n.getHlsNetlistBuilder()
            #    #o = b.buildConcat(o, o)
        if not isBlocking or dtype.bit_length() != 0:
            assert not isinstance(o._dtype, HBits) or not o._dtype.signed, (
                "At this stage all values of HBits type should have signed=None", o, instr)  # can potentially be of void type
            valCache.add(mbMeta.block, instrDstReg, o, True)
        return [n, ]

    @override
    def _translateMirToNetlist_HWTFPGA_CSTORE(self,
            mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
            mbMeta: "MachineBasicBlockMeta",
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: Union[HwIO, RtlSignal],
            dstIoMd: HwtHlsIoMetadata,
            index: Union[int, HlsNetNodeOutAny],
            cond: Optional[HlsNetNodeOutAny],
            bufferCapacity: Optional[int],
            writeNodeCls: TypingType[HlsNetNodeWrite]=HlsNetNodeWrite,
            writeNodeConstructorKwArgs={}) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`~.IoProxy._translateMirToNetlist_HWTFPGA_CLOAD`
        """
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        # srcVal, dstIo, index, cond = ops
        assert isinstance(dstIo, (HwIO, tuple, RtlSignal)), dstIo
        assert isinstance(index, int) and index == 0, (instr, index, "Because this read is not addressed there should not be any index")
        n = writeNodeCls(netlist, self, dstIo,
                         mayBecomeFlushable=self.mayBecomeFlushable,
                         bufferCapacity=bufferCapacity,
                         **writeNodeConstructorKwArgs)
        assert n.ioProxy is self, n
        mbMeta.parentElement.addNode(n)
        srcVal.connectHlsIn(n._inputs[0])

        _cond = cond
        # _cond = mbMeta.syncTracker.resolveControlOutput(cond)
        mirToNetlist._addExtraCond(n, _cond, None)
        mirToNetlist._addSkipWhen_n(n, _cond, None)
        mbMeta.addOrderedNode(n)
        return [n, ]

    @override
    def getHlsNetlistSimAgentMonitor(self, data: list) -> HlsNetlistSimAgent:
        return HlsNetlistSimAgentScalarMonitor(self, data)

    @override
    def getHlsNetlistSimAgentDriver(self, data: Sequence) -> HlsNetlistSimAgent:
        return HlsNetlistSimAgentScalarDriver(self, data)

    @override
    @staticmethod
    def _getRtlSyncSignals(
                hwIO: Union[HwIORdVldSync, HwIORdSync, HwIOVldSync, RtlSignalBase, HwIOSignal, ValidReadyTuple],
                formatAsValidReadyTuple: bool=False,
                ) -> Union[ValidReadyTuple, tuple[Union[RtlSignal, Literal[1]], Union[RtlSignal, Literal[1]]]]:
        if isinstance(hwIO, tuple):
            # expect ValidReadyTuple
            assert len(hwIO) == 2, hwIO
            assert isinstance(hwIO[0], (int, RtlSignalBase, HwIOSignal)), hwIO
            assert isinstance(hwIO[1], (int, RtlSignalBase, HwIOSignal)), hwIO
            return hwIO
        elif isinstance(hwIO, Axi_hs):
            return (hwIO.valid, hwIO.ready)
        elif isinstance(hwIO, (HwIODataRdVld, HwIORdVldSync)):
            return (hwIO.vld, hwIO.rd)
        elif isinstance(hwIO, HwIOVldSync):
            if formatAsValidReadyTuple:
                return (hwIO.vld, 1)
            else:
                return (hwIO.vld,)
        elif isinstance(hwIO, HwIOBramPort_noClk):
            if formatAsValidReadyTuple:
                return (hwIO.en, 1)
            else:
                return (hwIO.en,)
        elif isinstance(hwIO, HwIORdSync):
            if formatAsValidReadyTuple:
                return (1, hwIO.rd)
            else:
                return (hwIO.rd,)
        elif isinstance(hwIO, (RtlSignalBase, HwIOSignal, HwIOArray, HwIOStruct)):
            if formatAsValidReadyTuple:
                return (1, 1)
            else:
                return ()
        else:
            raise TypeError("Unknown synchronization of ", hwIO)

