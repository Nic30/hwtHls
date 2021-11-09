from typing import Union, List, Optional

from hwt.hdl.operator import Operator
from hwt.hdl.portItem import HdlPortItem
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.codeBlockContainer import HdlStmCodeBlockContainer
from hwt.hdl.statements.ifContainter import IfContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.signalUtils.exceptions import SignalDriverErr
from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock
from hwtHls.hlsStreamProc.ssa.instr import SsaInstr
from hwtHls.hlsStreamProc.ssa.phi import SsaPhi
from hwtHls.hlsStreamProc.ssa.translation.fromAst.memorySSAUpdater import MemorySSAUpdater
from hwtHls.hlsStreamProc.statements import HlsStreamProcStm, HlsStreamProcWhile, \
    HlsStreamProcWrite, HlsStreamProcRead
from hwtHls.tmpVariable import HlsTmpVariable

AnyStm = Union[HdlStatement, HlsStreamProcStm]


class AstToSsa():
    """
    * Matthias Braun, Sebastian Buchwald, Sebastian Hack, Roland Leißa, Christoph Mallon, and Andreas Zwinkau. 2013.
      Simple and efficient construction of static single assignment form.
      In Proceedings of the 22nd international conference on Compiler Construction (CC'13).
      Springer-Verlag, Berlin, Heidelberg, 102–122. DOI:https://doi.org/10.1007/978-3-642-37051-9_6

      • avoids computation of dominance or iterated DF
      • works directly on AST (avoids CFG)
      * :see: https://github.com/lohner/FormalSSA

    :see: http://dev.stephendiehl.com/numpile/
    :ivar start: basic block where the program beggins
    :ivar m_ssa_u: object which is used to track variable usage a to construct SsaPhi for SSA normal form
    :ivar _continue_target: basic block where code should jump on continue statement
    :ivar _continue_target: basic block where code should jump on break statement
    """

    def __init__(self, startBlockName:str="top"):
        self._tmpVarCounter = 0
        self.start = SsaBasicBlock(startBlockName)
        self.m_ssa_u = MemorySSAUpdater(self._onBlockReduce, self._createHlsTmpVariable)
        # all predecesors known (because this is an entry point)
        self._onAllPredecsKnown(self.start)
        self._continue_target: Optional[SsaBasicBlock] = None
        self._break_target: Optional[SsaBasicBlock] = None

    def _createHlsTmpVariable(self, origin: RtlSignal) -> HlsTmpVariable:
        v = HlsTmpVariable(f"v{self._tmpVarCounter}", origin)
        self._tmpVarCounter += 1
        return v

    def _onBlockReduce(self, block: SsaBasicBlock, replacement: SsaBasicBlock):
        if block is self.start:
            self.start = replacement

    @staticmethod
    def _addNewTargetBb(predecessor: SsaBasicBlock, cond: Optional[RtlSignal], label: str, origin) -> SsaBasicBlock:
        new_bb = SsaBasicBlock(label)
        if origin is not None:
            new_bb.origins.append(origin)
        predecessor.successors.addTarget(cond, new_bb)
        return new_bb

    def _onAllPredecsKnown(self, bb: SsaBasicBlock):
        self.m_ssa_u.sealBlock(bb)

    def visit_top_CodeBlock(self, obj: HdlStmCodeBlockContainer) -> SsaBasicBlock:
        bb = self.visit_CodeBlock(self.start, obj)
        self._onAllPredecsKnown(bb)
        return bb

    def visit_CodeBlock(self, bb: SsaBasicBlock, obj: HdlStmCodeBlockContainer) -> SsaBasicBlock:
        return self.visit_CodeBlock_list(bb, obj.statements)

    def visit_CodeBlock_list(self, bb: SsaBasicBlock, obj: List[AnyStm]) -> SsaBasicBlock:
        for o in obj:
            if isinstance(o, HdlAssignmentContainer):
                bb = self.visit_Assignment(bb, o)
            # elif isinstance(o, HlsStreamProcAwait):
            #     bb = self.visit_Await(bb, o)
            elif isinstance(o, HlsStreamProcWrite):
                bb = self.visit_Write(bb, o)
            elif isinstance(o, HlsStreamProcWhile):
                bb = self.visit_While(bb, o)
            elif isinstance(o, IfContainer):
                bb = self.visit_If(bb, o)
            else:
                raise NotImplementedError(o)

        return bb

    def visit_expr(self, bb: SsaBasicBlock, var: Union[RtlSignal, HValue]):
        if isinstance(var, RtlSignal):
            try:
                op = var.singleDriver()
            except SignalDriverErr:
                op = None

            if op is None or not isinstance(op, Operator):
                if isinstance(op, HlsStreamProcRead):
                    return bb, op
                else:
                    if isinstance(op, HdlPortItem):
                        raise NotImplementedError()
                    return bb, self.m_ssa_u.readVariable(var, bb)

            ops = []
            for o in op.operands:
                bb, _o = self.visit_expr(bb, o)
                ops.append(_o)

            i = self.m_ssa_u.writeVariable(var, bb, tuple(ops))
            var = self._createHlsTmpVariable(var)
            var.i = i
            bb.body.append(SsaInstr(var, (op.operator, ops)))
            return bb, var

        else:
            return bb, var

        return bb, var

    def visit_While(self, bb: SsaBasicBlock, o: HlsStreamProcWhile) -> SsaBasicBlock:
        if isinstance(o.cond, HValue):
            if o.cond:
                # while True
                # body_bb = self._addNewTargetBb(bb, None, f"{bb.label:s}_While1Body", o)
                # end_bb = self.visit_CodeBlock_list(body_bb, o.body)
                # end_bb.successors.addTarget(None, body_bb)
                # self._onAllPredecsKnown(body_bb)
                # return SsaBasicBlock(f"{bb.label:s}_While1Unreachable")

                body_bb = self._addNewTargetBb(bb, None, f"{bb.label:s}_wh", o)
                body_bb_begin = body_bb
                body_bb = self.visit_CodeBlock_list(body_bb, o.body)
                body_bb.successors.addTarget(None, body_bb_begin)

                self._onAllPredecsKnown(body_bb)

                return SsaBasicBlock(f"{bb.label:s}_whUnreachable")
            else:
                # while False
                return bb
        else:
            cond_bb = self._addNewTargetBb(bb, None, f"{bb.label:s}_whC", o)
            c = o.cond
            if c._dtype.bit_length() > 1:
                c = c != 0
            else:
                c = c._isOn()

            cond_bb, c = self.visit_expr(cond_bb, c)
            cond_bb.origins.append(o)

            body_bb = self._addNewTargetBb(cond_bb, c, f"{bb.label:s}_wh", o)
            self._onAllPredecsKnown(body_bb)
            end_bb = self._addNewTargetBb(cond_bb, None, f"{bb.label:s}_whE", o)
            body_bb = self.visit_CodeBlock_list(body_bb, o.body)
            body_bb.successors.addTarget(None, cond_bb)

            self._onAllPredecsKnown(cond_bb)

        return end_bb

    def visit_If(self, bb: SsaBasicBlock, o: IfContainer) -> SsaBasicBlock:
        cond_bb, cond = self.visit_expr(bb, o.cond)
        cond_bb.origins.append(o)
        self._onAllPredecsKnown(bb)
        end_if_bb = SsaBasicBlock(f"{bb.label:s}_IfE")

        if o.ifTrue:
            bb = SsaBasicBlock(f"{bb.label:s}_If")
            bb.origins.append(o)
            cond_bb.successors.addTarget(cond, bb)
            self._onAllPredecsKnown(bb)

            self.visit_CodeBlock_list(bb, o.ifTrue)
            bb.successors.addTarget(None, end_if_bb)
        else:
            cond_bb.successors.addTarget(None, end_if_bb)

        for i, (c, stms) in enumerate(o.elIfs):
            bb = SsaBasicBlock(f"{bb.label:s}_Elif{i:d}")
            bb.origins.append(o)
            _cond_bb, c = self.visit_expr(cond_bb, c)
            _cond_bb.successors.addTarget(c, bb)
            self._onAllPredecsKnown(bb)

            self.visit_CodeBlock_list(bb, stms)
            bb.successors.addTarget(None, end_if_bb)

        if o.ifFalse:
            bb = SsaBasicBlock(f"{bb.label:s}_Else")
            bb.origins.append(o)
            cond_bb.successors.addTarget(None, bb)
            self._onAllPredecsKnown(bb)

            self.visit_CodeBlock_list(bb, o.ifFalse)
            bb.successors.addTarget(None, end_if_bb)
        else:
            cond_bb.successors.addTarget(None, end_if_bb)

        self._onAllPredecsKnown(end_if_bb)

        return end_if_bb

    def visit_Assignment(self, bb: SsaBasicBlock, o: HdlAssignmentContainer) -> SsaBasicBlock:
        bb, src = self.visit_expr(bb, o.src)
        bb.origins.append(o)
        self.m_ssa_u.writeVariable(o.dst, bb, src)
        # ld = SsaInstr(o.dst, src)
        # bb.body.append(ld)
        # if isinstance(src, SsaPhi):
        #    src.users.append(ld)

        return bb

    # def visit_Await(self, bb: SsaBasicBlock, o: HlsStreamProcAwait) -> SsaBasicBlock:
    #    bb.body.append(o)
    #    return bb
    #
    def visit_Write(self, bb: SsaBasicBlock, o: HlsStreamProcWrite) -> SsaBasicBlock:
        bb, src = self.visit_expr(bb, o.src)
        o.src = src
        bb.body.append(o)
        bb.origins.append(o)

        if isinstance(src, SsaPhi):
            src.users.append(o)

        return bb

