from typing import Sequence, Union, Callable, List, Tuple, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.const import HConst
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.mainBases import HwIOBase
from hwt.mainBases import RtlSignalBase
from hwt.pyUtils.arrayQuery import flatten
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue
from hwt.math import AnyHValue


class PyObjectHwSubscriptRef():
    """
    An object which is a reference to an object in python array which is indexed in HW.
    This object must be expanded before used in expression or before it is written to.
    This object is not expanded immediately because when we construct the slice we do not know where it is used and if it only read or write access.
    """

    def __init__(self, instructionOffsetForLabels: Optional[int], sequence: Sequence,
                       index: Union[RtlSignal, SsaValue],
                       ):
        self.instructionOffsetForLabels = instructionOffsetForLabels
        self.sequence = sequence
        self.index = index

    def expandOnUse(self, toSsa: "PyBytecodeToSsa",
                        offsetForLabels: int,
                        frame: PyBytecodeFrame, curBlock: SsaBasicBlock):
        return self.expandIndexOnPyObjAsSwitchCase(toSsa, offsetForLabels, frame, curBlock)

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
            # build a ternary expression and check types
            res = None
            for (i, v) in reversed(tuple(enumerate(self.sequence))):
                t = getattr(v, "_dtype", None)
                if t is None:
                    v = inferedResultTy.from_py(v)
                else:
                    assert t == inferedResultTy, ("All items in sequence needs to have same type", t, inferedResultTy)
                
                if res is None:
                    res = v
                else:
                    res = self.index._eq(i)._ternary(v, res)
            
            assert res is not None
            return res

        return None

    def expandIndexOnPyObjAsSwitchCase(self,
                       toSsa: "PyBytecodeToSsa",
                       offsetForLabels: int,
                       frame: PyBytecodeFrame,
                       curBlock: SsaBasicBlock) -> Tuple[SsaValue, SsaBasicBlock]:
        _o = self.instructionOffsetForLabels
        if _o is not None:
            offsetForLabels = _o

        res = self.tryExpandIndexOnPyObjAsTernary()
        if res is not None:
            return res, curBlock

        astToSsa: HlsAstToSsa = toSsa.toSsa
        sucBlock = SsaBasicBlock(astToSsa.ssaCtx, f"{curBlock.label:s}_getSwEnd")
        curLabel = toSsa.blockToLabel[curBlock]
        toSsa.labelToBlock[curLabel].end = sucBlock
        toSsa.blockToLabel[sucBlock] = curLabel

        res = None
        for last, (i, v) in iter_with_last(enumerate(self.sequence)):
            assert isinstance(v, (HConst, RtlSignal, HwIO, PyObjectHwSubscriptRef)), ("Item in sequence must have HDL type", v)
            if res is None:
                # in first iteration create result variable in the previous block
                res = toSsa.hls.var(f"tmp_seq{offsetForLabels}", v._dtype)
            else:
                assert res._dtype == v._dtype, ("Type of items in sequence must be same", i, res._dtype, v._dtype)

            if last:
                cond = None
            else:
                curBlock, cond = astToSsa.visit_expr(curBlock, self.index._eq(i))

            caseBlock = SsaBasicBlock(astToSsa.ssaCtx, f"{curBlock.label:s}_{offsetForLabels:d}_c{i:d}")
            toSsa.blockToLabel[caseBlock] = curLabel
            curBlock.successors.addTarget(cond, caseBlock)
            toSsa._onAllPredecsKnown(frame, caseBlock)
            astToSsa.visit_CodeBlock_list(caseBlock, flatten([
                res(v)
            ]))
            caseBlock.successors.addTarget(None, sucBlock)

        if res is None:
            raise IndexError("Indexing using HW object on Python object of zero size, it is impossible to resolve result type for HW", self.sequence, self.index)

        toSsa._onAllPredecsKnown(frame, sucBlock)
        return res, sucBlock

    def expandSetitemAsSwitchCase(self,
                                  toSsa: "PyBytecodeToSsa",
                                  offsetForLabels: int,
                                  frame: PyBytecodeFrame,
                                  curBlock: SsaBasicBlock,
                                  assignFn: Callable[[int, Union[RtlSignal, HwIO, HConst, SsaValue]],
                                                     List[Union[SsaValue, HdlAssignmentContainer]]]) -> SsaBasicBlock:

        """
        :param assignFn: function with index and dst as argument
        """
        _o = self.instructionOffsetForLabels
        if _o is not None:
            offsetForLabels = _o

        astToSsa: HlsAstToSsa = toSsa.toSsa
        sucBlock = SsaBasicBlock(astToSsa.ssaCtx, f"{curBlock.label:s}_{offsetForLabels:d}_setSwEnd")
        curLabel = toSsa.blockToLabel[curBlock]
        toSsa.labelToBlock[curLabel].end = sucBlock
        toSsa.blockToLabel[sucBlock] = curLabel

        for last, (i, v) in iter_with_last(enumerate(self.sequence)):
            if last:
                cond = None
            else:
                curBlock, cond = astToSsa.visit_expr(curBlock, self.index._eq(i))

            caseBlock = SsaBasicBlock(astToSsa.ssaCtx, f"{curBlock.label:s}_{offsetForLabels:d}_c{i:d}")
            toSsa.blockToLabel[caseBlock] = curLabel

            curBlock.successors.addTarget(cond, caseBlock)
            toSsa._onAllPredecsKnown(frame, caseBlock)

            astToSsa.visit_CodeBlock_list(caseBlock, flatten([
                assignFn(i, v)
            ]))
            caseBlock.successors.addTarget(None, sucBlock)

        toSsa._onAllPredecsKnown(frame, sucBlock)
        # put variable with result of the indexing on top of stack
        return sucBlock


def expandBeforeUse(toSsa: "PyBytecodeToSsa",
                    offsetForLabels: int,
                    frame: PyBytecodeFrame, o, curBlock: SsaBasicBlock):
    if isinstance(o, PyObjectHwSubscriptRef):
        o: PyObjectHwSubscriptRef
        return o.expandOnUse(toSsa, offsetForLabels, frame, curBlock)

    return o, curBlock


def expandBeforeUseSequence(toSsa: "PyBytecodeToSsa",
                    offsetForLabels: int,
                    frame: PyBytecodeFrame, oSeq: Sequence, curBlock: SsaBasicBlock):
    if isinstance(oSeq, (RtlSignalBase, HwIOBase, HConst)):
        return oSeq, curBlock
    else:
        oSeqExpanded = []
        for o in oSeq:
            o, curBlock = expandBeforeUse(toSsa, offsetForLabels, frame, o, curBlock)
            oSeqExpanded.append(o)
        return oSeqExpanded, curBlock

