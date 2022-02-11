from io import StringIO
from typing import Union, Optional, List

from hdlConvertorAst.translate.common.name_scope import NameScope
from hwt.doc_markers import internal
from hwt.hdl.statements.codeBlockContainer import HdlStmCodeBlockContainer
from hwt.hdl.statements.ifContainter import IfContainer
from hwt.hdl.statements.statement import HdlStatement, HwtSyntaxError
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.signalOps import SignalOps
from hwt.interfaces.std import Handshaked, Signal, VldSynced
from hwt.interfaces.structIntf import StructIntf, HdlType_to_Interface
from hwt.interfaces.unionIntf import UnionSink, UnionSource
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName, \
    Interface_without_registration
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr, OP_ASSIGN
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axis import AxiStream
from hwt.hdl.statements.switchContainer import SwitchContainer
from hwtLib.amba.axis_comp.strformat import HdlType_to_Interface_with_AxiStream
from hwt.hdl.types.bits import Bits
from hwt.synthesizer.interfaceLevel.interfaceUtils.utils import walkPhysInterfaces
from hwt.synthesizer.interface import Interface
from hwt.hdl.types.struct import HStruct
from hwt.synthesizer.vectorUtils import iterBits, BitWalker
from enum import Enum


class HlsStreamProcStm(HdlStatement):

    def __init__(self, parent: "HlsStreamProc"):
        HdlStatement.__init__(self)
        self.parent = parent

    @internal
    def _get_rtl_context(self) -> 'RtlNetlist':
        return self.parent.parent._ctx

    def __repr__(self):
        from hwtHls.hlsStreamProc.debugCodeSerializer import HlsStreamProcDebugCodeSerializer
        name_scope = NameScope(None, "debug", False, debug=True)
        to_hdl = HlsStreamProcDebugCodeSerializer.TO_HDL_AST(name_scope)
        to_hdl.debug = True
        hdl = to_hdl.as_hdl(self)
        buff = StringIO()
        # import sys
        # buff = sys.stdout
        ser = HlsStreamProcDebugCodeSerializer.TO_HDL(buff)
        ser.visit_iHdlObj(hdl)
        return buff.getvalue()


class HlsStreamProcCodeBlock(HlsStreamProcStm, HdlStmCodeBlockContainer):

    def __init__(self, parent: "HlsStreamProc"):
        HdlStmCodeBlockContainer.__init__(self)
        HlsStreamProcStm.__init__(self, parent)
        self.parent = parent

    def __repr__(self):
        return HlsStreamProcStm.__repr__(self)


ANY_HLS_STREAM_INTF_TYPE = Union[AxiStream, Handshaked, VldSynced,
                                 HsStructIntf, RtlSignal, Signal,
                                 UnionSink, UnionSource]


class IN_STREAM_POS(Enum):
    """
    Enum for position of chunk of data inside of stream.
    """
    BEGIN = "BEGIN"  # if first but not last data chunk in frame
    BEGIN_END = "BEGIN_END"  # is first and last data chunk in frame
    BODY = "BODY"  # is not first not last data chunk in frame
    END_OR_BODY = "END_OR_BODY"  # could be at last data chunk in frame
    END = "END"  # is last data chunk in frame

    def isBegin(self):
        return self in (IN_STREAM_POS.BEGIN, IN_STREAM_POS.BEGIN_END)

    def isEnd(self):
        return self in (IN_STREAM_POS.BEGIN_END, IN_STREAM_POS.END)


class HlsStreamProcRead(HdlStatement, SignalOps, InterfaceBase, SsaInstr):
    """
    Container of informations about read from some stream
    """

    def __init__(self,
                 parent: "HlsStreamProc",
                 src: ANY_HLS_STREAM_INTF_TYPE,
                 type_or_size: Union[HdlType, RtlSignal, int],
                 inStreamPos=IN_STREAM_POS.BODY):
        super(HlsStreamProcRead, self).__init__()
        self._isAccessible = True
        assert isinstance(inStreamPos, IN_STREAM_POS), inStreamPos
        self._inStreamPos = inStreamPos
        self._parent = parent
        self._src = src
        self.block: Optional[SsaBasicBlock] = None

        if isinstance(src, (Handshaked, HsStructIntf)):
            assert (type_or_size is NOT_SPECIFIED or
                    type_or_size == src.data._dtype), (
                        "The handshaked interfaces do not undergo any parsing thus only their native type is supportted")
            type_or_size = src.data._dtype

        elif isinstance(src, (Signal, RtlSignal)):
            assert (type_or_size is NOT_SPECIFIED or
                    type_or_size == src._dtype), (
                        "The signal interfaces do not undergo any parsing thus only their native type is supportted",
                        type_or_size, src._dtype)
            type_or_size = src._dtype

        assert isinstance(type_or_size, HdlType), type_or_size
            
        intfName = getSignalName(src)
        var = parent.var
        sig = var(f"{intfName:s}_read", type_or_size)
        if isinstance(sig, Interface):
            sig_flat = var(f"{intfName:s}_read", Bits(type_or_size.bit_length()))
            # use flat signal and make type member fields out of slices of that signal
            bw = BitWalker(sig_flat)
            for i in walkPhysInterfaces(sig):
                i._sig = bw.get(i._sig._dtype.bit_length())

            sig_flat.drivers.append(self)
            sig_flat.origin = self
    
        else:
            sig_flat = sig
            sig.drivers.append(self)
            sig.origin = self

        self._sig = sig_flat
        self._valid = var(f"{intfName:s}_read_valid", BIT)
        self._GEN_NAME_PREFIX = intfName
        SsaInstr.__init__(self, parent.ssaCtx, type_or_size, OP_ASSIGN, (),
                          origin=sig)
        # self._out: Optional[ANY_HLS_STREAM_INTF_TYPE] = None

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
        # [todo] this put this object in temprorary inconsistent state,
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


class HlsStreamProcIf(HlsStreamProcStm, IfContainer):

    def __init__(self, parent: "HlsStreamProc", cond: Union[RtlSignal, HValue], body: List[HdlStatement]):
        HlsStreamProcStm.__init__(self, parent)
        assert isinstance(cond, (RtlSignal, HValue)), cond
        self.cond = cond
        self.ifTrue = body
        self.elIfs = []
        self.ifFalse = None

    def Elif(self, cond, *statements):
        self.elIfs.append((cond, statements))
        return self

    def Else(self, *statements):
        if self.ifFalse is not None:
            raise HwtSyntaxError(
                "Else on this if-then-else statement was already used")

        self.ifFalse = statements
        return self


class  HlsStreamProcSwitch(HlsStreamProcStm, SwitchContainer):

    def __init__(self, parent: "HlsStreamProc", switchOn: Union[RtlSignal, HValue]):
        HlsStreamProcStm.__init__(self, parent)
        assert isinstance(switchOn, (RtlSignal, HValue)), switchOn
        self.switchOn = switchOn
        self.cases = []
        self.default = None

        self._case_value_index = {}

    def Case(self, val, *statements):
        self.cases.append((val, statements))
        return self

    def Default(self, *statements):
        if self.default is not None:
            raise HwtSyntaxError(
                "Default on this switch-case statement was already used")

        self.default = statements
        return self


class HlsStreamProcFor(HlsStreamProcStm):
    """
    The for loop statement.
    """

    def __init__(self, parent: "HlsStreamProc",
                 init: List[HdlStatement],
                 cond: Union[RtlSignal, HValue],
                 step: List[HdlStatement],
                 body: List[HdlStatement]):
        super(HlsStreamProcFor, self).__init__(parent)
        assert isinstance(cond, (RtlSignal, HValue)), cond
        self.init = init
        self.cond = cond
        self.step = step
        self.body = body

    def __repr__(self):
        return f"<{self.__class__.__name__}({self.init}; {self.cond}; {self.step}): {self.body}>"


class HlsStreamProcWhile(HlsStreamProcStm):
    """
    The while loop statement.
    """

    def __init__(self, parent: "HlsStreamProc",
                 cond: Union[RtlSignal, HValue],
                 body: List[HdlStatement]):
        super(HlsStreamProcWhile, self).__init__(parent)
        assert isinstance(cond, (RtlSignal, HValue)), cond
        self.cond = cond
        self.body = body

    def __repr__(self):
        return f"<{self.__class__.__name__}({self.cond}): {self.body}>"


class HlsStreamProcBreak(HlsStreamProcStm):
    """
    The loop control statement "break".
    """

    def __init__(self, parent: "HlsStreamProc"):
        super(HlsStreamProcBreak, self).__init__(parent)

    def __repr__(self):
        return f"<{self.__class__.__name__}>"


class HlsStreamProcContinue(HlsStreamProcStm):
    """
    The loop control statement "continue".
    """

    def __init__(self, parent: "HlsStreamProc"):
        super(HlsStreamProcBreak, self).__init__(parent)

    def __repr__(self):
        return f"<{self.__class__.__name__}>"

