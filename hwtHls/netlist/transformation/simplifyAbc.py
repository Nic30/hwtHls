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
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn


def _collect1bOpTree(o: HlsNetNodeOut, inputs: UniqList[HlsNetNodeOut], inTreeOutputs: Set[HlsNetNodeOut]):
    """
    Collect tree of 1b operators ending from specified output

    :returns: True if it is a non trivial output (output is trivial if driven by const or non-translated node,
        if the output is trivial it can not be optimized further)
    """
    if o in inTreeOutputs:
        # already discovered
        return True

    obj: HlsNetNode = o.obj
    if isinstance(obj, HlsNetNodeConst):
        return False

    elif isinstance(obj, HlsNetNodeOperator):
        if obj.dependsOn[0]._dtype.bit_length() == 1:
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
    _collect = _collect1bOpTree

    def collect(n: HlsNetNode, i: HlsNetNodeIn):
        o = n.dependsOn[i.in_i]
        assert o is not None, ("Input must be connected", i)
        if o not in outputsSet and _collect(o, inputs, inTreeOutputs):
            # it may be the case that this is just wire and can not be optimized further
            # from this reason we do not add it to collected outputs
            outputsSet.add(o)
            outputs.append(o)
        
    for n in allNodeIt:
        n: HlsNetNode
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
        outputs = [o for o in outputs if o not in inTreeOutputs]
        abcFrame, abcNet, abcAig = toAbcAig.translate(inputs, outputs)
        abcAig.Cleanup()

        abcNet = abcCmd_resyn2(abcNet)
        abcNet = abcCmd_compress2(abcNet)

        toHlsNetlist = AbcAigToHlsNetlist(abcFrame, abcNet, abcAig, builder)
        newOutputs = toHlsNetlist.translate()
        assert len(outputs) == len(newOutputs)
        anyChangeSeen = False
        for o, newO in zip(outputs, newOutputs):
            if o is not newO:
                if isinstance(newO, HValue):
                    newO = builder.buildConst(newO)
                builder.replaceOutput(o, newO)
                # we can remove "o" immediately because its parent node may have multiple outputs
                worklist.append(newO.obj)
                anyChangeSeen = True

        if anyChangeSeen:
            worklist.extend(o.obj for o in inTreeOutputs)
            worklist.extend(o.obj for o in outputs)
        abcFrame.DeleteAllNetworks()
