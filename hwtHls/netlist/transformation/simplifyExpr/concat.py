from itertools import islice
from typing import Set, Dict, List

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith


def _collectConcatOfVoidTreeOutputs(o: HlsNetNodeOut):
    for use in o.obj.usedBy[o.out_i]:
        useO = use.obj
        if isinstance(useO, HlsNetNodeOperator) and useO.operator == HwtOps.CONCAT:
            yield from _collectConcatOfVoidTreeOutputs(useO._outputs[0])
        else:
            yield use


def _collectConcatOfVoidTreeInputs(o: HlsNetNodeOut, inputs: List[HlsNetNodeOut], seen:Set[HlsNetNodeOut]):
    if o in seen:
        return True

    seen.add(o)

    duplicitySeen = False
    obj: HlsNetNode = o.obj
    if isinstance(obj, HlsNetNodeOperator) and obj.operator == HwtOps.CONCAT:
        t = obj.dependsOn[0]._dtype
        assert HdlType_isVoid(t), obj
        for i in obj.dependsOn:
            duplicitySeen |= _collectConcatOfVoidTreeInputs(i, inputs, seen)
    else:
        inputs.append(o)

    return duplicitySeen


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


def netlistReduceConcat(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    if len(n.usedBy[0]) == 1:
        onlyUser = n.usedBy[0][0]
        onlyUserObj = onlyUser.obj
        if isinstance(onlyUserObj, HlsNetNodeOperator) and onlyUserObj.operator == HwtOps.CONCAT:
            # Merge this concat into only user which is also concat
            newOps = []
            newOps.extend(onlyUserObj.dependsOn[:onlyUser.in_i])
            newOps.extend(n.dependsOn)
            newOps.extend(onlyUserObj.dependsOn[onlyUser.in_i + 1:])

            replacement = n.getHlsNetlistBuilder().buildConcat(*newOps)
            replacement.obj.tryToInheritName(onlyUser.obj)

            replaceOperatorNodeWith(onlyUserObj, replacement, worklist)
            return True

    return False


def netlistReduceConcatOfVoid(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    """
    For concatenation of data of void type the ordering of operands does not matter. Also some ports (output, dataVoidOut)
    have stronger meaning than regular ordering and lesser strength ordering dependencies can be removed from expression.
    """
    assert len(n.dependsOn) >= 2, n
    assert HdlType_isVoid(n._outputs[0]._dtype), n
    allIsSameO = True
    allIsSameObj = True
    o0 = n.dependsOn[0]
    opsWithoutConst = []
    for o in islice(n.dependsOn, 1, None):
        if o is not o0:
            allIsSameO = False
            if not allIsSameObj:
                break
        if o.obj is not o0.obj:
            allIsSameObj = False
            if not allIsSameO:
                break
        if not isinstance(o.obj, HlsNetNodeConst):
            opsWithoutConst.append(o)

    if allIsSameO:
        replaceOperatorNodeWith(n, o0, worklist)
        return True
    elif allIsSameObj:
        obj = o0.obj
        if (obj._outputs[0] in n.dependsOn):
            # data of a void sync is the strongest port
            replaceOperatorNodeWith(n, obj._outputs[0], worklist)
            return True
        elif (obj._dataVoidOut in n.dependsOn):
            # dataVoidOut is stronger than regular ordering
            replaceOperatorNodeWith(n, obj._dataVoidOut, worklist)
            return True
    elif len(opsWithoutConst) < len(n.dependsOn):
        # we can cut out some constants
        if opsWithoutConst:
            replacement = n.getHlsNetlistBuilder().buildConcat(*opsWithoutConst)
        else:
            replacement = n.dependsOn[0]  # reuse first const

        replaceOperatorNodeWith(n, replacement, worklist)
        return True

    if len(n.usedBy[0]) > 1 or (not isinstance(n.usedBy[0][0].obj, HlsNetNodeOperator)
                                or n.usedBy[0][0].obj.operator != HwtOps.CONCAT):
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

            newO = n.getHlsNetlistBuilder().buildConcat(*newInputs)
            replaceOperatorNodeWith(n, newO, worklist)
            return True

    return False
