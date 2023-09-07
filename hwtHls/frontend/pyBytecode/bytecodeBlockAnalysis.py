from dis import Instruction
from networkx.classes.digraph import DiGraph
from typing import Tuple, Dict

from hwtHls.frontend.pyBytecode.instructions import \
    FOR_ITER, RAISE_VARARGS, RERAISE, \
    RETURN_VALUE, JUMPS_RELATIVE, JUMPS_CONDITIONAL_ANY 


def extractBytecodeBlocks(instructions: Tuple[Instruction, ...]) -> Tuple[Dict[int, Tuple[Instruction, ...]], DiGraph]:
    """
    This function extract CFG graph from instruction list.
    """
    cfg = DiGraph()
        
    curBlock = []
    blocks: Dict[int, Tuple[Instruction, ...]] = {}
    blocks[0] = curBlock
    lastWasConditionalJump = False
    lastWasAbsoluteJump = False
    skipNonJumpTargets = False
    for instr in instructions:
        instr: Instruction
        if skipNonJumpTargets:
            if not instr.is_jump_target:
                continue  # skip unreachable code
            else:
                skipNonJumpTargets = False
        
        isNotEntryPointAndJumpTarget = instr.is_jump_target and instr.offset != 0
        if isNotEntryPointAndJumpTarget or lastWasAbsoluteJump or lastWasConditionalJump:
            # create a new block
            if lastWasConditionalJump or (instr.is_jump_target and isNotEntryPointAndJumpTarget and not lastWasAbsoluteJump):
                src = curBlock[0].offset
                dst = instr.offset
                cfg.add_edge(src, dst)

            curBlock = [instr, ]
            blocks[instr.offset] = curBlock
            lastWasAbsoluteJump = False
            lastWasConditionalJump = False
            
        else:
            # append to existing block
            curBlock.append(instr)
        
        opc = instr.opcode
        if opc in (RETURN_VALUE, RERAISE, RAISE_VARARGS):
            lastWasAbsoluteJump = True
            skipNonJumpTargets = True

        elif opc in JUMPS_RELATIVE:
            src = curBlock[0].offset
            dst = instr.argval
            cfg.add_edge(src, dst)
            lastWasAbsoluteJump = True
            skipNonJumpTargets = True

        elif opc in JUMPS_CONDITIONAL_ANY:
            if instr.opcode == FOR_ITER:
                # :note: FOR_ITER is always jump target and conditional jump so this block always contains just this instr.
                assert len(curBlock) == 1, curBlock
                
            src = curBlock[0].offset
            cfg.add_edge(src, instr.argval)
            #cfg.add_edge(src, instr.offset + 2)
            lastWasConditionalJump = True

    if not cfg.nodes:
        # case with a single block without any jump
        cfg.add_node(0)

    return blocks, cfg
