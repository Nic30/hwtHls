from typing import Set, List, Dict

from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.orderable import HdlType_isVoid
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.analysis.reachability import _collectConcatOfVoidTreeInputs

 
def _getOrderingOutStrenght(o: HlsNetNodeOut):
    n: HlsNetNodeExplicitSync = o.obj
    if o.out_i == 0:
        return 3
    elif o is n._dataVoidOut:
        return 2
    else:
        if o is n._orderingOut:
            return 0
        else:
            return 1


def netlistReduceConcatOfVoid(n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    """
    For concatenation of data of void type the ordering of operands does not matter. Also some ports (output, dataVoidOut)
    have stronger meaning than regular ordering and lesser strenght ordering dependencies can be removed from expression.
    """
    o0, o1 = n.dependsOn
    if o0 is o1:
        replaceOperatorNodeWith(n, o0, worklist, removed)
        return True
    elif o0.obj is o1.obj:
        obj = o0.obj 
        if (obj._outputs[0] in (o0, o1)):
            # data of a void sync is the strongest port
            replaceOperatorNodeWith(n, obj._outputs[0], worklist, removed)
            return True
        elif (obj._dataVoidOut in (o0, o1)):
            # dataVoidOut is stronger than regular ordering
            replaceOperatorNodeWith(n, obj._dataVoidOut, worklist, removed)
            return True
    
    if len(n.usedBy[0]) > 1 or (not isinstance(n.usedBy[0][0].obj, HlsNetNodeOperator) or n.usedBy[0][0].obj.operator != AllOps.CONCAT):
        # collect all inputs and check if concat operator tree does not have any duplicit inputs
        inputs = []
        duplicity = _collectConcatOfVoidTreeInputs(n._outputs[0], inputs, set())
        representativeInput: Dict[HlsNetNodeExplicitSync, HlsNetNodeOut] = {}
        for i in inputs:
            curI = representativeInput.get(i.obj, None)
            if curI is None:
                representativeInput[i.obj] = i
            else:
                curStrength = _getOrderingOutStrenght(curI)
                newStrength = _getOrderingOutStrenght(i)
                if curStrength < newStrength:
                    representativeInput[i.obj] = i
                duplicity = True

        if duplicity:
            seen = set()
            newInputs = []
            for i in inputs:
                obj = i.obj
                if obj in seen:
                    continue
                seen.add(obj)
                newInputs.append(representativeInput[obj])
            
            newO = n.netlist.builder.buildConcatVariadic(tuple(newInputs))
            replaceOperatorNodeWith(n, newO, worklist, removed)
            return True

    return False
