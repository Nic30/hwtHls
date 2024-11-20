from itertools import islice
from typing import List, Tuple, Union

from hwt.hdl.const import HConst
from hwtHls.llvm.llvmIr import Value, BasicBlock


def isLastJumpFromBlock(jumpsFromLoopBody: List[Tuple[Union[None, Value, HConst], BasicBlock, int]],
                        srcBlock: BasicBlock, i: int):
    return not any(j.srcBlock == srcBlock for j in islice(jumpsFromLoopBody, i + 1, None))

