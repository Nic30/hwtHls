from math import ceil
from typing import Optional, Union

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOStruct import HwIO_to_HdlType, HwIOStruct
from hwt.mainBases import RtlSignalBase
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_getName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.code import  zextToTy
from hwtHls.frontend.statementsRead import HlsRead, \
    _copySliceNamesToFlattenedSignal
from hwtHls.llvm.llvmIr import Argument, Type, BasicBlock
from hwtHls.ssa.translation.toLlvmArgumentUtils import getArgumentForHwIO
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from hwtLib.amba.axi4s import Axi4Stream


class HlsStmReadAxi4Stream(HlsRead):
    """
    A statement used for reading of chunk of data from Axi4Stream interface.
    
    :ivar _isReliable: If true the input stream is guaranteed to have the data
        otherwise the presence of data must be checked during read FSM generation.
        Setting this to false can significantly simplify read FSM but malformed
        input data will result in undefined behavior.
    """

    def __init__(self,
                 ioProxy: "IoProxyAxi4Stream",
                 src: Axi4Stream,
                 dtype: HdlType,
                 isReliable: bool):
        super(HlsRead, self).__init__()
        self._isAccessible = True
        self._ioProxy = ioProxy
        self._src = src
        self._isReliable = isReliable
        self._isBlocking = True
        self._isVolatile = True
        assert isinstance(dtype, HdlType), dtype

        hwIOName = HwIO_getName(ioProxy.hls.parentHwModule, src)
        var = ioProxy.hls.var
        name = f"{hwIOName:s}_read"
        trueDtype = self._constructTypeOfInterfaceData(src, dtype)

        sig_flat = var(name, HBits(trueDtype.bit_length()))
        sig_flat._rtlDrivers.append(self)
        sig_flat._rtlObjectOrigin = self
        self._sig = sig_flat
        self._GEN_NAME_PREFIX = hwIOName
        self._dtype = sig_flat._dtype
        self._dtypeOrig = dtype

        self._name = name
        sig: HwIO = sig_flat._reinterpret_cast(trueDtype)
        sig._name = name
        sig._parent = ioProxy.hls.parentHwModule
        self._hwIOs = sig._hwIOs
        _copySliceNamesToFlattenedSignal(sig_flat, trueDtype, name, 0)

        # copy all members on this object
        self._copyRtlSignalsToSelf(sig)

    def _constructTypeOfInterfaceData(self, src: Axi4Stream, dtype: HdlType):
        """
        Construct HdlType which contains all data from interface.
        This type may contain additional signals for masks, last, and other signals
        which are physically present on interface and are not necessary just the data.
        
        :param dtype: a type of data which is read.
        """
        if src.DEST_WIDTH:
            raise NotImplementedError(src)

        if src.ID_WIDTH:
            raise NotImplementedError(src)

        if not self._isReliable and (src.USE_KEEP or src.USE_STRB):
            data_w = dtype.bit_length()
            assert data_w % 8 == 0, data_w
            mask_w = ceil(dtype.bit_length() / 8)
            maskT = HBits(mask_w)

        trueDtype = HStruct(
            (dtype, "data"),
            *(((maskT, "keep"),) if not self._isReliable and src.USE_KEEP else ()),
            *(((maskT, "strb"),) if not self._isReliable and src.USE_STRB else ()),
            (BIT, "last"),  # we do not know how many words this read could be,
                           # the eof is disjunction of eof signals from each word
        )
        return trueDtype

    def _copyRtlSignalsToSelf(self, sig: HwIOStruct):
        """
        Copy members of sig which is virtual IO
        (which represents represents this read value in frontend AST expressions)
        to this object properties.
        """
        self.data: RtlSignal
        self.last: RtlSignal
        self.strb: Optional[RtlSignal]
        self.keep: Optional[RtlSignal]
        self.user: Optional[RtlSignal]
        for field_path, fieldHwIO in sig._fieldsToHwIOs.items():
            if len(field_path) == 1:
                n = field_path[0]
                assert not hasattr(self, n), (self, n)
                setattr(self, n, fieldHwIO)

    @staticmethod
    def _getWordType(hwIO: Axi4Stream):
        return HwIO_to_HdlType().apply(hwIO, exclude={hwIO.ready, hwIO.valid})

    def _isEoF(self):
        """
        :return: an expression which is 1 if this is a last word in the frame
        """
        return self.last

    def _isValid(self) -> AnyHBitsValue:
        """
        :return: an expression which is 1 if all bytes of data are marked valid by mask (strb/keep)
        """
        src = self._src
        if self._isReliable:
            return b1
        if src.USE_STRB:
            mask = self.strb
            if src.USE_KEEP:
                mask = mask & self.keep
        elif src.USE_KEEP:
            mask = self.keep
        else:
            mask = None

        if mask is None:
            return b1
        else:
            if mask._dtype.bit_length() == 1:
                v = mask
            else:
                v = mask._eq(mask._dtype.all_mask())
            return v

    @override
    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator", bb: BasicBlock):
        src, elmT = getArgumentForHwIO(toLlvm, self._src, self._ioProxy, self, True)
        src: Argument
        t: Type
        name = toLlvm.strCtx.addTwine(self._name)
        v = toLlvm.b.CreateStreamRead(src,
                                      self._dtypeOrig.bit_length(),  # chunkBitWidth
                                      self._sig._dtype.bit_length(),  # returnBitWidth
                                      self._isReliable, name)
        return toLlvm._translateToLlvm_HlsRead_registerVar(bb, self, v)

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name", None)
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {HwIO_getName(self._ioProxy.hls.parentHwModule, self._src):s}, {t}>"


class HlsStmReadAxi4StreamSegmented(HlsStmReadAxi4Stream):

    def __init__(self,
                 ioProxy: "IoProxyAxi4Stream",
                 src: Axi4StreamSegmented,
                 dtype: HdlType,
                 reliable: bool):
        HlsStmReadAxi4Stream.__init__(self, ioProxy, src, dtype, reliable)

    @override
    def _constructTypeOfInterfaceData(self, src: Axi4StreamSegmented, dtype: HdlType):
        """
        :see: :meth:`~.HlsStmReadAxi4Stream._constructTypeOfInterfaceData`
        """
        dataWidth = dtype.bit_length()

        hasEmpty = not self._isReliable and src._hasEmpty(dataWidth, src.BYTE_WIDTH, src.SUPPORT_ZLP)
        if hasEmpty:
            emptyWidth = src._getWidthOfEmpty(dtype.bit_length(), src.BYTE_WIDTH, src.SUPPORT_ZLP)

        trueDtype = HStruct(
            (dtype, "data"),
            *(((BIT, "enable"),) if src._hasEnable(src.SEGMENT_CNT) else ()),
            *(((BIT, "sof"),) if src.USE_SOF else ()),
            (BIT, "eof"),  # we do not know how many words this read could be,
                           # the eof is disjunction of eof signals from each word
            * (((HBits(src.ERROR_WIDTH), "err"),) if src.ERROR_WIDTH else ()),
            *(((HBits(emptyWidth), "empty"),) if hasEmpty else ()),
        )
        return trueDtype

    def _isEoF(self):
        return self.eof

    @override
    def _copyRtlSignalsToSelf(self, sig: HwIOStruct):
        """
        Copy members of sig which is virtual IO
        (which represents represents this read value in frontend AST expressions)
        to this object properties.
        """
        self.data: RtlSignal
        self.enable: RtlSignal
        self.sof: Optional[RtlSignal]
        self.eof: Optional[RtlSignal]
        self.err: Optional[RtlSignal]
        self.empty: Optional[RtlSignal]
        for field_path, fieldHwIO in sig._fieldsToHwIOs.items():
            if len(field_path) == 1:
                n = field_path[0]
                assert not hasattr(self, n), (self, n)
                setattr(self, n, fieldHwIO)

    def getSize(self) -> Union[int, RtlSignalBase[HBits]]:
        dataT = self.data._dtype
        dataBytesCnt = dataT.bit_length() // self._src.BYTE_WIDTH
        src: Axi4StreamSegmented = self._src
        if src._hasEmpty(src.SEGMENT_DATA_WIDTH, src.BYTE_WIDTH, src.SUPPORT_ZLP):
            sizeT = HBits(self.empty._dtype.bit_length() + 1)
            # setHasNoUnsignedWrap
            return sizeT.from_py(dataBytesCnt) - zextToTy(self.empty, sizeT)
        else:
            return dataBytesCnt
