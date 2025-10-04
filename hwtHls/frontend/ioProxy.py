from typing import Optional, Union, Sequence, Type as TypingType, Literal

from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.io.portGroups import BankedPortGroup, MultiPortGroup, \
    iterAllPortGroupVariants
from hwtHls.llvm.llvmIr import MDTuple, MachineInstr, Register, Type, PointerType, HwtHlsIoMetadata
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtLib.handshaked.streamNode import ValidReadyTuple


class IoProxy(object):
    """
    An object managing of translation of HW IO access
    from python to LLVM IR,
    from LLVM MIR to HlsNetlist and
    from HlsNetlist to HWT RTL
    """

    def __init__(self, hls: "HlsScope", interface: Union[HwIO, MultiPortGroup, BankedPortGroup], dtype:Optional[HdlType]=None):
        self.interface = interface
        self._nativeReadTy: Optional[HdlType] = dtype  # :note: use getDataTypeOfNativeRead
        self._nativeWriteTy: Optional[HdlType] = dtype  # :note: use getDataTypeOfNativeWrite
        self._nativeDataWordTy: Optional[HdlType] = None  # :note: use
        self.hls = hls
        self.hasBlockingRead = None
        self.hasBlockingWrite = None
        self.mayBecomeFlushable = None
        if hls is not None and interface is not None:
            for i in iterAllPortGroupVariants(interface):
                # register all interfaces and group to this proxy
                hls._ioProxyForIo[i] = self
        self.T = dtype

    def getDataWordType(self) -> HdlType:
        """
        Get the HdlType which represents just data without any other support signals like byte enable, framing signals etc.
        """
        raise AssertionError("Override this method in implementation of this abstract class", self.__class__)

    def getDataTypeOfNativeRead(self) -> HdlType:
        """
        Get the HdlType of word returned from read of this HwIO.
        This may include support signals like byte enable, framing signals etc.
        
        :attention: the type for read/write may be different.
           This is for example if the write word has write mask and read has not.
        """
        raise AssertionError("Override this method in implementation of this abstract class", self.__class__)

    def getDataTypeOfNativeWrite(self) -> HdlType:
        """
        Equivalent of :meth:`~.getDataTypeOfNativeRead` for write word.
        """
        raise AssertionError("Override this method in implementation of this abstract class", self.__class__)

    def _getInterfaceTypeForLlvmFnArg(self, toLlvm: 'ToLlvmIrTranslator',
                                      ioIndex: int) -> tuple[Type, Type]:
        """
        Get llvm pointer and item type to represent this this IO in argument os functions
        and load/gep/store and alike instructions.
        """
        width = max(self.getDataTypeOfNativeRead().bit_length(), 1)
        if self.hasBlockingRead is not None and not self.hasBlockingRead:
            width += 1

        width = max(width, self.getDataTypeOfNativeWrite().bit_length())

        ptrT = PointerType.get(toLlvm.ctx, ioIndex + 1)
        elmT = Type.getIntNTy(toLlvm.ctx, width)
        addrWidth = 0

        return ptrT, elmT, addrWidth

    def _getLlvmIoProtocolMetadata(self, toLlvm: "ToLlvmIrTranslator") -> Optional[MDTuple]:
        pass

    def updateLlvmHwtHlsIoMetadata(self, tr: "ToLlvmIrTranslator", md: HwtHlsIoMetadata) -> bool:
        """
        This prepares HwtHlsIoMetadata metadata
        :returns: True if some change has been made
        """
        return False

    def _translateMirToNetlist_HWTFPGA_CLOAD(self,
                               mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                               mbMeta: "MachineBasicBlockMeta",
                               instr: MachineInstr,
                               srcIo: HwIO,
                               srcIoMd: HwtHlsIoMetadata,
                               index: Union[int, HlsNetNodeOutAny],
                               cond: Optional[HlsNetNodeOutAny],
                               instrDstReg: Register) -> Sequence[HlsNetNode]:
        """
        This method is called to generated HlsNetlist nodes from LLVM MIR.
        The purpose of this function is to make this translation customizable for specific :class:`hwt.hwIO.HwIO` instances.

        :param representativeReadStm: Any found read for this interface before LLVM opt.
            We can not find the original because optimization process may remove and generate new reads and exact mapping can not be found.
            This may be used to find meta informations about interface.
        :param mirToNetlist: Main object form LLVM MIR to HlsNetlist translation.
        :param instr: LLVM MIR instruction which is being translated
        :param srcIo: An interface used by this instruction.
        :param index: An index to specify the address used in this read.
        :param cond: An enable condition for this operation to happen.
        :param instrDstReg: A register where this instruction stores the read data.
        """
        raise AssertionError("Override this method in implementation of this abstract class", self.__class__)

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
            writeNodeCls: TypingType[HlsNetNodeWrite]=HlsNetNodeWrite) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`~.IoProxy._translateMirToNetlist_HWTFPGA_CLOAD`
        """
        raise AssertionError("Override this method in implementation of this abstract class", self.__class__)

    @classmethod
    def _getRtlSyncSignals(cls,
                hwIO: Union[HwIO, ValidReadyTuple],
                formatAsValidReadyTuple: bool=False,
                ) -> Union[ValidReadyTuple, tuple[Union[RtlSignal, Literal[1]], Union[RtlSignal, Literal[1]]]]:
        raise AssertionError("Override this method in implementation of this abstract class", cls)

    @classmethod
    def _getRtlSyncTuple(cls, hwIO: Union[HwIO, ValidReadyTuple]):
        return cls._getRtlSyncSignals(hwIO, formatAsValidReadyTuple=True)

