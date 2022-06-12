from io import StringIO
from typing import Union, List

from hdlConvertorAst.translate.common.name_scope import NameScope
from hwt.doc_markers import internal
from hwt.hdl.statements.codeBlockContainer import HdlStmCodeBlockContainer
from hwt.hdl.statements.ifContainter import IfContainer
from hwt.hdl.statements.statement import HdlStatement, HwtSyntaxError
from hwt.hdl.statements.switchContainer import SwitchContainer
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal


class HlsStm(HdlStatement):

    def __init__(self, parent: "HlsScope"):
        HdlStatement.__init__(self)
        self.parent = parent

    @internal
    def _get_rtl_context(self) -> 'RtlNetlist':
        return self.parent.parent._ctx

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


class HlsStmCodeBlock(HlsStm, HdlStmCodeBlockContainer):

    def __init__(self, parent: "HlsScope"):
        HdlStmCodeBlockContainer.__init__(self)
        HlsStm.__init__(self, parent)
        self.parent = parent

    def __repr__(self):
        return HlsStm.__repr__(self)


class HlsStmIf(HlsStm, IfContainer):

    def __init__(self, parent: "HlsScope", cond: Union[RtlSignal, HValue], body: List[HdlStatement]):
        HlsStm.__init__(self, parent)
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


class  HlsStmSwitch(HlsStm, SwitchContainer):

    def __init__(self, parent: "HlsScope", switchOn: Union[RtlSignal, HValue]):
        HlsStm.__init__(self, parent)
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


class HlsStmFor(HlsStm):
    """
    The for loop statement.
    """

    def __init__(self, parent: "HlsScope",
                 init: List[HdlStatement],
                 cond: Union[RtlSignal, HValue],
                 step: List[HdlStatement],
                 body: List[HdlStatement]):
        super(HlsStmFor, self).__init__(parent)
        assert isinstance(cond, (RtlSignal, HValue)), cond
        self.init = init
        self.cond = cond
        self.step = step
        self.body = body

    def __repr__(self):
        return f"<{self.__class__.__name__}({self.init}; {self.cond}; {self.step}): {self.body}>"


class HlsStmWhile(HlsStm):
    """
    The while loop statement.
    """

    def __init__(self, parent: "HlsScope",
                 cond: Union[RtlSignal, HValue],
                 body: List[HdlStatement]):
        super(HlsStmWhile, self).__init__(parent)
        assert isinstance(cond, (RtlSignal, HValue)), cond
        self.cond = cond
        self.body = body

    def __repr__(self):
        return f"<{self.__class__.__name__}({self.cond}): {self.body}>"


class HlsStmBreak(HlsStm):
    """
    The loop control statement "break".
    """

    def __init__(self, parent: "HlsScope"):
        super(HlsStmBreak, self).__init__(parent)

    def __repr__(self):
        return f"<{self.__class__.__name__}>"


class HlsStmContinue(HlsStm):
    """
    The loop control statement "continue".
    """

    def __init__(self, parent: "HlsScope"):
        super(HlsStmContinue, self).__init__(parent)

    def __repr__(self):
        return f"<{self.__class__.__name__}>"

