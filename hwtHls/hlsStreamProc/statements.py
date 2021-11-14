from io import StringIO
from typing import Union, Optional, List

from hdlConvertorAst.translate.common.name_scope import NameScope
from hwt.doc_markers import internal
from hwt.hdl.statements.codeBlockContainer import HdlStmCodeBlockContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.defs import BOOL
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.typeCast import toHVal
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.signalOps import SignalOps
from hwt.interfaces.std import Handshaked, Signal
from hwt.interfaces.structIntf import StructIntf
from hwt.interfaces.unionIntf import UnionSink, UnionSource
from hwt.pyUtils.arrayQuery import flatten
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.hlsStreamProc.ssa.phi import SsaPhi
from hwtLib.amba.axis import AxiStream


class HlsStreamProcStm(HdlStatement):

    def __init__(self, parent: "HlsStreamProc"):
        super(HlsStreamProcStm, self).__init__()
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


class HlsStreamProcRead(HdlStatement, SignalOps, InterfaceBase):
    """
    Container of informations about read from some stream
    """

    def __init__(self,
                 parent: "HlsStreamProc", src: Union[AxiStream, Handshaked, Signal, RtlSignal],
                 type_or_size: Union[HdlType, RtlSignal, int]):
        super(HlsStreamProcRead, self).__init__()
        self._isAccessible = True
        self._parent = parent
        self._src = src

        ctx = parent.ctx
        if isinstance(src, (Handshaked, HsStructIntf)):
            assert (type_or_size is NOT_SPECIFIED or
                    type_or_size is src.data._dtype), "The handshaked interfaces do not undergo any parsing thus only their native type is supportted"
            type_or_size = src.data._dtype
        elif isinstance(src, (Signal, RtlSignal)):
            assert (type_or_size is NOT_SPECIFIED or
                    type_or_size is src._dtype), "The signal interfaces do not undergo any parsing thus only their native type is supportted"
            type_or_size = src._dtype

        assert isinstance(type_or_size, HdlType), type_or_size
        self._sig = ctx.sig(f"{getSignalName(src):s}_read", type_or_size)
        self._sig.drivers.append(self)
        self._sig.origin = self

        self._dtype = type_or_size
        self._out: Optional[Handshaked] = None

        if isinstance(self._sig, (StructIntf, UnionSink, UnionSource)):
            sig = self._sig
            # copy all members on this object
            for field_path, field_intf in sig._fieldsToInterfaces.items():
                if len(field_path) == 1:
                    n = field_path[0]
                    setattr(self, n, field_intf)

    @property
    def _name(self):
        return self._src._name

    @internal
    def _get_rtl_context(self) -> 'RtlNetlist':
        return self._parent.ctx

    def __repr__(self):
        return f"<{self.__class__.__name__} {getSignalName(self._src):s}, {self._dtype}>"


class HlsStreamProcWrite(HlsStreamProcStm):
    """
    Container of informations about write in some stream
    """

    def __init__(self,
                 parent: "HlsStreamProc",
                 src:Union[HlsStreamProcRead, Handshaked, AxiStream, bytes, HValue],
                 dst: Union[AxiStream, Handshaked]):
        super(HlsStreamProcWrite, self).__init__(parent)
        self.parent = parent
        if isinstance(src, int):
            dtype = getattr(dst, "_dtype", None)
            if dtype is None:
                dtype = dst.data._dtype
            src = dtype.from_py(src)
        self.src = src
        # store original source for debugging
        self._orig_src = src
        self.dst = dst

    def iterInputs(self):
        yield self.src

    def replaceInput(self, orig_expr: SsaPhi, new_expr: SsaPhi):
        src = self.src
        assert orig_expr is src
        orig_expr.users.remove(self)
        self.src = new_expr
        new_expr.users.append(self)

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.src}->{getSignalName(self.dst)}>"

# class HlsStreamProcJump(HlsStreamProcStm):
#
#    def __init__(self, parent: "HlsStreamProc",
#                 cond: RtlSignal,
#                 if_true:Optional[HlsStreamProcStm],
#                 if_false:Optional[HlsStreamProcStm]):
#        super(HlsStreamProcJump, self).__init__(parent)
#        self.cond = cond
#        self.if_true = if_true
#        self.if_false = if_false
#
#    def __repr__(self):
#        return f"<{self.__class__.__name__} 0x{id(self):x} {self.cond}, {self.if_true}, {self.if_false}>"

# class HlsStreamProcAwait(HlsStreamProcStm):
#    """
#    Await until the read/write is finished
#    """
#
#    def __init__(self, parent: "HlsStreamProc", op: Union[HlsStreamProcRead, HlsStreamProcWrite]):
#        super(HlsStreamProcAwait, self).__init__(parent)
#        assert isinstance(op, (HlsStreamProcRead, HlsStreamProcWrite)), op
#        self.op = op
#
#    def __repr__(self):
#        return f"<{self.__class__.__name__} {self.op}>"

# class HlsStreamProcDelete(HlsStreamProcStm):
#    """
#    Mark result of read transaction as not needed anymore and deallocate it and
#     allow for next data load in transaction storage if there is any.
#    """
#
#    def __init__(self, parent: "HlsStreamProc", op: HlsStreamProcRead):
#        super(HlsStreamProcDelete, self).__init__(parent)
#        self.op = op
#
#    def __repr__(self):
#        return f"<{self.__class__.__name__} {self.op}>"
#


class HlsStreamProcWhile(HlsStreamProcStm):
    """
    * All reads are converted to a reads of a streams of original type
    * All parsers/deparsers are restarte on while exit
    """

    def __init__(self, parent: "HlsStreamProc", cond: Union[RtlSignal, bool], body: List[HdlStatement]):
        super(HlsStreamProcWhile, self).__init__(parent)
        assert isinstance(cond, (RtlSignal, bool)), cond
        self.cond = toHVal(cond, BOOL)
        self.body = list(flatten(body))

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.cond}: {self.body}>"


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

# class HlsStreamProcExclusiveGroups(list):
#    pass
