from itertools import chain
from typing import Union, List, Optional, Tuple

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.portItem import HdlPortItem
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.codeBlockContainer import HdlStmCodeBlockContainer
from hwt.hdl.statements.ifContainter import IfContainer
from hwt.hdl.value import HValue
from hwt.interfaces.std import Signal
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.signalUtils.exceptions import SignalDriverErr
from hwtHls.hlsStreamProc.statements import HlsStreamProcStm, HlsStreamProcWhile, \
    HlsStreamProcCodeBlock, HlsStreamProcIf, HlsStreamProcFor, HlsStreamProcContinue, \
    HlsStreamProcBreak
from hwtHls.hlsStreamProc.statementsIo import HlsStreamProcWrite, HlsStreamProcRead
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.instr import SsaInstr, SsaInstrBranch
from hwtHls.ssa.translation.fromAst.memorySSAUpdater import MemorySSAUpdater
from hwtHls.ssa.value import SsaValue


AnyStm = Union[HdlAssignmentContainer, HlsStreamProcStm]


class SsaInstrBranchUnreachable(SsaInstrBranch):

    def addTarget(self, cond:Optional[SsaValue], target:"SsaBasicBlock"):
        pass


class SsaBasicBlockUnreachable(SsaBasicBlock):

    def __init__(self, ctx: SsaContext, label:str):
        SsaBasicBlock.__init__(self, ctx, label)
        self.successors = SsaInstrBranchUnreachable(self)


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
    :ivar _loop_stack: list of loop where the AST visitor actually is to resolve
        the continue/break and loop association. The record is a tuple (loop statement, entry block, list of blocks ending with break).
        The blocks ending with break will have its branch destination assigned after the loop is processed (in loop parsing fn.).
    """

    def __init__(self, ssaCtx: SsaContext, startBlockName:str, original_code_for_debug: Optional[HlsStreamProcCodeBlock]):
        self.ssaCtx = ssaCtx
        self.start = SsaBasicBlock(ssaCtx, startBlockName)
        self.m_ssa_u = MemorySSAUpdater(self._onBlockReduce, self.visit_expr)
        # all predecessors known (because this is an entry point)
        self._continue_target: List[SsaBasicBlock] = []
        self._break_target: List[SsaBasicBlock] = []
        self.original_code_for_debug = original_code_for_debug
        self._loop_stack: List[Tuple[HlsStreamProcWhile, SsaBasicBlock, List[SsaBasicBlock]]] = []

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
        # self._onAllPredecsKnown(block)
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
            elif isinstance(o, HlsStreamProcBreak):
                block = self.visit_Break(block, o)
            elif isinstance(o, HlsStreamProcContinue):
                block = self.visit_Continue(block, o)
            else:
                raise NotImplementedError(o)

        return block

    def visit_expr(self, block: SsaBasicBlock, var: Union[RtlSignal, HValue]) -> Tuple[SsaBasicBlock, Union[SsaValue, HValue]]:
        if isinstance(var, Signal):
            var = var._sig

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
                        # read first used there else already visited
                        block.appendInstruction(op)
                        # HlsStreamProcRead is a SsaValue and thus represents "variable"
                        self.m_ssa_u.writeVariable(var, (), block, op)

                    return block, op

                elif isinstance(op, (HlsStreamProcBreak, HlsStreamProcContinue)):
                    raise NotImplementedError()

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
            
            sig = var
            var = SsaInstr(block.ctx, var._dtype, op.operator, ops, origin=var)
            block.appendInstruction(var)
            self.m_ssa_u.writeVariable(sig, (), block, var)
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
                self._loop_stack.append((o, cond_block, []))
                body_block = self._addNewTargetBb(cond_block, None, f"{block.label:s}_wh", o)
                self._onAllPredecsKnown(body_block)
                body_block = self.visit_CodeBlock_list(body_block, o.body)
                body_block.successors.addTarget(None, cond_block)

                self._onAllPredecsKnown(cond_block)
                
                _o, _, breaks = self._loop_stack.pop()
                assert _o is o, (_o, o, "Must be record of this loop")
                if breaks:
                    end_block = SsaBasicBlock(block.ctx, f"{block.label:s}_whEnd")
                    for b in breaks:
                        b: SsaBasicBlock
                        b.successors.addTarget(None, end_block)
                        
                else:
                    end_block = SsaBasicBlockUnreachable(block.ctx, f"{block.label:s}_whUnreachable")

                self._onAllPredecsKnown(end_block)

            else:
                # while False
                end_block = block
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
            self._loop_stack.append((o, cond_block, []))

            body_block = self._addNewTargetBb(cond_block, c, f"{block.label:s}_wh", o)
            self._onAllPredecsKnown(body_block)
            end_block = self._addNewTargetBb(cond_block, None, f"{block.label:s}_whE", o)
            body_block = self.visit_CodeBlock_list(body_block, o.body)
            body_block.successors.addTarget(None, cond_block)

            self._onAllPredecsKnown(cond_block_orig)
            
            _o, _, breaks = self._loop_stack.pop()
            assert _o is o, (_o, o, "Must be record of this loop")
            if breaks:
                for b in breaks:
                    b: SsaBasicBlock
                    b.successors.addTarget(None, end_block)
                    
            self._onAllPredecsKnown(end_block)

        return end_block
    
    def visit_Continue(self, block: SsaBasicBlock, o: HlsStreamProcContinue) -> SsaBasicBlock:
        assert self._loop_stack, (o, "Must be in loop")
        _, loop_entry, _ = self._loop_stack[-1]
        block.successors.addTarget(None, loop_entry)

        return self._make_Unreachable(block.ctx, f"{block.label:s}_conUnreachable")

    def _make_Unreachable(self, ctx:SsaContext, label:str):
        end_block = SsaBasicBlockUnreachable(ctx, label)

        self._onAllPredecsKnown(end_block)
        return end_block
        
    def visit_Break(self, block: SsaBasicBlock, o: HlsStreamProcContinue) -> SsaBasicBlock:
        assert self._loop_stack, (o, "Must be in loop")
        _, _, break_blocks = self._loop_stack[-1]
        break_blocks.append(block)

        return self._make_Unreachable(block.ctx, f"{block.label:s}_breUnreachable")
    
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
        # * just the registration of the variable for the symbol
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
        sealedBlocks = self.m_ssa_u.sealedBlocks
        for b in chain((self.start,), sealedBlocks):
            for p in b.predecessors:
                assert p in sealedBlocks, (p, "was not sealed")
            for s in b.successors.iterBlocks():
                assert s in sealedBlocks, (s, "was not sealed")

        assert not self.m_ssa_u.incompletePhis, self.m_ssa_u.incompletePhis