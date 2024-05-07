from copy import copy
from itertools import chain
from typing import Set, Dict, Optional, Tuple, Union, Literal, List, Generator

from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData, HVoidData, \
    HdlType_isVoid
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.observableList import ObservableList, ObservableListRm
from hwtHls.netlist.analysis.reachabilityCpp.reachabiltyCpp import DagGraphWithDFSReachQuery
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability, \
    NodeOrPort


class HlsNetlistAnalysisPassReachabilityCpp(HlsNetlistAnalysisPassReachability):

    def __init__(self, removed: Optional[Set[HlsNetNode]]=None):
        super(HlsNetlistAnalysisPassReachabilityCpp, self).__init__()
        self._dataGraph: Optional[DagGraphWithDFSReachQuery] = None
        self._anyConGraph: Optional[DagGraphWithDFSReachQuery] = None
        self.removed = removed

    def doesReachTo(self, src:NodeOrPort, dst:NodeOrPort):
        return self._anyConGraph.isReachable(src, dst)

    def doesReachToControl(self, src:HlsNetNode, dst:HlsNetNodeExplicitSync):
        for i in (dst.extraCond, dst.skipWhen):
            if i is not None and self._anyConGraph.isReadable(src, i):
                return True

        return False

    def doesReachToData(self, src:HlsNetNode, dst:HlsNetNode):
        return self._dataGraph.isReachable(src, dst)

    def doesUseControlOf(self, n: HlsNetNodeExplicitSync, user: HlsNetNode):
        if isinstance(n, HlsNetNodeRead) and n._validNB is not None:
            return self._anyConGraph.isReachable(n._validNB, user)

        return False

    def _beforeNodeAddedListener(self, _, parentList: ObservableList[HlsNetNode], index: Union[slice, int], val: Union[HlsNetNode, Literal[ObservableListRm]]):
        if isinstance(val, HlsNetNode):
            val.dependsOn._setObserver(self._beforeInputDriveUpdate, val)
            n = val
            for io in chain(n._inputs, n._outputs):
                self._anyConGraph.insertNode(io)
                self._dataGraph.insertNode(io)
            for dep in n.dependsOn:
                assert dep is None
            for uses in n.usedBy:
                assert not uses
            self._anyConGraph.insertNodeWithLinks(n, n._inputs, n._outputs)
            self._dataGraph.insertNodeWithLinks(n, n._inputs, n._outputs)

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
                    self._anyConGraph.insertNode(inp)
                    self._dataGraph.insertNode(inp)

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
                    for d in (self._dataGraph, self._anyConGraph):
                        d.removeNode(inp)
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
                    self._anyConGraph.insertNode(inp)
                    self._dataGraph.insertNode(inp)

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
                self._anyConGraph.insertNodeWithLinks(outp, [n], [])
                if HdlType_isNonData(outp._dtype):
                    self._dataGraph.insertNodeWith(outp)
                else:
                    self._dataGraph.insertNodeWithLinks(outp, [n], [])
            else:
                raise NotImplementedError(n, index, val)

    def _updateAfterLinkAdd(self, o: HlsNetNodeOut, i: HlsNetNodeIn):
        self._anyConGraph.insertLink(o, i)
        if not HdlType_isNonData(o._dtype):
            self._anyConGraph.dataLink(o, i)

    def _linkDiscard(self, o: HlsNetNodeOut, i:HlsNetNodeIn):
        self._anyConGraph.removeLink(o, i)
        if not HdlType_isNonData(o._dtype):
            self._dataGraph.removeLink(o, i)

    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        assert self._dataGraph is None
        assert self._anyConGraph is None
        removed = self.removed
        anyConG = self._dataGraph = HlsNetlistAnalysisPassReachability()
        dataG = self._anyConGraph = HlsNetlistAnalysisPassReachability()
        addAnyNode = anyConG.insertNode
        addDataNode = dataG.insertNode
        addAnyNodeWithLinks = anyConG.insertNodeWithLinks
        addDataNodeWithLinks = dataG.insertNodeWithLinks

        for n in netlist.iterAllNodes():
            if removed is not None and n in removed:
                continue
            for io in chain(n._inputs, n._outputs):
                addAnyNode(io)
                addDataNode(io)

            addAnyNodeWithLinks(n, n._inputs, n._outputs)
            addDataNodeWithLinks(n, n._inputs, n._outputs)

        for n in netlist.iterAllNodes():
            if removed is not None and n in removed:
                continue
            for dep, user in zip(n.dependsOn, n._inputs):
                anyConG.insertLink(dep, user)
