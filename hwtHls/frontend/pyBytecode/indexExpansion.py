from typing import Sequence, Union, Callable, List, Tuple

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.pyUtils.arrayQuery import flatten
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue
from hwtHls.scope import HlsScope
from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer


class PyObjectHwSubscriptRef():
    """
    An object which is a reference to an object in python array which is indexed in HW.
    This object must be expanded before used in expression or before it is written to.
    This object is not expanded immediately because when we construct the slice we do not know where it is used and if it only read or write access.
    """

    def __init__(self, pyBytecodeToSsa: "PyBytecodeToSsa",
                       sequence: Sequence,
                       index: Union[RtlSignal, SsaValue],
                       originalInstrOffsetForLabels: int):
        self.pyBytecodeToSsa = pyBytecodeToSsa
        self.sequence = sequence
        self.index = index
        self.originalInstrOffsetForLabels = originalInstrOffsetForLabels
    
    def expandOnUse(self, curBlock: SsaBasicBlock):
        return self.expandIndexOnPyObjAsSwitchCase(curBlock)

    def expandIndexOnPyObjAsSwitchCase(self, curBlock: SsaBasicBlock) -> Tuple[SsaValue, SsaBasicBlock]:
        res = None
        toSsa = self.pyBytecodeToSsa
        sucBlock = SsaBasicBlock(toSsa.to_ssa.ssaCtx, f"{curBlock.label:s}_getSwEnd")
        curLabel = toSsa.blockToLabel[curBlock]
        toSsa.labelToBlock[curLabel].end = sucBlock
        toSsa.blockToLabel[sucBlock] = curLabel
        offsetForLabels = self.originalInstrOffsetForLabels

        for last, (i, v) in iter_with_last(enumerate(self.sequence)):
            if res is None:
                # in first iteration create result variable in the previous block
                res = toSsa.hls.var(f"tmp_seq{offsetForLabels}", v._dtype)
            else:
                assert res._dtype == v._dtype, ("Type of items in sequence must be same", i, res._dtype, v._dtype)
    
            if last:
                cond = None
            else:
                curBlock, cond = toSsa.to_ssa.visit_expr(curBlock, self.index._eq(i))
            
            caseBlock = SsaBasicBlock(toSsa.to_ssa.ssaCtx, f"{curBlock.label:s}_{offsetForLabels:d}_c{i:d}")
            toSsa.blockToLabel[caseBlock] = curLabel
            curBlock.successors.addTarget(cond, caseBlock)
            toSsa._onAllPredecsKnown(caseBlock)
            toSsa.to_ssa.visit_CodeBlock_list(caseBlock, flatten([
                res(v)
            ]))
            caseBlock.successors.addTarget(None, sucBlock)
    
        if res is None:
            raise IndexError("Indexing using HW object on Python object of zero size, it is impossible to resolve result type for HW", self.sequence, self.index)
    
        toSsa._onAllPredecsKnown(sucBlock)
        return res, sucBlock

    def expandSetitemAsSwitchCase(self,
                                  curBlock: SsaBasicBlock,
                                  assignFn: Callable[[int, Union[RtlSignal, Interface, HValue, SsaValue]], 
                                                     List[Union[SsaValue, HdlAssignmentContainer]]]) -> SsaBasicBlock:
        
        """
        :param assignFn: function with index and dst as argument
        """
        toSsa = self.pyBytecodeToSsa
        offsetForLabels = self.originalInstrOffsetForLabels
        sucBlock = SsaBasicBlock(toSsa.to_ssa.ssaCtx, f"{curBlock.label:s}_{offsetForLabels:d}_setSwEnd")
        curLabel = toSsa.blockToLabel[curBlock]
        toSsa.labelToBlock[curLabel].end = sucBlock
        toSsa.blockToLabel[sucBlock] = curLabel

        for last, (i, v) in iter_with_last(enumerate(self.sequence)):
            if last:
                cond = None
            else:
                curBlock, cond = toSsa.to_ssa.visit_expr(curBlock, self.index._eq(i))
            
            caseBlock = SsaBasicBlock(toSsa.to_ssa.ssaCtx, f"{curBlock.label:s}_{offsetForLabels:d}_c{i:d}")
            toSsa.blockToLabel[caseBlock] = curLabel
    
            curBlock.successors.addTarget(cond, caseBlock)
            toSsa._onAllPredecsKnown(caseBlock)
    
            toSsa.to_ssa.visit_CodeBlock_list(caseBlock, flatten([
                assignFn(i, v)
            ]))
            caseBlock.successors.addTarget(None, sucBlock)
    
        toSsa._onAllPredecsKnown(sucBlock)
        # put variable with result of the indexing on top of stack
        return sucBlock


def expandBeforeUse(o, curBlock: SsaBasicBlock):
    if isinstance(o, PyObjectHwSubscriptRef):
        o: PyObjectHwSubscriptRef
        return o.expandOnUse(curBlock)
    
    return o, curBlock