from dataclasses import dataclass

from hwt.hdl.operatorDefs import HwtOps
from hwtHls.netlist.builder import HlsNetlistBuilder, \
    HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from pyMathBitPrecise.bit_utils import to_unsigned, mask
from hwt.pyUtils.arrayQuery import balanced_reduce
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from tests.math.addTree import OP_ADD_TREE


@dataclass
class AdderTreeTerm():
    value: HlsNetNodeOut
    multiplier: int  # 1 rpresents +value, -1 represents -value, but the value of multiplier
    # may be arbitrary intger as a single term may have appered multiple times in the tree


def adderTreeCollectTerms(o: HlsNetNodeOut, multiplier: int, terms: list[AdderTreeTerm], treeNodes: set[HlsNetNode]) -> int:
    """
    :returns: accumulated constant bias
    """
    assert multiplier != 0
    n = o.obj
    
    if isinstance(n, HlsNetNodeConst):
        if n.val._is_full_valid():
            return to_unsigned(int(n.val) * multiplier, o._dtype.bit_length())
        else:
            terms.append(AdderTreeTerm(o, multiplier))
            return 0
            
    if n in treeNodes and isinstance(n, HlsNetNodeOperator):
        op = n.operator
        if op == HwtOps.MINUS_UNARY:
            return adderTreeCollectTerms(n.dependsOn[0], multiplier * -1)
        elif op == HwtOps.ADD:
            return adderTreeCollectTerms(n.dependsOn[0], multiplier) + \
                   adderTreeCollectTerms(n.dependsOn[1], multiplier)
        elif op == HwtOps.SUB:
            return adderTreeCollectTerms(n.dependsOn[0], multiplier) + \
                   adderTreeCollectTerms(n.dependsOn[1], multiplier * -1)
        
    terms.append(AdderTreeTerm(o, multiplier))
    return 0


def adderTreePruneTerms(terms: list[AdderTreeTerm]) -> list[AdderTreeTerm]:
    termMap: dict[HlsNetNodeOut, AdderTreeTerm] = {}
    newTerms:list[AdderTreeTerm] = []
    for t in terms:
        existing = termMap.get(t.value)
        if existing is not None:
            existing.multiplier += t.multiplier
        else:
            termMap[t.value] = t
            newTerms.append(t)
        
    return [t for t in newTerms if t.multiplier != 0]
    

_ADD_SUB = (HwtOps.ADD, HwtOps.SUB, HwtOps.MINUS_UNARY) 


def _discardSubtreeFromSet(n: HlsNetNodeOperator, potentialTreeNodes: set[HlsNetNode]):
    try:
        potentialTreeNodes.remove(n)
    except KeyError:
        return

    for dep in n.dependsOn:
        depN = dep.obj
        _discardSubtreeFromSet(depN, potentialTreeNodes)


def _adderTreeFindTreeNodes(node: HlsNetNodeOperator, potentialTreeNodes:set[HlsNetNode]):
    potentialTreeNodes.add(node)
    for dep in node.dependsOn:
        depN = dep.obj
        if isinstance(depN, HlsNetNodeOperator) and depN.operator in _ADD_SUB:
            _adderTreeFindTreeNodes(depN, potentialTreeNodes)


def adderTreeFind(node: HlsNetNodeOperator):
    if node.operator not in _ADD_SUB:
        return None

    potentialTreeNodes:set[HlsNetNode] = {}
    assert len(node.usedBy) == 1, node
    for user in node.usedBy[0]:
        if isinstance(user.obj, HlsNetNodeOperator) and user.obj.operator in _ADD_SUB:
            return None  # the tree begins on user or its user, not there
    
    _adderTreeFindTreeNodes(node, potentialTreeNodes)
    _potentialTreeNodes = list(potentialTreeNodes)
    for n in _potentialTreeNodes:
        if n is node:
            continue
        hasUseOutOfTree = False
        for uses in n.usedBy:
            for u in uses:
                if u.obj not in potentialTreeNodes:
                    hasUseOutOfTree = True
                    break
        if hasUseOutOfTree:
            _discardSubtreeFromSet(n, potentialTreeNodes)
    return potentialTreeNodes

    
def adderTreeExtract(builder: HlsNetlistBuilderWithWorklist, root: HlsNetNode) -> bool:
    treeNodes = adderTreeFind(root)
    if treeNodes is None or len(treeNodes) < 2:
        return None
    terms: list[AdderTreeTerm] = []
    const_bias = adderTreeCollectTerms(root._outputs[0], 1, terms, treeNodes)
    terms = adderTreePruneTerms(terms)
    
    # normalize input terms
    t = root._outputs[0]._dtype
    for term in terms:
        if abs(term.multiplier) > 1:
            mul = builder.buildConstPy(t, abs(term.multiplier))
            term.value = builder.buildOp(HwtOps.MUL, t, term.value, mul)
            term.multiplier = 1 if term.multiplier >= 0 else -1
        
        if term.multiplier == -1:
            const_bias += 1
            term.value = builder.buildNot(term.value)
    
    const_bias &= mask(t.bit_length())
    if const_bias != 0:
        c = builder.buildConstPy(t, const_bias)
        terms.append(AdderTreeTerm(c, 1))

    inputs = tuple(sorted(terms, key=lambda t: (t.value.obj._id, t.value.out_i)))
    newO = builder.buildOp(OP_ADD_TREE, None, t, *inputs)
    replaceOperatorNodeWith(root, newO, builder.worklist)
    return True
