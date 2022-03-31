from typing import Sequence, Union

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.pyUtils.arrayQuery import flatten
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue


def expandIndexOnPyObjAsSwitchCase(pyBytecodeToSsa: "PythonBytecodeToSsa", curBlock: SsaBasicBlock,
                                    offsetForLabels: int,
                                    sequence:Sequence,
                                    index: Union[RtlSignal, SsaValue],
                                    stack: list):
    res = None
    sucBlock = SsaBasicBlock(pyBytecodeToSsa.to_ssa.ssaCtx, f"{curBlock.label:s}_getSwEnd")
    curLabel = pyBytecodeToSsa.blockToLabel[curBlock]
    pyBytecodeToSsa.labelToBlock[curLabel].end = sucBlock
    pyBytecodeToSsa.blockToLabel[sucBlock] = curLabel

    for last, (i, v) in iter_with_last(enumerate(sequence)):
        if res is None:
            # in first iteration create result variable in the previous block
            res = pyBytecodeToSsa.hls.var(f"tmp_seq{offsetForLabels}", v._dtype)
        else:
            assert res._dtype == v._dtype, ("Type of items in sequence must be same", i, res._dtype, v._dtype)

        if last:
            cond = None
        else:
            curBlock, cond = pyBytecodeToSsa.to_ssa.visit_expr(curBlock, index._eq(i))
        
        caseBlock = SsaBasicBlock(pyBytecodeToSsa.to_ssa.ssaCtx, f"{curBlock.label:s}_{offsetForLabels:d}_c{i:d}")
        pyBytecodeToSsa.blockToLabel[caseBlock] = curLabel
        curBlock.successors.addTarget(cond, caseBlock)
        pyBytecodeToSsa._onAllPredecsKnown(caseBlock)
        pyBytecodeToSsa.to_ssa.visit_CodeBlock_list(caseBlock, flatten([
            res(v)
        ]))
        caseBlock.successors.addTarget(None, sucBlock)

    if res is None:
        raise IndexError("Indexing using HW object on Python object of zero size", sequence, index)

    pyBytecodeToSsa._onAllPredecsKnown(sucBlock)
    # put variable with result of the indexing on top of stack
    stack.append(res)
    return sucBlock


def expandSetitemOnPytObjAsSwitchCase(pyBytecodeToSsa: "PythonBytecodeToSsa",
                                      curBlock: SsaBasicBlock,
                                      offsetForLabels: int,
                                      sequence:Sequence,
                                      index: Union[RtlSignal, SsaValue],
                                      val,
                                      stack: list):
    sucBlock = SsaBasicBlock(pyBytecodeToSsa.to_ssa.ssaCtx, f"{curBlock.label:s}_{offsetForLabels:d}_setSwEnd")
    curLabel = pyBytecodeToSsa.blockToLabel[curBlock]
    pyBytecodeToSsa.labelToBlock[curLabel].end = sucBlock
    pyBytecodeToSsa.blockToLabel[sucBlock] = curLabel

    for last, (i, v) in iter_with_last(enumerate(sequence)):
        if last:
            cond = None
        else:
            curBlock, cond = pyBytecodeToSsa.to_ssa.visit_expr(curBlock, index._eq(i))
        
        caseBlock = SsaBasicBlock(pyBytecodeToSsa.to_ssa.ssaCtx, f"{curBlock.label:s}_{offsetForLabels:d}_c{i:d}")
        pyBytecodeToSsa.blockToLabel[caseBlock] = curLabel

        curBlock.successors.addTarget(cond, caseBlock)
        pyBytecodeToSsa._onAllPredecsKnown(caseBlock)

        pyBytecodeToSsa.to_ssa.visit_CodeBlock_list(caseBlock, flatten([
            v(val)
        ]))
        caseBlock.successors.addTarget(None, sucBlock)

    pyBytecodeToSsa._onAllPredecsKnown(sucBlock)
    # put variable with result of the indexing on top of stack
    return sucBlock
