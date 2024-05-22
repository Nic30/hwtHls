from typing import Set, Sequence, List, Dict

from hwt.hdl.operatorDefs import BITWISE_OPS, COMPARE_OPS, HwtOps
from hwt.hdl.const import HConst
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.translation.hlsNetlistExprToLlvmIr import HlsNetlistExprToLlvmIr
from hwtHls.netlist.translation.llvmIrExprToHlsNetlist import LlvmIrExprToHlsNetlist


_collectCmpContainingExpr_OPS = {
    *BITWISE_OPS,
    *COMPARE_OPS,
}


def _collectCmpContainingExprInToOut(o: HlsNetNodeOut, collectedNodes: SetList[HlsNetNode]):
    """
    Walk expression tree leafs to root and collect all operands which are in _collectCmpContainingExpr_OPS
    """
    for user in o.obj.usedBy[o.out_i]:
        user: HlsNetNodeIn
        uObj = user.obj
        if uObj in collectedNodes:
            continue
        if isinstance(uObj, HlsNetNodeOperator) and (
            uObj.operator in _collectCmpContainingExpr_OPS or
            uObj.operator == HwtOps.TERNARY and len(uObj._inputs) == 3):
            assert len(uObj._outputs) == 1, uObj
            collectedNodes.append(uObj)
            _collectCmpContainingExprInToOut(uObj._outputs[0], collectedNodes)


def runLlvmCmpOpt(builder: HlsNetlistBuilder, worklist: SetList[HlsNetNode],
                  removed: Set[HlsNetNode], allNodeIt: Sequence[HlsNetNode]):
    """
    Run LLVM expression simplify pipeline to optimize expressions with comparisons
    """
    inputs: SetList[HlsNetNodeOut] = SetList()
    cmpCoutPerOut: Dict[HlsNetNodeOut, int] = {}
    for n in allNodeIt:
        n: HlsNetNode
        if n in removed:
            continue
        if isinstance(n, HlsNetNodeOperator) and n.operator in COMPARE_OPS:
            for op in n.dependsOn:
                if isinstance(op.obj, HlsNetNodeConst):
                    continue
                cnt = cmpCoutPerOut.get(op, 0)
                if cnt == 1:
                    inputs.append(op)  # append to inputs if there are more than 1 compare operands on this output
                cmpCoutPerOut[op] = cnt + 1

    collectedNodes: SetList[HlsNetNode] = SetList()
    for dep in inputs:
        if dep.obj in collectedNodes:
            continue
        _collectCmpContainingExprInToOut(dep, collectedNodes)

    outputs: List[HlsNetNodeOut] = []
    for n in collectedNodes:
        n: HlsNetNode
        for o in n._outputs:
            for use in o.obj.usedBy[o.out_i]:
                if use.obj not in collectedNodes:
                    outputs.append(o)

        for dep in n.dependsOn:
            if dep.obj not in collectedNodes:
                obj = dep.obj
                if isinstance(obj, HlsNetNodeConst) and (obj.val._is_full_valid() or obj.val.vld_mask == 0):
                    # if is llvm compatible constant let it be a part of expression
                    continue

                inputs.append(dep)

    if outputs:
        toLlvmIr = HlsNetlistExprToLlvmIr("runLlvmCmpOpt")
        # set of inputs which were originally input
        # but then it was discovered that the expression is also an expr tree of interest
        # and the input has became output
        inputsWhichBecomeOutputs = set(o for o in outputs if o in inputs)
        if inputsWhichBecomeOutputs:
            inputs = SetList(i for i in inputs if i not in inputsWhichBecomeOutputs)
        toLlvmIr.translate(inputs, outputs)
        toLlvmIr.llvm.runExprOpt()

        toHlsNetlist = LlvmIrExprToHlsNetlist(builder.netlist)
        toHlsNetlist.fillInConstantNodesFromToLlvmIrExpr(toLlvmIr)
        newOutputs = toHlsNetlist.translate(toLlvmIr.llvm.main, inputs, outputs)
        assert len(outputs) == len(newOutputs)
        anyChangeSeen = False
        for o, newO in zip(outputs, newOutputs):
            if o is not newO:
                if isinstance(newO, HConst):
                    newO = builder.buildConst(newO)
                else:
                    newObj = newO.obj
                    if isinstance(newObj, HlsNetNodeOperator) and newObj.name is None:
                        # inherit the name is possible
                        newObj.name = o.obj.name

                builder.replaceOutput(o, newO, True)
                # we can remove "o" immediately because its parent node may have multiple outputs
                for use in newO.obj.usedBy[newO.out_i]:
                    worklist.append(use.obj)
                anyChangeSeen = True

        if anyChangeSeen:
            worklist.extend(o.obj for o in outputs)


def runLlvmMuxCondOpt(builder: HlsNetlistBuilder, worklist: SetList[HlsNetNode],
                  removed: Set[HlsNetNode], allNodeIt: Sequence[HlsNetNode]):
    """
    Use (~prevC | C) & (prevC | C) for each condition of MUX to prune duplicated checks
    in MUX conditions. Because check for previous conditions in later condition inputs are useless.
    """
    return False
    # inputs: SetList[HlsNetNodeOut] = SetList()
    # for n in allNodeIt:
    #    n: HlsNetNode
    #    if n in removed:
    #        continue
    #    if isinstance(n, HlsNetNodeMux) and len(n._inputs) > 3:
    #        for (_, c), (_, cI) in n._iterValueConditionDriverInputPairs():
    #            if c is not None:
    #                raise NotImplementedError()
    #
    #
    # collectedNodes: SetList[HlsNetNode] = SetList()
    # for dep in inputs:
    #    if dep.obj in collectedNodes:
    #        continue
    #    _collectCmpContainingExprInToOut(dep, collectedNodes)
    #
    # outputs: List[HlsNetNodeOut] = []
    # for n in collectedNodes:
    #    n: HlsNetNode
    #    for o in n._outputs:
    #        for use in o.obj.usedBy[o.out_i]:
    #            if use.obj not in collectedNodes:
    #                outputs.append(o)
    #
    #    for dep in n.dependsOn:
    #        if dep.obj not in collectedNodes:
    #            obj = dep.obj
    #            if isinstance(obj, HlsNetNodeConst) and (obj.val._is_full_valid() or obj.val.vld_mask == 0):
    #                # if is llvm compatible constant let it be a part of expression
    #                continue
    #
    #            inputs.append(dep)
    #
    # if outputs:
    #    toLlvmIr = HlsNetlistExprToLlvmIr("runLlvmCmpOpt")
    #    toLlvmIr.translate(inputs, outputs)
    #    toLlvmIr.llvm.runExprOpt()
    #
    #    toHlsNetlist = LlvmIrExprToHlsNetlist(builder.netlist)
    #    toHlsNetlist.fillInConstantNodesFromToLlvmIrExpr(toLlvmIr)
    #    newOutputs = toHlsNetlist.translate(toLlvmIr.llvm.main, inputs, outputs)
    #    assert len(outputs) == len(newOutputs)
    #    anyChangeSeen = False
    #    for o, newO in zip(outputs, newOutputs):
    #        if o is not newO:
    #            if isinstance(newO, HConst):
    #                newO = builder.buildConst(newO)
    #            else:
    #                newObj = newO.obj
    #                if isinstance(newObj, HlsNetNodeOperator) and newObj.name is None:
    #                    # inherit the name is possible
    #                    newObj.name = o.obj.name
    #
    #            builder.replaceOutput(o, newO, True)
    #            # we can remove "o" immediately because its parent node may have multiple outputs
    #            for use in newO.obj.usedBy[newO.out_i]:
    #                worklist.append(use.obj)
    #            anyChangeSeen = True
    #
    #    if anyChangeSeen:
    #        worklist.extend(o.obj for o in outputs)
    #
