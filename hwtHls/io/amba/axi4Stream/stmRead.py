from math import ceil
from typing import Optional, Union

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hdl.const import HConst
from hwt.hwIOs.hwIOStruct import HwIO_to_HdlType
from hwt.hwIO import HwIO
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_getName
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.io.amba.axi4Stream.metadata import addAxi4StreamLllvmMetadata
from hwtHls.llvm.llvmIr import Argument, Type
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr, OP_ASSIGN
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi4s import Axi4Stream


class HlsStmReadAxi4Stream(HlsRead):
    """
    A statement used for reading of chunk of data from Axi4Stream interface.
    
    :ivar _reliable: If true the input stream is guaranteed to have the data otherwise the presence of data must be checked
        during read FSM generation.
    """

    def __init__(self,
                 parent: "HlsScope",
                 src: Axi4Stream,
                 dtype: HdlType,
                 reliable: bool):
        super(HlsRead, self).__init__()
        self._isAccessible = True
        self._parent = parent
        self._src = src
        self._reliable = reliable
        self.block: Optional[SsaBasicBlock] = None
        assert isinstance(dtype, HdlType), dtype

        hwIOName = HwIO_getName(self._parent.parentHwModule, src)
        var = parent.var
        name = f"{hwIOName:s}_read"
        if src.DEST_WIDTH:
            raise NotImplementedError(src)

        if src.ID_WIDTH:
            raise NotImplementedError(src)

        if src.USE_KEEP or src.USE_STRB:
            data_w = dtype.bit_length()
            assert data_w % 8 == 0, data_w
            mask_w = ceil(dtype.bit_length() / 8)
            maskT = HBits(mask_w)

        trueDtype = HStruct(
            (dtype, "data"),
            *(((maskT, "keep"),) if src.USE_KEEP else ()),
            *(((maskT, "strb"),) if src.USE_STRB else ()),
            (BIT, "last"),  # we do not know how many words this read could be last is disjunction of last signals from each word
        )

        sig_flat = var(name, HBits(trueDtype.bit_length()))
        sig_flat.drivers.append(self)
        sig_flat.origin = self
        self._sig = sig_flat
        self._last = None
        self._GEN_NAME_PREFIX = hwIOName
        SsaInstr.__init__(self, parent.ssaCtx, sig_flat._dtype, OP_ASSIGN, (),
                          origin=sig_flat)
        self._dtypeOrig = dtype

        sig: HwIO = sig_flat._reinterpret_cast(trueDtype)
        sig._name = name
        sig._parent = parent.parentHwModule
        self._hwIOs = sig._hwIOs
        # copy all members on this object
        for field_path, fieldHwIO in sig._fieldsToHwIOs.items():
            if len(field_path) == 1:
                n = field_path[0]
                assert not hasattr(self, n), (self, n)
                setattr(self, n, fieldHwIO)

    def replaceBy(self, replacement: Union[SsaValue, HConst]):
        super(HlsStmReadAxi4Stream, self).replaceBy(replacement)
        self._sig.drivers.remove(self)
        self._sig.drivers.append(replacement)

    @staticmethod
    def _getWordType(hwIO: Axi4Stream):
        return HwIO_to_HdlType().apply(hwIO, exclude={hwIO.ready, hwIO.valid})

    def _isLast(self):
        """
        :return: an expression which is 1 if this is a last word in the frame
        """
        if self._last is None:
            # generate expression for last on demand
            self._last = self._sig[self._sig._dtype.bit_length() - 1]

        return self._last

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator"):
        toLlvm.addAfterTranslationUnique(addAxi4StreamLllvmMetadata)
        src, _, t = toLlvm.ioToVar[self._src]
        src: Argument
        t: Type
        name = toLlvm.strCtx.addTwine(toLlvm._formatVarName(self._name))
        return toLlvm.b.CreateStreamRead(src, self._dtypeOrig.bit_length(), self._sig._dtype.bit_length(), name)

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name", None)
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {HwIO_getName(self._parent.parentHwModule, self._src):s}, {t}>"

