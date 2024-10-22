from itertools import chain
from typing import Set, Optional, Union, Literal

from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.observableList import ObservableList, ObservableListRm
from hwtHls.netlist.analysis.reachabilityCpp.reachabiltyCpp import DagGraphWithDFSReachQuery
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability, \
    NodeOrPort


class HlsNetlistAnalysisPassReachabilityCpp(HlsNetlistAnalysisPassReachability):

    def __init__(self, removed: Optional[Set[HlsNetNode]]=None):
        super(HlsNetlistAnalysisPassReachabilityCpp, self).__init__()
        self._connectionGraph: Optional[DagGraphWithDFSReachQuery] = None
        self.removed = removed

    def doesReachTo(self, src:NodeOrPort, dst:NodeOrPort):
        return self._connectionGraph.isReachable(src, dst)

    def _beforeNodeAddedListener(self, _, parentList: ObservableList[HlsNetNode], index: Union[slice, int], val: Union[HlsNetNode, Literal[ObservableListRm]]):
        if isinstance(val, HlsNetNode):
            val.dependsOn._setObserver(self._beforeInputDriveUpdate, val)
            n = val
            for io in chain(n._inputs, n._outputs):
                self._connectionGraph.insertNode(io)
            for dep in n.dependsOn:
                assert dep is None
            for uses in n.usedBy:
                assert not uses
            self._connectionGraph.insertNodeWithLinks(n, n._inputs, n._outputs)

    def _beforeInputDriveUpdate(self, n: HlsNetNode,
                                parentList: ObservableList[HlsNetNodeOut],
                                index: Union[slice, int],
                                val: Union[HlsNetNodeOut, Literal[ObservableListRm]]):
        inp = n._inputs[index]
        try:
            curDep = n.dependsOn[index]
        except IndexError:
            curDep = None

        if val is ObservableListRm or val is None:
            if isinstance(index, int):
                _len = len(n.dependsOn)
                isAppend = index == _len
                if isAppend:
                    assert val is None, val
                    self._connectionGraph.insertNode(inp)

                if curDep is not None:
                    if index < _len:
                        list.__setitem__(n.dependsOn, index, None)
                    elif isAppend:
                        list.append(n.dependsOn, None)
                    else:
                        raise IndexError(index)

                    # update curDep successors sets after we removed the use in inp port
                    self._linkDiscard(curDep, inp)

                    if isAppend:
                        list.pop(n.dependsOn)  # rm temporarily added item

                if val is ObservableListRm:
                    # remove input from internal dictionaries
                    self._connectionGraph.removeNode(inp)
            else:
                raise NotImplementedError(n, index, val)
        else:
            if isinstance(index, int):
                if curDep is val:
                    return

                _len = len(n.dependsOn)
                isAppend = index == _len
                if index < _len:
                    list.__setitem__(n.dependsOn, index, val)
                elif isAppend:
                    list.append(n.dependsOn, val)
                else:
                    raise IndexError(index)

                if curDep is not None:
                    assert inp not in curDep.obj.usedBy[curDep.out_i], (curDep, "->", inp, "usedBy should be updated before dependsOn")
                    self._linkDiscard(curDep, inp)
                val.obj.usedBy[val.out_i].append(inp)

                if isAppend:
                    self._connectionGraph.insertNode(inp)

                self._updateAfterLinkAdd(val, inp)
                tmp = val.obj.usedBy[val.out_i].pop()
                assert tmp is inp, (tmp, inp)
                if isAppend:
                    list.pop(n.dependsOn)  # remove temporal added item

            else:
                raise NotImplementedError(n, index, val)

    def _beforeOutputUpdate(self, n: HlsNetNode,
                            parentList: ObservableList[HlsNetNodeOut],
                            index: Union[slice, int],
                            val: Union[HlsNetNodeOut, Literal[ObservableListRm]]):
        if val is ObservableListRm:
            outp = n._outputs[index]
            for d in (self._dataSuccessors, self._anySuccessors):
                sucs = d.pop(outp)
                assert not sucs, (outp, "Port must not be connected before removing", sucs)
        else:
            _len = len(n._outputs)
            isAppend = index == _len
            if isAppend:
                outp = val
                if self.ommitNonData:
                    if HdlType_isNonData(outp._dtype):
                        self._connectionGraph.insertNodeWith(outp)
                    else:
                        self._connectionGraph.insertNodeWithLinks(outp, [n], [])
                else:
                    self._connectionGraph.insertNodeWithLinks(outp, [n], [])

            else:
                raise NotImplementedError(n, index, val)

    def _updateAfterLinkAdd(self, o: HlsNetNodeOut, i: HlsNetNodeIn):
        if not self.ommitNonData or not HdlType_isNonData(o._dtype):
            self._connectionGraph.dataLink(o, i)

    def _linkDiscard(self, o: HlsNetNodeOut, i:HlsNetNodeIn):
        if  not self.ommitNonData or not HdlType_isNonData(o._dtype):
            self._connectionGraph.removeLink(o, i)

    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        assert self._dataGraph is None
        removed = self.removed
        anyConG = self._dataGraph = HlsNetlistAnalysisPassReachability()
        addAnyNode = anyConG.insertNode
        addAnyNodeWithLinks = anyConG.insertNodeWithLinks

        for n in netlist.iterAllNodes():
            if removed is not None and n in removed:
                continue
            for io in chain(n._inputs, n._outputs):
                addAnyNode(io)

            addAnyNodeWithLinks(n, n._inputs, n._outputs)

        for n in netlist.iterAllNodes():
            if removed is not None and n in removed:
                continue
            for dep, user in zip(n.dependsOn, n._inputs):
                anyConG.insertLink(dep, user)
