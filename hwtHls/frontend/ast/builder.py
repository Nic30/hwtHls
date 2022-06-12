from collections import deque
from typing import Union, Tuple

from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.types.defs import BOOL
from hwt.hdl.types.typeCast import toHVal
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.astToSsa import AnyStm
from hwtHls.frontend.ast.statements import HlsStm, HlsStmWhile, HlsStmFor, \
    HlsStmBreak, HlsStmContinue, HlsStmIf, HlsStmSwitch


class HlsAstBuilder():
    """
    read/write/var and others are shared with HlsScope and are not duplicated on this builder.
    """

    def __init__(self, parent: "HlsScope"):
        self.parent = parent
    
    def While(self, cond: Union[RtlSignal, bool], *body: AnyStm):
        """
        Create a while statement in thread.
        """
        return HlsStmWhile(self, toHVal(cond, BOOL), list(body))

    def For(self,
            init: Union[AnyStm, Tuple[AnyStm, ...]],
            cond: Union[Tuple, RtlSignal],
            step: Union[AnyStm, Tuple[AnyStm, ...]],
            *body: AnyStm):
        if not isinstance(init, (tuple, list, deque)):
            assert isinstance(init, (HdlAssignmentContainer, HlsStm)), init
            init = [init, ]
        cond = toHVal(cond, BOOL)
        if not isinstance(step, (tuple, list, deque)):
            assert isinstance(step, (HdlAssignmentContainer, HlsStm)), step
            step = [step, ]

        return HlsStmFor(self, init, cond, step, list(body))

    def Break(self):
        return HlsStmBreak(self)

    def Continue(self):
        return HlsStmContinue(self)

    def If(self, cond: Union[RtlSignal, bool], *body: AnyStm):
        return HlsStmIf(self, toHVal(cond, BOOL), list(body))

    def Switch(self, switchOn):
        return HlsStmSwitch(self, toHVal(switchOn))
