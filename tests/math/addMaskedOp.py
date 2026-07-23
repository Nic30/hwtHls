
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyUtils import getConstOfOutput
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith


def _OP_ADD_MASKED_runSimplifyRules(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    assert n.operator in (OP_ADD_MASKED, OP_ADD_ONES_COMPLEMENT_MASKED), n
    if len(n.dependsOn) == 2:
        stateIn = None
        dataIn, maskIn = n.dependsOn
    else:
        stateIn, dataIn, maskIn = n.dependsOn
    
    # [todo] precompute sum of const data items with mask bit=1
    # [todo] rm data items with mask bit=0
    # [todo] if number of const data items is small enough precompute
    #        lookup table for variants of maskIn
    stateT = n._outputs[0]._dtype
    b = HlsNetlistBuilderWithWorklist(n.getHlsNetlistBuilder(), worklist)
    dataInC = getConstOfOutput(dataIn)
    if dataInC is not None and dataInC._is_full_valid() and int(dataInC) == 0:
        # sum(stateIn, 0, 0, ...) -> stateIn
        if stateIn is None:
            stateIn = b.buildConst(stateT.from_py(0))
        replaceOperatorNodeWith(n, stateIn, worklist)
        return True
    
    maskInC = getConstOfOutput(maskIn)
    if maskInC is not None and maskInC._is_full_valid() and int(maskInC) == 0:
        # sum(stateIn, 0 ? n0: 0, 0 ? n1: 0, ...) -> stateIn
        if stateIn is None:
            stateIn = b.buildConst(stateT.from_py(0))
        replaceOperatorNodeWith(n, stateIn, worklist)
        return True
    
    if stateIn is not None:
        stateIn: HlsNetNodeOut
        stateInC = getConstOfOutput(stateIn)
        if stateInC is not None and stateInC._is_full_valid() and int(stateInC) == 0:
            # stateIn = 0; sum(stateIn, n0, n1, ...) -> sum(n0, n1, ...)
            b.unregisterOperatorNode(n)
            worklist.append(stateIn.obj)
            n._inputs[0].disconnectFromHlsOut()
            n._removeInput(0)
            b.registerOperatorNode(n)
            return True

    return False


def _OP_ADD_MASKED_DoesNotUseLLVMOperator(*args):
    raise NotImplementedError()


# inputs: stateIn?, dataInVec, maskBitVec, output: sum,
# * arbitrary number of input items in dataInVec
# * stateIn has the same bitwidht as output, the items in dataInVec may have lower bitwidth
OP_ADD_MASKED = HOperatorDef(_OP_ADD_MASKED_DoesNotUseLLVMOperator, idStr="OP_ADD_MASKED")
OP_ADD_MASKED.runSimplifyRules = _OP_ADD_MASKED_runSimplifyRules


def _OP_ADD_ONES_COMPLEMENT_MASKED_DoesNotUseLLVMOperator(*args):
    raise NotImplementedError()

# same as OP_ADD_MASKED just using ones complement
OP_ADD_ONES_COMPLEMENT_MASKED = HOperatorDef(_OP_ADD_ONES_COMPLEMENT_MASKED_DoesNotUseLLVMOperator, idStr="OP_ADD_ONES_COMPLEMENT_MASKED")
OP_ADD_ONES_COMPLEMENT_MASKED.runSimplifyRules = _OP_ADD_MASKED_runSimplifyRules
