from typing import Sequence, Set, List

from hwt.hdl.const import HConst
from hwt.pyUtils.setList import SetList
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
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.abc.abcCpp import Io_FileType_t


def _collect1bOpTree(o: HlsNetNodeOut,
                     inputs: SetList[HlsNetNodeOut],
                     inTreeOutputs: Set[HlsNetNodeOut],
                     collectedNodes: Set[HlsNetNode]):
    """
    Collect tree of 1b operators ending from specified output

    :param inTreeOutputs: set of outputs which were already processed
    :param collectedNodes: set of nodes which were collected into expression tree

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
            for dep in obj.dependsOn:
                _collect1bOpTree(dep, inputs, inTreeOutputs, collectedNodes)
                inTreeOutputs.add(dep)
            collectedNodes.add(obj)
            return True

    inputs.append(o)
    return False


def runAbcControlpathOpt(builder: HlsNetlistBuilder, worklist: SetList[HlsNetNode], allNodeIt: Sequence[HlsNetNode]):
    """
    Run berkeley-ABC to optimize control path.
    """
    inputs: SetList[HlsNetNodeOut] = []
    inTreeOutputs: Set[HlsNetNodeOut] = set()
    outputs: List[HlsNetNodeOut] = []
    outputsSet: Set[HlsNetNodeOut] = set()
    treeNodes: Set[HlsNetNode] = set()

    def collect(n: HlsNetNode, i: HlsNetNodeIn):
        o = n.dependsOn[i.in_i]
        assert o is not None, ("Input must be connected", i)
        if o not in outputsSet and _collect1bOpTree(o, inputs, inTreeOutputs, treeNodes):
            # it may be the case that this is just wire and can not be optimized further
            # from this reason we do not add it to collected outputs
            outputsSet.add(o)
            outputs.append(o)

    for n in allNodeIt:
        n: HlsNetNode
        if n._isMarkedRemoved:
            continue
        if isinstance(n, HlsNetNodeExplicitSync):
            n: HlsNetNodeExplicitSync
            if n.extraCond is not None:
                collect(n, n.extraCond)
            if n.skipWhen is not None:
                collect(n, n.skipWhen)
            if isinstance(n, HlsNetNodeWrite):
                if n._portSrc is not None:
                    src = n.dependsOn[n._portSrc.in_i]
                    if src._dtype.bit_length() == 1:
                        collect(n, n._portSrc)
        elif isinstance(n, HlsNetNodeMux):
            for _, c in n._iterValueConditionInputPairs():
                if c is not None:
                    collect(n, c)

    if outputs:
        toAbcAig = HlsNetlistToAbcAig()
        # filter outputs from nodes which are used only inside of this expression tree which will be replaced
        outputs = [o for o in outputs
                        if any(user.obj not in treeNodes
                               for user in o.obj.usedBy[o.out_i])]
        abcFrame, abcNet, abcAig, ioMap = toAbcAig.translate(inputs, outputs)
        abcAig.Cleanup()
        # abcNet.Io_Write("runAbcControlpathOpt.abc.0.dot", Io_FileType_t.IO_FILE_DOT)
        abcNet = abcCmd_resyn2(abcNet)
        abcNet = abcCmd_compress2(abcNet)
        # abcNet.Io_Write("runAbcControlpathOpt.abc.1.dot", Io_FileType_t.IO_FILE_DOT)

        toHlsNetlist = AbcAigToHlsNetlist(abcFrame, abcNet, abcAig, ioMap, builder)
        anyChangeSeen = False
        for o, newO in toHlsNetlist.translate():
            if o is not newO:
                # print("replace")
                # print("    ", o)
                # print("    ", newO)
                if isinstance(newO, HConst):
                    newO = builder.buildConst(newO)
                else:
                    newObj = newO.obj
                    if isinstance(newObj, HlsNetNodeOperator):
                        # inherit the name is possible
                        newObj.tryToInheritName(o.obj)

                builder.replaceOutput(o, newO, True)
                # we can remove "o" immediately because its parent node may have multiple outputs
                for use in newO.obj.usedBy[newO.out_i]:
                    worklist.append(use.obj)
                anyChangeSeen = True
            #else:
            #    print("same")
            #    print("    ", o)

        if anyChangeSeen:
            worklist.extend(o.obj for o in inTreeOutputs)
            worklist.extend(o.obj for o in outputs)
        abcFrame.DeleteAllNetworks()
