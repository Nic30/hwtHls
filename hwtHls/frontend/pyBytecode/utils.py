from itertools import islice
from typing import List, Tuple, Union

from hwt.hdl.value import HValue
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue
from hwtHls.frontend.pyBytecode.loopMeta import BranchTargetPlaceholder


def isLastJumpFromBlock(jumpsFromLoopBody: List[Tuple[Union[None, SsaValue, HValue], SsaBasicBlock, int]],
                        srcBlock: SsaBasicBlock, i: int):
    return not any(j.srcBlock is srcBlock for j in islice(jumpsFromLoopBody, i + 1, None))


def blockHasBranchPlaceholder(curBlock: SsaBasicBlock):
    """
    :note: BranchTargetPlaceholder is added for loop exits
    """
    for target in curBlock.successors.targets:
        if isinstance(target, BranchTargetPlaceholder):
            return True
    return False
