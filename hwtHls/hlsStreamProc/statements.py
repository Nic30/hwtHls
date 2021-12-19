from io import StringIO
from typing import Union, Optional, List

from hdlConvertorAst.translate.common.name_scope import NameScope
from hwt.doc_markers import internal
from hwt.hdl.statements.codeBlockContainer import HdlStmCodeBlockContainer
from hwt.hdl.statements.statement import HdlStatement, HwtSyntaxError
from hwt.hdl.types.defs import BOOL
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.typeCast import toHVal
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.signalOps import SignalOps
from hwt.interfaces.std import Handshaked, Signal, VldSynced
from hwt.interfaces.structIntf import StructIntf
from hwt.interfaces.unionIntf import UnionSink, UnionSource
from hwt.pyUtils.arrayQuery import flatten
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr, OP_ASSIGN
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axis import AxiStream
from hwt.hdl.statements.ifContainter import IfContainer


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


class HlsStreamProcRead(HdlStatement, SignalOps, InterfaceBase, SsaInstr):
    """
    Container of informations about read from some stream
    """

    def __init__(self,
                 parent: "HlsStreamProc",
                 src: ANY_HLS_STREAM_INTF_TYPE,
                 type_or_size: Union[HdlType, RtlSignal, int]):
        super(HlsStreamProcRead, self).__init__()
        self._isAccessible = True
        self._parent = parent
        self._src = src
        self.block: Optional[SsaBasicBlock] = None

        ctx = parent.ctx
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
        self._sig = ctx.sig(f"{getSignalName(src):s}_read", type_or_size)
        self._sig.drivers.append(self)
        self._sig.origin = self

        SsaInstr.__init__(self, parent.ssaCtx, type_or_size, OP_ASSIGN, (),
                          name=self._sig.name, origin=self._sig)
        # self._out: Optional[ANY_HLS_STREAM_INTF_TYPE] = None

        if isinstance(self._sig, StructIntf):
            sig = self._sig
            # copy all members on this object
            for field_path, field_intf in sig._fieldsToInterfaces.items():
                if len(field_path) == 1:
                    n = field_path[0]
                    setattr(self, n, field_intf)

    @internal
    def _get_rtl_context(self) -> 'RtlNetlist':
        return self._parent.ctx

    def __repr__(self):
        return f"<{self.__class__.__name__} {getSignalName(self._src):s}, {self._dtype}>"


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

