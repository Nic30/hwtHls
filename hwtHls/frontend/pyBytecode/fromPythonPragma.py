from hwtHls.frontend.pyBytecode.loopMeta import PyBytecodeLoopInfo
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import ConditionBlockTuple


def _applyLoopPragma(headerBlock: SsaBasicBlock, loopInfo:PyBytecodeLoopInfo):
    """
    In LLVM loop metadata are specified on jumps from latch blocks to a loop header.
    :see: Loop::setLoopID, Loop::getLoopID 
    """
    anyJumpToHeaderFound = False
    latchOrExitBlocks = set(j.srcBlock for j in loopInfo.jumpsFromLoopBody)

    for pred in headerBlock.predecessors:
        if pred in latchOrExitBlocks:
            for i, t in enumerate(pred.successors.targets):
                if t.dstBlock is headerBlock:
                    found = True
                    meta = t.meta
                    if meta is None:
                        meta = []
                        pred.successors.targets[i] = ConditionBlockTuple(t.condition, t.dstBlock, meta)

                    meta.extend(loopInfo.pragma)

            assert found, ("Jump from latch block ", pred.label, " to header block ", headerBlock.label,
                           " was from loop was not found", j.srcBlock.successors.targets)
            anyJumpToHeaderFound |= found
