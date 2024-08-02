from typing import Tuple

from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue


class HwIterator():
    """
    The base class for iterators which can be translated to hw code.
    """

    def hwInit(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock) -> SsaBasicBlock:
        """
        Construct code for initialization of iterator.
        """
        raise NotImplementedError("Override this method in implementation of this abstract class", self.__class__)

    def hwCondition(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock) -> Tuple[SsaBasicBlock, SsaValue]:
        """
        Construct a "break" condition for an iterator
        """
        raise NotImplementedError("Override this method in implementation of this abstract class", self.__class__)

    def hwIterStepValue(self):
        """
        .. code-block::Python
            # this function would return variable i in this example
            for i in range(10):
                pass

        :return: values returned in iteration step
        """
        raise NotImplementedError("Override this method in implementation of this abstract class", self.__class__)

    def hwStep(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock) -> SsaBasicBlock:
        """
        Construct a code corresponding to sptep of an iterator
        """
        raise NotImplementedError("Override this method in implementation of this abstract class", self.__class__)
