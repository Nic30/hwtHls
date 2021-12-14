from typing import Set

from hwtHls.ssa.basicBlock import SsaBasicBlock


def collect_all_blocks(start: SsaBasicBlock, seen_blocks: Set[SsaBasicBlock]):
    seen_blocks.add(start)
    yield start
    for suc in start.successors.iter_blocks():
        if suc not in seen_blocks:
            yield from collect_all_blocks(suc, seen_blocks)
