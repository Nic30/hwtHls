from typing import Set

from hwtHls.ssa.instr import SsaInstr
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite


def ssaTryHoistBeforeInSameBlock(hoistPosition: SsaInstr, toHoist: Set[SsaInstr]):
    assert toHoist
    hoistPositionIndex = None
    nonHoistable = {hoistPosition, }
    block = hoistPosition.block
    hoistingBeforeIo = isinstance(hoistPosition, (HlsRead, HlsWrite))
    for i, instr in enumerate(block.body):
        instr: SsaInstr
        if hoistPositionIndex is not None:
            if hoistingBeforeIo and isinstance(instr, (HlsRead, HlsWrite)):
                if instr in toHoist:
                    return False, hoistPositionIndex
                nonHoistable.add(instr)
                continue

            for inp in instr.iterInputs():
                if inp in nonHoistable:
                    if instr in toHoist:
                        return False, hoistPositionIndex

                    nonHoistable.add(instr)
                    break
        elif instr is hoistPosition:
            hoistPositionIndex = i

    assert hoistPositionIndex is not None, ("If it is None it means that the hoistPosition is not in the block", hoistPosition)
    # cut off hoistPosition and everything after
    modifiedSection = block.body[hoistPositionIndex + 1:]
    del block.body[hoistPositionIndex:]
    # append hoistable in original order
    block.body.extend(instr for instr in modifiedSection if instr not in nonHoistable)
    hoistPositionIndex = len(block.body)
    block.body.append(hoistPosition)
    # append hoistPosition, non-hoistable in original order
    block.body.extend(instr for instr in modifiedSection if instr in nonHoistable)
    return True, hoistPositionIndex
