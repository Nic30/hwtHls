from typing import Tuple

from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.llvm.llvmIr import Value, BasicBlock


class HwIterator():
    """
    The base class for iterators which can be translated to hw code.
    """

    def hwInit(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: BasicBlock) -> BasicBlock:
        """
        Construct code for initialization of iterator.
        """
        raise NotImplementedError("Override this method in implementation of this abstract class", self.__class__)

    def hwCondition(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: BasicBlock) -> Tuple[BasicBlock, Value]:
        """
        Construct a "break" condition for an iterator
        """
        raise NotImplementedError("Override this method in implementation of this abstract class", self.__class__)

    def hwIterStepValue(self) -> RtlSignal:
        """
        .. code-block::Python
            # this function would return variable i in this example
            for i in range(10):
                pass

        :return: values returned in iteration step
        """
        raise NotImplementedError("Override this method in implementation of this abstract class", self.__class__)

    def hwStep(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: BasicBlock) -> BasicBlock:
        """
        Construct a code corresponding to sptep of an iterator
        """
        raise NotImplementedError("Override this method in implementation of this abstract class", self.__class__)
