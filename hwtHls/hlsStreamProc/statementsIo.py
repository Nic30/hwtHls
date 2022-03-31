from enum import Enum
from math import ceil
from typing import Optional, Union

from hwt.doc_markers import internal
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.signalOps import SignalOps
from hwt.interfaces.std import Handshaked, Signal, VldSynced
from hwt.interfaces.structIntf import StructIntf, Interface_to_HdlType
from hwt.interfaces.unionIntf import UnionSink, UnionSource
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.hlsStreamProc.statements import HlsStreamProcStm
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr, OP_ASSIGN
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axis import AxiStream


class IN_STREAM_POS(Enum):
    """
    Enum for position of chunk of data inside of stream.
    """
    BEGIN_OR_BODY_OR_END = "ANY"
    BEGIN = "BEGIN"  # if first but not last data chunk in frame
    BEGIN_END = "BEGIN_END"  # is first and last data chunk in frame
    BODY = "BODY"  # is not first not last data chunk in frame
    END_OR_BODY = "END_OR_BODY"  # could be at last data chunk in frame
    END = "END"  # is last data chunk in frame

    def isBegin(self):
        return self in (IN_STREAM_POS.BEGIN_OR_BODY_OR_END, IN_STREAM_POS.BEGIN, IN_STREAM_POS.BEGIN_END)

    def isEnd(self):
        return self in (IN_STREAM_POS.BEGIN_OR_BODY_OR_END, IN_STREAM_POS.BEGIN_END, IN_STREAM_POS.END)


ANY_HLS_STREAM_INTF_TYPE = Union[AxiStream, Handshaked, VldSynced,
                                 HsStructIntf, RtlSignal, Signal,
                                 UnionSink, UnionSource]


class HlsStreamProcRead(HdlStatement, SignalOps, InterfaceBase, SsaInstr):
    """
    Container of informations about read from some stream
    """

    def __init__(self,
                 parent: "HlsStreamProc",
                 src: ANY_HLS_STREAM_INTF_TYPE,
                 dtype: HdlType):
        super(HlsStreamProcRead, self).__init__()
        self._isAccessible = True
        self._parent = parent
        self._src = src
        self.block: Optional[SsaBasicBlock] = None
            
        intfName = getSignalName(src)
        var = parent.var
        name = f"{intfName:s}_read"
        sig = var(name, dtype)
        if isinstance(sig, Interface):
            sig_flat = var(name, Bits(dtype.bit_length()))
            # use flat signal and make type member fields out of slices of that signal
            sig = sig_flat._reinterpret_cast(dtype)
            sig._name = name
            sig_flat.drivers.append(self)
            sig_flat.origin = self
    
        else:
            sig_flat = sig
            sig.drivers.append(self)
            sig.origin = self

        self._sig = sig_flat
        self._GEN_NAME_PREFIX = intfName
        SsaInstr.__init__(self, parent.ssaCtx, sig_flat._dtype, OP_ASSIGN, (),
                          origin=sig)

        if isinstance(sig, StructIntf):
            self._interfaces = sig._interfaces
            # copy all members on this object
            for field_path, field_intf in sig._fieldsToInterfaces.items():
                if len(field_path) == 1:
                    n = field_path[0]
                    assert not hasattr(self, n), (self, n)
                    setattr(self, n, field_intf)
        else:
            self._interfaces = []

    @internal
    def _get_rtl_context(self) -> 'RtlNetlist':
        return self._parent.ctx

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name")
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {getSignalName(self._src):s}, {t}>"


class HlsStreamProcReadAxiStream(HlsStreamProcRead):
        
    def __init__(self,
                 parent: "HlsStreamProc",
                 src: AxiStream,
                 dtype: HdlType,
                 inStreamPos=IN_STREAM_POS.BODY):
        super(HlsStreamProcRead, self).__init__()
        self._isAccessible = True
        assert isinstance(inStreamPos, IN_STREAM_POS), inStreamPos
        self._inStreamPos = inStreamPos
        self._parent = parent
        self._src = src
        self.block: Optional[SsaBasicBlock] = None
        assert isinstance(dtype, HdlType), dtype
            
        intfName = getSignalName(src)
        var = parent.var
        name = f"{intfName:s}_read"
        if src.DEST_WIDTH:
            raise NotImplementedError()
        
        if src.ID_WIDTH:
            raise NotImplementedError()
        
        if src.USE_KEEP or src.USE_STRB:
            data_w = dtype.bit_length()
            assert data_w % 8 == 0, data_w
            mask_w = ceil(dtype.bit_length() / 8)
            maskT = Bits(mask_w)

        trueDtype = HStruct(
            (dtype, "data"),
            *(((maskT, "keep"), ) if src.USE_KEEP else ()),
            *(((maskT, "strb"), ) if src.USE_STRB else ()),
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


    @staticmethod
    def _getWordType(intf: AxiStream):
        return Interface_to_HdlType().apply(intf, exclude={intf.ready, intf.valid})

    def _isLast(self):
        """
        :return: an expression which is 1 if this is a last word in the frame
        """
        if self._last is None:
            self._last = self._sig[self._sig._dtype.bit_length() - 1]

        return self._last

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name")
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {getSignalName(self._src):s}, {t}, {self._inStreamPos.name}>"


class HlsStreamProcWrite(HlsStreamProcStm, SsaInstr):
    """
    Container of informations about write in some stream
    """

    def __init__(self,
                 parent: "HlsStreamProc",
                 src:Union[SsaValue, Handshaked, AxiStream, bytes, HValue],
                 dst: Union[AxiStream, Handshaked]):
        HlsStreamProcStm.__init__(self, parent)
        if isinstance(src, int):
            dtype = getattr(dst, "_dtype", None)
            if dtype is None:
                dtype = dst.data._dtype
            src = dtype.from_py(src)
        else:
            dtype = src._dtype

        if isinstance(dst, RtlSignal):
            intf, indexes, sign_cast_seen = dst._getIndexCascade()
            if intf is not dst or indexes:
                raise NotImplementedError()

        SsaInstr.__init__(self, parent.ssaCtx, dtype, OP_ASSIGN, ())
        # [todo] this put this object in temporary inconsistent state,
        #  because src can be more than just SsaValue/HValue instance
        self.operands = (src,)
        self.parent = parent

        # store original source for debugging
        self._orig_src = src
        self.dst = dst

    def getSrc(self):
        assert len(self.operands) == 1, self
        return self.operands[0]

    def __repr__(self):
        i = self.operands[0]
        return f"<{self.__class__.__name__} {i if isinstance(i, HValue) else i._name}->{getSignalName(self.dst)}>"
