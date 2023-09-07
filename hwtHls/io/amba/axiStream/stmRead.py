from math import ceil
from typing import Optional, Union

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hdl.value import HValue
from hwt.interfaces.structIntf import Interface_to_HdlType
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getInterfaceName
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.io.amba.axiStream.metadata import addAxiStreamLllvmMetadata
from hwtHls.llvm.llvmIr import Argument, Type
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr, OP_ASSIGN
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axis import AxiStream


class HlsStmReadAxiStream(HlsRead):
    """
    A statement used for reading of chunk of data from AxiStream interface.
    
    :ivar _reliable: If true the input stream is guaranteed to have the data otherwise the presence of data must be checked
        during read FSM generation.
    """

    def __init__(self,
                 parent: "HlsScope",
                 src: AxiStream,
                 dtype: HdlType,
                 reliable: bool):
        super(HlsRead, self).__init__()
        self._isAccessible = True
        self._parent = parent
        self._src = src
        self._reliable = reliable
        self.block: Optional[SsaBasicBlock] = None
        assert isinstance(dtype, HdlType), dtype

        intfName = getInterfaceName(self._parent.parentUnit, src)
        var = parent.var
        name = f"{intfName:s}_read"
        if src.DEST_WIDTH:
            raise NotImplementedError(src)

        if src.ID_WIDTH:
            raise NotImplementedError(src)

        if src.USE_KEEP or src.USE_STRB:
            data_w = dtype.bit_length()
            assert data_w % 8 == 0, data_w
            mask_w = ceil(dtype.bit_length() / 8)
            maskT = Bits(mask_w)

        trueDtype = HStruct(
            (dtype, "data"),
            *(((maskT, "keep"),) if src.USE_KEEP else ()),
            *(((maskT, "strb"),) if src.USE_STRB else ()),
            (BIT, "last"),  # we do not know how many words this read could be last is disjunction of last signals from each word
        )

        sig_flat = var(name, Bits(trueDtype.bit_length()))
        sig_flat.drivers.append(self)
        sig_flat.origin = self
        self._sig = sig_flat
        self._last = None
        self._GEN_NAME_PREFIX = intfName
        SsaInstr.__init__(self, parent.ssaCtx, sig_flat._dtype, OP_ASSIGN, (),
                          origin=sig_flat)
        self._dtypeOrig = dtype

        sig: Interface = sig_flat._reinterpret_cast(trueDtype)
        sig._name = name
        sig._parent = parent.parentUnit
        self._interfaces = sig._interfaces
        # copy all members on this object
        for field_path, field_intf in sig._fieldsToInterfaces.items():
            if len(field_path) == 1:
                n = field_path[0]
                assert not hasattr(self, n), (self, n)
                setattr(self, n, field_intf)

    def replaceBy(self, replacement: Union[SsaValue, HValue]):
        super(HlsStmReadAxiStream, self).replaceBy(replacement)
        self._sig.drivers.remove(self)
        self._sig.drivers.append(replacement)

    @staticmethod
    def _getWordType(intf: AxiStream):
        return Interface_to_HdlType().apply(intf, exclude={intf.ready, intf.valid})

    def _isLast(self):
        """
        :return: an expression which is 1 if this is a last word in the frame
        """
        if self._last is None:
            # generate expression for last on demand
            self._last = self._sig[self._sig._dtype.bit_length() - 1]

        return self._last

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator"):
        toLlvm.addAfterTranslationUnique(addAxiStreamLllvmMetadata)
        src, _, t = toLlvm.ioToVar[self._src]
        src: Argument
        t: Type
        name = toLlvm.strCtx.addTwine(toLlvm._formatVarName(self._name))
        return toLlvm.b.CreateStreamRead(src, self._dtypeOrig.bit_length(), self._sig._dtype.bit_length(), name)

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name")
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {getInterfaceName(self._parent.parentUnit, self._src):s}, {t}>"

