from dis import Instruction
from networkx.classes.digraph import DiGraph
from typing import Tuple, Dict

from hwtHls.frontend.pyBytecode.instructions import \
    FOR_ITER, RAISE_VARARGS, RERAISE, \
    RETURN_VALUE, JUMPS_NON_OPTIONAL, JUMPS_CONDITIONAL_ANY, EXTENDED_ARG


def extractBytecodeBlocks(instructions: Tuple[Instruction, ...]) -> Tuple[Dict[int, Tuple[Instruction, ...]], DiGraph]:
    """
    This function extract CFG graph from instruction list.
    """
    cfg = DiGraph()

    curBlock = []
    blocks: Dict[int, Tuple[Instruction, ...]] = {}
    blocks[0] = curBlock
    lastWasConditionalJump = False
    lastWasNonOptionalJump = False
    skipNonJumpTargets = False
    for instr in instructions:
        instr: Instruction
        if skipNonJumpTargets:
            if not instr.is_jump_target:
                continue  # skip unreachable code
            else:
                skipNonJumpTargets = False

        isNotEntryPointAndJumpTarget = instr.is_jump_target and instr.offset != 0
        if isNotEntryPointAndJumpTarget or lastWasNonOptionalJump or lastWasConditionalJump:
            # create a new block
            if lastWasConditionalJump or (instr.is_jump_target and isNotEntryPointAndJumpTarget and not lastWasNonOptionalJump):
                src = curBlock[0].offset
                dst = instr.offset
                cfg.add_edge(src, dst)

            curBlock = [instr, ]
            blocks[instr.offset] = curBlock
            lastWasNonOptionalJump = False
            lastWasConditionalJump = False

        else:
            # append to existing block
            curBlock.append(instr)
        
        # [todo] skip jump instruction’s CACHE entries when applying jump offset
        opc = instr.opcode
        if opc in (RETURN_VALUE, RERAISE, RAISE_VARARGS):
            lastWasNonOptionalJump = True
            skipNonJumpTargets = True

        elif opc in JUMPS_NON_OPTIONAL:
            src = curBlock[0].offset
            dst = instr.argval
            cfg.add_edge(src, dst)
            lastWasNonOptionalJump = True
            skipNonJumpTargets = True

        elif opc in JUMPS_CONDITIONAL_ANY:
            if instr.opcode == FOR_ITER:
                # :note: FOR_ITER is always jump target and conditional jump so this block always contains just this instr.
                assert len(curBlock) == 1 or (
                    len(curBlock) == 2 and curBlock[0].opcode == EXTENDED_ARG), curBlock

            src = curBlock[0].offset
            cfg.add_edge(src, instr.argval)
            # cfg.add_edge(src, instr.offset + 2)
            lastWasConditionalJump = True

    if not cfg.nodes:
        # case with a single block without any jump
        cfg.add_node(0)

    return blocks, cfg
