from io import StringIO

from hdlConvertorAst.translate.common.name_scope import NameScope
from hwt.doc_markers import internal
from hwt.hdl.statements.statement import HdlStatement


class HlsStm(HdlStatement):

    def __init__(self, parent: "HlsScope"):
        HdlStatement.__init__(self)
        self.parent = parent

    @internal
    def _get_rtl_context(self) -> 'RtlNetlist':
        return self.parent.parent._rtlCtx

    def __repr__(self):
        from hwtHls.frontend.ast.debugCodeSerializer import HlsScopeDebugCodeSerializer
        name_scope = NameScope(None, "debug", False, debug=True)
        to_hdl = HlsScopeDebugCodeSerializer.TO_HDL_AST(name_scope)
        to_hdl.debug = True
        hdl = to_hdl.as_hdl(self)
        buff = StringIO()
        # import sys
        # buff = sys.stdout
        ser = HlsScopeDebugCodeSerializer.TO_HDL(buff)
        ser.visit_iHdlObj(hdl)
        return buff.getvalue()

