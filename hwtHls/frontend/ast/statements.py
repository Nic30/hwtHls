from hwt.doc_markers import internal
from hwt.hdl.statements.statement import HdlStatement


class HlsStm(HdlStatement):

    def __init__(self, parent: "HlsScope"):
        HdlStatement.__init__(self)
        self.parent = parent

    @internal
    def _get_rtl_context(self) -> 'RtlNetlist':
        return self.parent.parent._rtlCtx

