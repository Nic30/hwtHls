from itertools import chain
from typing import Union, List, Optional, Tuple, Dict, Callable

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.portItem import HdlPortItem
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.codeBlockContainer import HdlStmCodeBlockContainer
from hwt.hdl.statements.ifContainter import IfContainer
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.value import HValue
from hwt.interfaces.std import Signal
from hwt.interfaces.structIntf import StructIntf
from hwt.synthesizer.interfaceLevel.interfaceUtils.utils import packIntf
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.signalUtils.exceptions import SignalDriverErr
from hwtHls.frontend.ast.memorySSAUpdater import MemorySSAUpdater
from hwtHls.frontend.ast.statements import HlsStm, HlsStmWhile, \
    HlsStmCodeBlock, HlsStmIf, HlsStmFor, HlsStmContinue, \
    HlsStmBreak
from hwtHls.frontend.ast.statementsRead import HlsRead, HlsReadAddressed
from hwtHls.frontend.ast.statementsWrite import HlsWrite, HlsWriteAddressed
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.instr import SsaInstr, SsaInstrBranch
from hwtHls.ssa.value import SsaValue
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwt.synthesizer.interface import Interface
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.llvm.llvmIr import Register, LoadInst, StoreInst
from hwtHls.ssa.exprBuilder import SsaExprBuilder
AnyStm = Union[HdlAssignmentContainer, HlsStm]


class SsaInstrBranchUnreachable(SsaInstrBranch):

    def addTarget(self, cond:Optional[SsaValue], target:"SsaBasicBlock"):
        pass


class SsaBasicBlockUnreachable(SsaBasicBlock):

    def __init__(self, ctx: SsaContext, label:str):
        SsaBasicBlock.__init__(self, ctx, label)
        self.successors = SsaInstrBranchUnreachable(self)


NetlistReadNodeConsructorT = Callable[[
        "HlsNetlistAnalysisPassMirToNetlist",
        "MachineBasicBlockSyncContainer",
        LoadInst,
        Interface,  # srcIo
        Union[int, HlsNetNodeOutAny],  # index
        HlsNetNodeOutAny,  # cond
        Register,  # instrDstReg
    ], None]
NetlistWriteNodeConsructorT = Callable[[
    "HlsNetlistAnalysisPassMirToNetlist",
    "MachineBasicBlockSyncContainer",
    StoreInst,
    HlsNetNodeOutAny,  # srcVal
    Interface,  # dstIo
    Union[int, HlsNetNodeOutAny],  # index
    HlsNetNodeOutAny,  # cond
], None]
NetlistIoConstructorDictT = Dict[Interface, Tuple[Optional[NetlistReadNodeConsructorT], Optional[NetlistWriteNodeConsructorT]]]


class HlsAstToSsa():
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
    :ivar ioNodeConstructors: a 
    """

    def __init__(self, ssaCtx: SsaContext, startBlockName:str, original_code_for_debug: Optional[HlsStmCodeBlock]):
        self.ssaCtx = ssaCtx
        self.label = startBlockName
        self.start = SsaBasicBlock(ssaCtx, startBlockName)
        self.m_ssa_u = MemorySSAUpdater(self.visit_expr)
        # all predecessors known (because this is an entry point)
        self._continue_target: List[SsaBasicBlock] = []
        self._break_target: List[SsaBasicBlock] = []
        self.original_code_for_debug = original_code_for_debug
        self._loop_stack: List[Tuple[HlsStmWhile, SsaBasicBlock, List[SsaBasicBlock]]] = []
        self.ioNodeConstructors: Optional[NetlistIoConstructorDictT] = None
        self.ssaBuilder = SsaExprBuilder(self.start, None)

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
            elif isinstance(o, HlsWrite):
                block = self.visit_Write(block, o)
            elif isinstance(o, HlsStmWhile):
                block = self.visit_While(block, o)
            elif isinstance(o, HlsStmFor):
                block = self.visit_For(block, o)
            elif isinstance(o, (HlsStmIf, IfContainer)):
                block = self.visit_If(block, o)
            elif isinstance(o, HlsRead):
                block, _ = self.visit_expr(block, o)
            elif isinstance(o, HlsStmBreak):
                block = self.visit_Break(block, o)
            elif isinstance(o, HlsStmContinue):
                block = self.visit_Continue(block, o)
            else:
                raise NotImplementedError(o)

        return block

    def visit_expr(self, block: SsaBasicBlock, var: Union[RtlSignal, HValue]) -> Tuple[SsaBasicBlock, Union[SsaValue, HValue]]:
        if isinstance(var, Signal):
            var = var._sig
        builder = self.ssaBuilder
        if builder.block is not block:
            builder.setInsertPoint(block, None)

        if isinstance(var, RtlSignal):
            try:
                op = var.singleDriver()
            except SignalDriverErr:
                op = None

            if op is None or not isinstance(op, Operator):
                if isinstance(op, HdlPortItem):
                    raise NotImplementedError(op)
                
                elif isinstance(op, HlsRead):
                    if op.block is None:
                        if isinstance(op, HlsReadAddressed):
                            assert len(op.operands) == 1, (op, op.operands)
                            block, index = self.visit_expr(block, op.operands[0])
                            op.operands = (index,)
                        # read first used there else already visited
                        builder._insertInstr(op)
                        # HlsRead is a SsaValue and thus represents "variable"
                        self.m_ssa_u.writeVariable(var, (), builder.block, op)

                    return block, op

                elif isinstance(op, (HlsStmBreak, HlsStmContinue)):
                    raise NotImplementedError()

                else:
                    return block, self.m_ssa_u.readVariable(var, block)

            if op.operator in (AllOps.BitsAsVec, AllOps.BitsAsUnsigned) and not var._dtype.signed:
                # skip implicit conversions
                assert len(op.operands) == 1
                return self.visit_expr(block, op.operands[0])

            if (op.operator == AllOps.INDEX
                and var._dtype.bit_length() == 1
                and len(op.operands) == 2
                and isinstance(op.operands[1], BitsVal)
                and int(op.operands[1]) == 0
                and op.operands[0]._dtype.bit_length() == 1):
                # skip indexing on 1b vectors/ 1b bits
                return self.visit_expr(block, op.operands[0])

            ops = []
            for o in op.operands:
                block, _o = self.visit_expr(block, o)
                ops.append(_o)
            if op.operator == AllOps.CONCAT:
                ops = list(reversed(ops))

            sig = var
            var = SsaInstr(builder.block.ctx, var._dtype, op.operator, ops, origin=var)
            builder._insertInstr(var)
            self.m_ssa_u.writeVariable(sig, (), builder.block, var)
            # we know for sure that this in in this block that is why we do not need to use readVariable
            return block, var

        elif isinstance(var, HValue):
            return block, var

        else:
            if isinstance(var, HlsRead):
                if var.block is None:
                    if isinstance(var, HlsReadAddressed):
                        block, var._index = self.visit_expr(block, var._index)
                        # var.operands = (i, )
                    builder._insertInstr(var)
                    # HlsRead is a SsaValue and thus represents "variable"
                    self.m_ssa_u.writeVariable(var._sig, (), builder.block, var)

                var = var._sig

            elif isinstance(var, StructIntf):
                var = packIntf(var)
                return self.visit_expr(block, var)

            return builder.block, self.m_ssa_u.readVariable(var, builder.block)

    def visit_For(self, block: SsaBasicBlock, o: HlsStmFor) -> SsaBasicBlock:
        block = self.visit_CodeBlock_list(block, o.init)
        return self.visit_While(block, HlsStmWhile(o.parent, o.cond, o.body + o.step))

    def visit_While(self, block: SsaBasicBlock, o: HlsStmWhile) -> SsaBasicBlock:
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
    
    def visit_Continue(self, block: SsaBasicBlock, o: HlsStmContinue) -> SsaBasicBlock:
        assert self._loop_stack, (o, "Must be in loop")
        _, loop_entry, _ = self._loop_stack[-1]
        block.successors.addTarget(None, loop_entry)

        return self._make_Unreachable(block.ctx, f"{block.label:s}_conUnreachable")

    def _make_Unreachable(self, ctx:SsaContext, label:str):
        end_block = SsaBasicBlockUnreachable(ctx, label)

        self._onAllPredecsKnown(end_block)
        return end_block
        
    def visit_Break(self, block: SsaBasicBlock, o: HlsStmContinue) -> SsaBasicBlock:
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

    def visit_If(self, block: SsaBasicBlock, o: HlsStmIf) -> SsaBasicBlock:
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

        return block

    def visit_Write(self, block: SsaBasicBlock, o: HlsWrite) -> SsaBasicBlock:
        if isinstance(o, HlsWriteAddressed):
            block, index = self.visit_expr(block, o.getIndex())
        else:
            index = None
        block, src = self.visit_expr(block, o.getSrc())
        builder = self.ssaBuilder
        builder._insertInstr(o)
        builder.block.origins.append(o)

        if index is not None:
            o.operands = (src, index)
        else:
            o.operands = (src,)
        for op in o.operands:
            if isinstance(op, SsaValue):
                op.users.append(o)

        return block

    def finalize(self):
        sealedBlocks = self.m_ssa_u.sealedBlocks
        for b in chain((self.start,), sealedBlocks):
            for p in b.predecessors:
                assert p in sealedBlocks, (p, "was not sealed")
            for s in b.successors.iterBlocks():
                assert s in sealedBlocks, (s, "was not sealed")

        assert not self.m_ssa_u.incompletePhis, self.m_ssa_u.incompletePhis

    def collectIo(self) -> Dict[Interface, Tuple[List[HlsRead], List[HlsWrite]]]:
        io: Dict[Interface, Tuple[List[HlsRead], List[HlsWrite]]] = {}
        for block in collect_all_blocks(self.start, set()):
            for instr in block.body:
                if isinstance(instr, HlsRead):
                    instr: HlsRead
                    cur = io.get(instr._src, None)
                    if cur is None:
                        io[instr._src] = ([instr], [])
                    else:
                        otherReads, _ = cur
                        otherReads.append(instr)

                elif isinstance(instr, HlsWrite):
                    instr: HlsWrite
                    cur = io.get(instr.dst, None)
                    if cur is None:
                        io[instr.dst] = ([], [instr])
                    else:
                        _, otherWrites = cur
                        otherWrites.append(instr)
        return io

    def resolveIoNetlistConstructors(self, io: Dict[Interface, Tuple[List[HlsRead], List[HlsWrite]]]):
        ioNodeConstructors = self.ioNodeConstructors = {}
        for i, (reads, writes) in io.items():
            ioNodeConstructors[i] = (reads[0]._translateMirToNetlist if reads else None,
                                     writes[0]._translateMirToNetlist if writes else None)
