from typing import Sequence, Set, List

from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.abc.abcAigToHlsNetlist import AbcAigToHlsNetlist
from hwtHls.netlist.abc.hlsNetlistToAbcAig import HlsNetlistToAbcAig
from hwtHls.netlist.abc.optScripts import abcCmd_resyn2, abcCmd_compress2
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn


def _collect1bOpTree(o: HlsNetNodeOut, inputs: UniqList[HlsNetNodeOut], inTreeOutputs: Set[HlsNetNodeOut]):
    """
    Collect tree of 1b operators ending from specified output

    :return: True if it is a non trivial output (output is trivial if driven by const or non-translated node,
        if the output is trivial it can not be optimized further)
    """
    if o in inTreeOutputs:
        # already discovered
        return True

    obj: HlsNetNode = o.obj
    if isinstance(obj, HlsNetNodeConst):
        return False

    elif isinstance(obj, HlsNetNodeOperator):
        t = obj.dependsOn[0]._dtype
        assert not HdlType_isNonData(t), obj
        if t.bit_length() == 1:
            for i in obj.dependsOn:
                _collect1bOpTree(i, inputs, inTreeOutputs)
                inTreeOutputs.add(i)
            return True

    inputs.append(o)
    return False


def runAbcControlpathOpt(builder: HlsNetlistBuilder, worklist: UniqList[HlsNetNode],
                         removed: Set[HlsNetNode], allNodeIt: Sequence[HlsNetNode]):
    """
    Run berkeley-ABC to optimize control path.
    """
    inputs: UniqList[HlsNetNodeOut] = []
    inTreeOutputs: Set[HlsNetNodeOut] = set()
    outputs: List[HlsNetNodeOut] = []
    outputsSet: Set[HlsNetNodeOut] = set()

    def collect(n: HlsNetNode, i: HlsNetNodeIn):
        o = n.dependsOn[i.in_i]
        assert o is not None, ("Input must be connected", i)
        if o not in outputsSet and _collect1bOpTree(o, inputs, inTreeOutputs):
            # it may be the case that this is just wire and can not be optimized further
            # from this reason we do not add it to collected outputs
            outputsSet.add(o)
            outputs.append(o)

    for n in allNodeIt:
        n: HlsNetNode
        if n in removed:
            continue
        if isinstance(n, HlsNetNodeExplicitSync):
            n: HlsNetNodeExplicitSync
            if n.extraCond is not None:
                collect(n, n.extraCond)
            if n.skipWhen is not None:
                collect(n, n.skipWhen)
        elif isinstance(n, HlsNetNodeMux):
            for _, c in n._iterValueConditionInputPairs():
                if c is not None:
                    collect(n, c)

    if outputs:
        toAbcAig = HlsNetlistToAbcAig()
        # filter outputs from nodes which are used only inside of this expression tree which will be replaced
        treeNodes = set(o.obj for o in inTreeOutputs)
        outputs = [o for o in outputs if any(user.obj not in treeNodes for user in o.obj.usedBy[o.out_i])]
        abcFrame, abcNet, abcAig, ioMap = toAbcAig.translate(inputs, outputs)
        abcAig.Cleanup()

        abcNet = abcCmd_resyn2(abcNet)
        abcNet = abcCmd_compress2(abcNet)

        toHlsNetlist = AbcAigToHlsNetlist(abcFrame, abcNet, abcAig, ioMap, builder)
        anyChangeSeen = False
        for o, newO in toHlsNetlist.translate():
            if o is not newO:
                if isinstance(newO, HValue):
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
            worklist.extend(o.obj for o in inTreeOutputs)
            worklist.extend(o.obj for o in outputs)
        abcFrame.DeleteAllNetworks()
