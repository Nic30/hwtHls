from typing import Union, List, Optional, Tuple

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.portItem import HdlPortItem
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.codeBlockContainer import HdlStmCodeBlockContainer
from hwt.hdl.statements.ifContainter import IfContainer
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.signalUtils.exceptions import SignalDriverErr
from hwtHls.hlsStreamProc.statements import HlsStreamProcStm, HlsStreamProcWhile, \
    HlsStreamProcWrite, HlsStreamProcRead, HlsStreamProcCodeBlock, \
    HlsStreamProcIf, HlsStreamProcFor
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.translation.fromAst.memorySSAUpdater import MemorySSAUpdater
from hwtHls.ssa.value import SsaValue

AnyStm = Union[HdlAssignmentContainer, HlsStreamProcStm]


class AstToSsa():
    """
    * Matthias Braun, Sebastian Buchwald, Sebastian Hack, Roland Leißa, Christoph Mallon, and Andreas Zwinkau. 2013.
      Simple and efficient construction of static single assignment form.
      In Proceedings of the 22nd international conference on Compiler Construction (CC'13).
      Springer-Verlag, Berlin, Heidelberg, 102–122. DOI:https://doi.org/10.1007/978-3-642-37051-9_6

      * avoids computation of dominance or iterated DF
      * works directly on AST (avoids CFG)
    :see: https://github.com/lohner/FormalSSA
    :note: new statements do generate a new block if this statement is not a loop the bloc is sealed.
        If statement is loop the first block is sealed once all jumps from loop end are resolved.
        Once the block is sealed the arguments for all phi functions is resolved recursively
        and redundant phis are reduced.

    :see: http://dev.stephendiehl.com/numpile/
    :ivar start: basic block where the program begins
    :ivar m_ssa_u: object which is used to track variable usage a to construct SsaPhi for SSA normal form
    :ivar _continue_target: list of basic blocks where code should jump on continue statement
    :ivar _break_target: list of basic blocks where code should jump on break statement
    """

    def __init__(self, ssaCtx: SsaContext, startBlockName:str, original_code_for_debug: Optional[HlsStreamProcCodeBlock]):
        self.ssaCtx = ssaCtx
        self.start = SsaBasicBlock(ssaCtx, startBlockName)
        self.m_ssa_u = MemorySSAUpdater(self._onBlockReduce, self.visit_expr)
        # all predecesors known (because this is an entry point)
        self._onAllPredecsKnown(self.start)
        self._continue_target: List[SsaBasicBlock] = []
        self._break_target: List[SsaBasicBlock] = []
        self.original_code_for_debug = original_code_for_debug

    def _onBlockReduce(self, block: SsaBasicBlock, replacement: SsaBasicBlock):
        if block is self.start:
            self.start = replacement

    @staticmethod
    def _addNewTargetBb(predecessor: SsaBasicBlock, cond: Optional[RtlSignal], label: str, origin) -> SsaBasicBlock:
        new_block = SsaBasicBlock(predecessor.ctx, label)
        if origin is not None:
            new_block.origins.append(origin)
        predecessor.successors.addTarget(cond, new_block)
        return new_block

    def _onAllPredecsKnown(self, block: SsaBasicBlock):
        self.m_ssa_u.sealBlock(block)

    def visit_top_CodeBlock(self, obj: HdlStmCodeBlockContainer) -> SsaBasicBlock:
        block = self.visit_CodeBlock(self.start, obj)
        self._onAllPredecsKnown(block)
        return block

    def visit_CodeBlock(self, block: SsaBasicBlock, obj: HdlStmCodeBlockContainer) -> SsaBasicBlock:
        return self.visit_CodeBlock_list(block, obj.statements)

    def visit_CodeBlock_list(self, block: SsaBasicBlock, obj: List[AnyStm]) -> SsaBasicBlock:
        for o in obj:
            if isinstance(o, HdlAssignmentContainer):
                block = self.visit_Assignment(block, o)
            elif isinstance(o, HlsStreamProcWrite):
                block = self.visit_Write(block, o)
            elif isinstance(o, HlsStreamProcWhile):
                block = self.visit_While(block, o)
            elif isinstance(o, HlsStreamProcFor):
                block = self.visit_For(block, o)
            elif isinstance(o, (HlsStreamProcIf, IfContainer)):
                block = self.visit_If(block, o)
            elif isinstance(o, HlsStreamProcRead):
                block, _ = self.visit_expr(block, o)
            else:
                raise NotImplementedError(o)

        return block

    def visit_expr(self, block: SsaBasicBlock, var: Union[RtlSignal, HValue]) -> Tuple[SsaBasicBlock, Union[SsaValue, HValue]]:
        if isinstance(var, RtlSignal):
            try:
                op = var.singleDriver()
            except SignalDriverErr:
                op = None

            if op is None or not isinstance(op, Operator):
                if isinstance(op, HdlPortItem):
                    raise NotImplementedError(op)
                elif isinstance(op, HlsStreamProcRead):
                    if op.block is None:
                        block.appendInstruction(op)
                        # HlsStreamProcRead is a SsaValue and thus represents "variable"
                        self.m_ssa_u.writeVariable(var, (), block, op)
                    return block, op
                else:
                    return block, self.m_ssa_u.readVariable(var, block)

            if op.operator in (AllOps.BitsAsVec, AllOps.BitsAsUnsigned) and not var._dtype.signed:
                # skip implicit conversions
                assert len(op.operands) == 1
                return self.visit_expr(block, op.operands[0])

            ops = []
            for o in op.operands:
                block, _o = self.visit_expr(block, o)
                ops.append(_o)

            self.m_ssa_u.writeVariable(var, (), block, tuple(ops))
            var = SsaInstr(block.ctx, var._dtype, op.operator, ops, origin=var)
            block.appendInstruction(var)
            # we know for sure that this in in this block that is why we do not need to use readVariable
            return block, var

        elif isinstance(var, HValue):
            return block, var

        else:
            if isinstance(var, HlsStreamProcRead):
                if var.block is None:
                    block.appendInstruction(var)
                    # HlsStreamProcRead is a SsaValue and thus represents "variable"
                    self.m_ssa_u.writeVariable(var._sig, (), block, var)
                var = var._sig
            return block, self.m_ssa_u.readVariable(var, block)

    def visit_For(self, block: SsaBasicBlock, o: HlsStreamProcFor) -> SsaBasicBlock:
        block = self.visit_CodeBlock_list(block, o.init)
        return self.visit_While(block, HlsStreamProcWhile(o.parent, o.cond, o.body + o.step))

    def visit_While(self, block: SsaBasicBlock, o: HlsStreamProcWhile) -> SsaBasicBlock:
        if isinstance(o.cond, HValue):
            if o.cond:
                # while True
                cond_block = self._addNewTargetBb(block, None, f"{block.label:s}_whC", o)
                body_block = self._addNewTargetBb(cond_block, None, f"{block.label:s}_wh", o)
                self._onAllPredecsKnown(body_block)
                body_block = self.visit_CodeBlock_list(body_block, o.body)
                body_block.successors.addTarget(None, cond_block)

                self._onAllPredecsKnown(cond_block)

                return SsaBasicBlock(block.ctx, f"{block.label:s}_whUnreachable")
            else:
                # while False
                return block
        else:
            #
            cond_block_orig = self._addNewTargetBb(block, None, f"{block.label:s}_whC", o)
            c = o.cond
            if c._dtype.bit_length() > 1:
                c = c != 0
            else:
                c = c._isOn()

            cond_block, c = self.visit_expr(cond_block_orig, c)
            cond_block.origins.append(o)

            body_block = self._addNewTargetBb(cond_block, c, f"{block.label:s}_wh", o)
            self._onAllPredecsKnown(body_block)
            end_block = self._addNewTargetBb(cond_block, None, f"{block.label:s}_whE", o)
            body_block = self.visit_CodeBlock_list(body_block, o.body)
            body_block.successors.addTarget(None, cond_block)

            self._onAllPredecsKnown(cond_block_orig)
            self._onAllPredecsKnown(end_block)

        return end_block

    def visit_If_branch(self, origin: IfContainer, label: str, cond_block: SsaBasicBlock,
                        end_if_block: SsaBasicBlock, cond: Optional[SsaValue], caseStatements: list):
        if caseStatements:
            # new top block for the branch
            block = self._addNewTargetBb(cond_block, cond, label, origin)
            self._onAllPredecsKnown(block)

            # load body of the branch
            block = self.visit_CodeBlock_list(block, caseStatements)

            # add jump from the end of the branch to end of if-then-else
            block.successors.addTarget(None, end_if_block)
            # now nothing can jump on start or end of the branch, end_if_block will be only successor

        else:
            cond_block.successors.addTarget(cond, end_if_block)

    def visit_If(self, block: SsaBasicBlock, o: HlsStreamProcIf) -> SsaBasicBlock:
        cond_block = self._addNewTargetBb(block, None, f"{block.label:s}_IfC", o)
        self._onAllPredecsKnown(cond_block)
        cond_block, cond = self.visit_expr(cond_block, o.cond)

        end_if_block = SsaBasicBlock(self.ssaCtx, f"{block.label:s}_IfE")
        self.visit_If_branch(o, f"{block.label:s}_If", cond_block, end_if_block, cond, o.ifTrue)

        for i, (c, stms) in enumerate(o.elIfs):
            cond_block, cond = self.visit_expr(cond_block, c)
            self.visit_If_branch(o, f"{block.label:s}_Elif{i:d}", cond_block, end_if_block, cond, stms)

        self.visit_If_branch(o, f"{block.label:s}_Else", cond_block, end_if_block, None, o.ifFalse)

        self._onAllPredecsKnown(end_if_block)

        return end_if_block

    def visit_Assignment(self, block: SsaBasicBlock, o: HdlAssignmentContainer) -> SsaBasicBlock:
        block, src = self.visit_expr(block, o.src)
        block.origins.append(o)
        # this may result in:
        # * store instruction
        # * just the registration of the varialbe for the symbol
        #   * only a segment in bit vector can be assigned, this result in the assignment of the concatenation of previous and new value
        self.m_ssa_u.writeVariable(o.dst, o.indexes, block, src)
        # ld = SsaInstr(o.dst, src)
        # block.appendInstruction(ld)
        # if isinstance(src, SsaValue):
        #    src.users.append(ld)

        return block

    def visit_Write(self, block: SsaBasicBlock, o: HlsStreamProcWrite) -> SsaBasicBlock:
        block, src = self.visit_expr(block, o.getSrc())
        o.operands = (src,)
        block.appendInstruction(o)
        block.origins.append(o)

        if isinstance(src, SsaValue):
            src.users.append(o)

        return block

    def finalize(self):
        assert not self.m_ssa_u.incompletePhis, self.m_ssa_u.incompletePhis
