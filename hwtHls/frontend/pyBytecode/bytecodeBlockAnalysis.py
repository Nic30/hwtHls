from dis import Instruction
from typing import Tuple, Dict

from networkx.classes.digraph import DiGraph

from hwtHls.frontend.pyBytecode.instructions import JUMP_OPS, \
    JUMP_ABSOLUTE, JUMP_FORWARD, JUMP_IF_FALSE_OR_POP, JUMP_IF_TRUE_OR_POP, \
    POP_JUMP_IF_FALSE, POP_JUMP_IF_TRUE, FOR_ITER


def extractBytecodeBlocks(instructions: Tuple[Instruction, ...]):
    cfg = DiGraph()
    curBlock = []
    blocks: Dict[int, Tuple[Instruction, ...]] = {}
    blocks[0] = curBlock
    lastWasJump = False
    skipIfNotJumpTarget = False
    for instr in instructions:
        instr: Instruction
        if skipIfNotJumpTarget:
            if not instr.is_jump_target:
                continue  # unreachable code
            else:
                skipIfNotJumpTarget = False

        if (instr.is_jump_target and instr.offset != 0) or lastWasJump:
            if curBlock[-1].opcode not in JUMP_OPS:
                src = (curBlock[0].offset,)
                dst = (instr.offset,)
                cfg.add_edge(src, dst)

            curBlock = [instr, ]
            blocks[instr.offset] = curBlock
            lastWasJump = False
        else:
            curBlock.append(instr)
            if instr.opcode in JUMP_OPS:
                lastWasJump = True
            else:
                lastWasJump = False

        if instr.opcode in (JUMP_ABSOLUTE, JUMP_FORWARD):
            src = (curBlock[0].offset,)
            dst = (instr.argval,)
            cfg.add_edge(src, dst)
            skipIfNotJumpTarget = True

        elif instr.opcode in (JUMP_IF_FALSE_OR_POP,
                JUMP_IF_TRUE_OR_POP,
                POP_JUMP_IF_FALSE,
                POP_JUMP_IF_TRUE,
                FOR_ITER,):
            src = (curBlock[0].offset,)
            cfg.add_edge(src, (instr.argval,))
            cfg.add_edge(src, (instr.offset + 2,))
            lastWasJump = True

    return blocks, cfg
