from itertools import islice
from typing import List, Tuple, Union, Optional, Self

from hwt.hdl.const import HConst
from hwtHls.llvm.llvmIr import Value, BasicBlock


def isLastJumpFromBlock(jumpsFromLoopBody: List[Tuple[Union[None, Value, HConst], BasicBlock, int]],
                        srcBlock: BasicBlock, i: int):
    return not any(j.srcBlock == srcBlock for j in islice(jumpsFromLoopBody, i + 1, None))


class ObjectWithHlsStoreOverride():

    def hlsOverrideInitializeStorageCell(self, toSsa:"PyBytecodeToSsa", localVarName: str) -> Self:
        """
        Prepare hls variables to accommodate values of this object
        """
        raise NotImplementedError("override this in your implementation", self.__class__)

    def hlsOverrideStore(self, toSsa: "PyBytecodeToSsa", curBlock:BasicBlock, newValue) -> BasicBlock:
        """
        Called when the data is stored in cell where this object originally was.
        This is intended to allow python containers to handle copy of its contents.
        :attention: the actual object of this type is not replaced
        """
        raise NotImplementedError("override this in your implementation", self.__class__)
