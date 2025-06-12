from typing import Sequence, Union, Callable, List, Tuple, Optional

from hwt.hObjList import HObjList
from hwt.hdl.const import HConst
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.mainBases import HwIOBase
from hwt.mainBases import RtlSignalBase
from hwt.math import AnyHValue
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.llvm.llvmIr import Value, BasicBlock, IRBuilder, \
    SwitchInst, ConstantInt, APInt, ValueToConstantInt
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class PyObjectRequiresExpandBeforeUse():

    def expandOnUse(self, toSsa: "PyBytecodeToSsa",
                    offsetForLabels: int,
                    frame: PyBytecodeFrame, curBlock: BasicBlock) -> Tuple[BasicBlock, Value]:
        raise NotImplementedError("Implement this method in child class")


class PyObjectHwSubscriptRef(PyObjectRequiresExpandBeforeUse):
    """
    An object which is a reference to an object in python array which is indexed in HW.
    This object must be expanded before used in expression or before it is written to.
    This object is not expanded immediately because when we construct the slice we do not know where it is used and if it only read or write access.
    """

    def __init__(self,
                 instructionOffsetForLabels: Optional[int],
                 sequence: Sequence,
                 index: Union[RtlSignal, Value],
                ):
        self.instructionOffsetForLabels = instructionOffsetForLabels
        self.sequence = sequence
        self.index = index

    @classmethod
    def _getTypeOfHObj(cls, v: Union[HObjList, HConst, RtlSignal, HwIO]):
        if isinstance(v, HObjList):
            return cls._getTypeOfHObj(v[0])[len(v)]
        else:
            return v._dtype

    def expandOnUse(self, toSsa: "PyBytecodeToSsa",
                        offsetForLabels: int,
                        frame: PyBytecodeFrame, curBlock: BasicBlock) -> Tuple[BasicBlock, Value]:
        res = self.tryExpandIndexOnPyObjAsTernary()
        if res is not None:
            return curBlock, res

        res = toSsa.hls.var(f"tmp_seq{offsetForLabels}", self._getTypeOfHObj(self.sequence[0]), arrayPartitionComplete=True)
        sucBlock = self._createSwitchCaseBlocks(
            toSsa, offsetForLabels, curBlock,
            lambda toLlvm, i, v, caseBlock: toLlvm.visit_Assignments(caseBlock, res(v))
        )

        return sucBlock, res

    def tryExpandIndexOnPyObjAsTernary(self) -> Optional[AnyHValue]:
        # try find any type on items
        inferedResultTy = None
        for v in self.sequence:
            inferedResultTy = getattr(v, "_dtype", None)
            if inferedResultTy is not None:
                if isinstance(inferedResultTy, HdlType):
                    break
                else:
                    inferedResultTy = None

        if inferedResultTy is not None:
            muxTy = inferedResultTy if inferedResultTy.isScalar() else HBits(inferedResultTy.bit_length())
            # build a ternary expression and check types
            res = None
            for (i, v) in reversed(tuple(enumerate(self.sequence))):
                t = getattr(v, "_dtype", None)
                if t is None:
                    v = muxTy.from_py(v)
                else:
                    assert t == inferedResultTy, ("All items in sequence needs to have same type", t, inferedResultTy)

                if muxTy is not inferedResultTy:
                    # mux operates on flatened type only
                    v = v._reinterpret_cast(muxTy)

                if res is None:
                    res = v
                else:
                    res = self.index._eq(i)._ternary(v, res)

            assert res is not None
            if muxTy is not inferedResultTy:
                # undo flatening of values for mux
                res = res._reinterpret_cast(inferedResultTy)

            return res

        return None

    def _createSwitchCaseBlocks(self, toSsa: "PyBytecodeToSsa",
                       offsetForLabels: int,
                       curBlock: BasicBlock,
                       populateCaseBlockFn: Callable[[ToLlvmIrTranslator, int, object], None]) -> BasicBlock:
        _o = self.instructionOffsetForLabels
        if _o is not None:
            offsetForLabels = _o

        toLlvm: ToLlvmIrTranslator = toSsa.toLlvm
        # construct sucBlock. It is a block where all case blocks will jump to
        sucBLockName = toLlvm.strCtx.addTwine(f"{curBlock.getName().str():s}_{offsetForLabels:d}_setSwEnd")
        sucBlock = BasicBlock.Create(toLlvm.ctx, sucBLockName, toLlvm.llvm.main, None)
        curLabel = toSsa.blockToLabel[curBlock]
        toSsa.labelToBlock[curLabel].end = sucBlock
        toSsa.blockToLabel[sucBlock] = curLabel

        # create a SwitchInst at the end of curBLock
        builder: IRBuilder = toLlvm.b
        curBlock, swCond = toLlvm._translateExprToLlvm(curBlock, self.index)
        builder.SetInsertPoint(curBlock)
        swInst:SwitchInst = builder.CreateSwitch(swCond, sucBlock, NumCases=len(self.sequence))
        # swInst: SwitchInst = ValueToInstruction(InstructionToSwitchInst(swInst))

        swCondTy = swCond.getType()
        swCondTyWidth = swCondTy.getIntegerBitWidth()
        for (i, v) in enumerate(self.sequence):
            # construct case block
            caseName = toLlvm.strCtx.addTwine(f"{curBlock.getName().str():s}_{offsetForLabels:d}_c{i:d}")
            caseBlock = BasicBlock.Create(toLlvm.ctx, caseName, toLlvm.llvm.main, None)
            toSsa.blockToLabel[caseBlock] = curLabel

            # add case to SwitchInst
            caseI = ValueToConstantInt(ConstantInt.get(swCondTy, APInt(swCondTyWidth, i)))
            swInst.addCase(caseI, caseBlock)

            # process case block body
            builder.SetInsertPoint(caseBlock)
            populateCaseBlockFn(toLlvm, i, v, caseBlock)

            # jump from case block to sucBlock
            builder.SetInsertPoint(caseBlock)
            assert caseBlock.getTerminator() is None, caseBlock
            builder.CreateBr(sucBlock)

        builder.SetInsertPoint(sucBlock)
        # put variable with result of the indexing on top of stack
        return sucBlock

    def expandSetitemAsSwitchCase(self,
                                  toSsa: "PyBytecodeToSsa",
                                  offsetForLabels: int,
                                  frame: PyBytecodeFrame,
                                  curBlock: BasicBlock,
                                  assignFn: Callable[[int, Union[RtlSignal, HwIO, HConst, Value]],
                                                     List[Union[Value, HdlAssignmentContainer]]]) -> BasicBlock:
        """
        :param assignFn: function with index and dst as argument
        """
        return self._createSwitchCaseBlocks(
            toSsa, offsetForLabels, curBlock,
            lambda toLlvm, i, v, caseBlock: toLlvm.visit_Assignments(caseBlock, assignFn(i, v))
        )


def expandBeforeUse(toSsa: "PyBytecodeToSsa",
                    offsetForLabels: int,
                    frame: PyBytecodeFrame, o, curBlock: BasicBlock) -> Tuple[BasicBlock, Value]:
    if isinstance(o, PyObjectRequiresExpandBeforeUse):
        o: PyObjectRequiresExpandBeforeUse
        return o.expandOnUse(toSsa, offsetForLabels, frame, curBlock)

    return curBlock, o


def expandBeforeUseSequence(toSsa: "PyBytecodeToSsa",
                    offsetForLabels: int,
                    frame: PyBytecodeFrame, oSeq: Sequence, curBlock: BasicBlock) -> Tuple[BasicBlock, Value]:
    if isinstance(oSeq, (RtlSignalBase, HwIOBase, HConst)):
        return curBlock, oSeq
    else:
        oSeqExpanded = []
        for o in oSeq:
            curBlock, o = expandBeforeUse(toSsa, offsetForLabels, frame, o, curBlock)
            oSeqExpanded.append(o)

        return curBlock, oSeqExpanded

