from io import StringIO
from itertools import islice
from typing import List, Tuple, Optional, Dict

from hwt.hdl.types.defs import BIT
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.transformation.channelHandshakeCycleBreak import RtlArchPassChannelHandshakeCycleBreak, \
    ChannelHandshakeCycleDeadlockError
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidData
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeWriteAnyChannel, \
    HlsNetNodeReadAnyChannel
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.translation.dumpNodesDot import HlsNetlistPassDumpNodesDot
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.examples.base_serialization_TC import BaseSerializationTC


class BreakHandshakeCycles_TC(BaseSerializationTC):
    __FILE__ = __file__

    @staticmethod
    def _parseChannelSpec(nodeSpec:str):
        specParts = nodeSpec.split(" ")
        nodeName = specParts[0]
        nodeType = nodeName[0]
        if nodeName.startswith("r") or nodeName.startswith("w"):
            channelType = nodeName[1]
            assert channelType in ('f', 'b'), channelType
            channelId = int(nodeName[2:])
        else:
            channelType = None
            assert nodeType in ('i', 'o'), nodeType
            channelId = int(nodeName[1:])

        initValueCnt = 0
        hasSw = False
        hasEc = False
        for specPart in islice(specParts, 1, None):
            specPart: str
            if specPart.startswith("init:"):
                initValueCnt = int(specPart[len("init:"):])
                assert initValueCnt >= 1, (nodeSpec, initValueCnt)
            elif specPart == "sw":
                hasSw = True
            elif specPart == "ec":
                hasEc = True
            else:
                raise NotImplementedError(nodeSpec, specPart)

        return nodeName, nodeType, channelType, channelId, initValueCnt, hasSw, hasEc

    def _subNodesFromStages(self, stages: List[List[HlsNetNode]]):
        subNodes = SetList()
        for nodes in stages:
            subNodes.extend(nodes)
        return subNodes

    def _test_graph(self, graph: List[Tuple[str, List[List[HlsNetNode]]]]):
        netlist = HlsNetlistCtx(None, int(1e6), "test", platform=VirtualHlsPlatform())
        netlist._setBuilder(HlsNetlistBuilder(netlist))
        clkPeriod: SchedTime = netlist.normalizedClkPeriod
        channels: Dict[int, Tuple[Optional[HlsNetNodeWriteAnyChannel], Optional[HlsNetNodeReadAnyChannel]]] = {}
        nameToNode: Dict[str, HlsNetNode] = {}
        for elmName, elmNodeTemplate in graph:
            stages = []
            for stageIndex, stageTemplate in enumerate(elmNodeTemplate):
                stageNodes = []
                for nodeName in stageTemplate:
                    nodeName, nodeTy, cTy, cId, initValueCnt, hasSw, hasEc = self._parseChannelSpec(nodeName)
                    if nodeTy == "r":
                        cur = channels.get(cId, None)
                        if cTy == 'b':
                            r = HlsNetNodeReadBackedge(netlist, HVoidData, nodeName)
                        else:
                            assert cTy == 'f'
                            r = HlsNetNodeReadForwardedge(netlist, HVoidData, nodeName)

                        if cur is not None:
                            assert cur[1] is None, ("This channel must not have read already", cId, cur)
                            cur[0].associateRead(r)
                            channels[cId] = (cur[0], r)
                        else:
                            # write is not instantiated yet
                            channels[cId] = (None, r)
                        n = r

                    elif nodeTy == 'w':
                        cur = channels.get(cId, None)
                        if cTy == 'b':
                            w = HlsNetNodeWriteBackedge(netlist, name=nodeName)
                        else:
                            assert cTy == 'f'
                            w = HlsNetNodeWriteForwardedge(netlist, name=nodeName)
                        if initValueCnt:
                            w.channelInitValues = tuple(() for _ in range(initValueCnt))
                        if cur is not None:
                            assert cur[0] is None, ("This channel must not have write already", cId, cur)
                            w.associateRead(cur[1])
                            channels[cId] = (w, cur[0])
                        else:
                            # write is not instantiated yet
                            channels[cId] = (w, None)
                        n = w
                    elif nodeTy == 'i':
                        n = HlsNetNodeRead(netlist, None, HVoidData, nodeName)
                    elif nodeTy == 'o':
                        n = HlsNetNodeWrite(netlist, None, nodeName)
                    else:
                        raise NotImplementedError(nodeTy)

                    if hasEc:
                        nEc = HlsNetNodeRead(netlist, None, BIT, f"{nodeName}_ec")
                        nEc._rtlUseReady = nEc._rtlUseValid = False
                        stageNodes.append(nEc)
                        nEc.resolveRealization()
                        nEc._setScheduleZeroTimeSingleClock(clkPeriod * stageIndex)
                        n.addControlSerialExtraCond(nEc._outputs[0], addDefaultScheduling=True)

                    if hasSw:
                        nSw = HlsNetNodeRead(netlist, None, BIT, f"{nodeName}_sw")
                        nSw._rtlUseReady = nSw._rtlUseValid = False
                        stageNodes.append(nSw)
                        nSw.resolveRealization()
                        nSw._setScheduleZeroTimeSingleClock(clkPeriod * stageIndex)
                        n.addControlSerialSkipWhen(nSw._outputs[0], addDefaultScheduling=True)

                    n.resolveRealization()
                    n._setScheduleZeroTimeSingleClock(clkPeriod * stageIndex)
                    n._rtlUseReady = True
                    n._rtlUseValid = True

                    stageNodes.append(n)
                    nameToNode[nodeName] = n

                stages.append(stageNodes)

            elm = ArchElementPipeline(netlist, elmName, self._subNodesFromStages(stages), stages, None)
            elm.resolveRealization()
            elm._setScheduleZeroTimeSingleClock(0)
            nameToNode[elmName] = elm
            netlist.nodes.append(elm)

        RtlArchPassChannelHandshakeCycleBreak().runOnHlsNetlist(netlist)
        buff = StringIO()
        HlsNetlistPassDumpNodesDot(lambda name: (buff, False), expandAggregates=True, addLegend=False).runOnHlsNetlist(netlist)
        self.assert_same_as_file(buff.getvalue(), "data/" + self.getTestName() + ".dot")
        return nameToNode

    def test_wire(self):
        graph = [("p0", [["i0", "o0"]])]
        self._test_graph(graph)

    def test_wire_iSw(self):
        graph = [("p0", [["i0 sw", "o0"]])]
        self._test_graph(graph)

    def test_wire_oSw(self):
        graph = [("p0", [["i0", "o0 sw"]])]
        self._test_graph(graph)

    def test_wire_ioSw(self):
        graph = [("p0", [["i0 sw", "o0 sw"]])]
        self._test_graph(graph)

    def test_wire_2clk(self):
        graph = [("p0", [["i0", "wf0"], ["rf0", "o0"]])]
        self._test_graph(graph)

    def test_wire_2x(self):
        graph = [("p0", [["i0", "i1", "o0", "o1"]])]
        self._test_graph(graph)

    def test_wire_2parallelIndependent(self):
        graph = [("p0", [["i0", "o0"]]),
                 ("p1", [["i1", "o1"]])]
        self._test_graph(graph)

    def test_wire_2parallelOptional(self):
        graph = [("p0", [["i0", "wf0 ec sw"]]),
                 ("p1", [["rf0 ec sw", "o1"]])]
        self._test_graph(graph)

    def test_wire_2parallel_1f(self):
        graph = [("p0", [["i0", "o0", 'wf0']]),
                 ("p1", [["i1", "o1", 'rf0']])]
        self._test_graph(graph)

    def test_wire_2parallel_2f(self):
        graph = [("p0", [["i0", "o0", 'wf0', 'wf1']]),
                 ("p1", [["i1", "o1", 'rf0', 'rf1']])]
        self._test_graph(graph)

    def test_wire_2parallel_1b(self):
        graph = [("p0", [["i0", "o0", 'wb0 init:1']]),
                 ("p1", [["i1", "o1", 'rb0']])]
        self._test_graph(graph)

    def test_wire_2parallel_2b(self):
        graph = [("p0", [["i0", "o0", 'wb0 init:1', 'wb1 init:1']]),
                 ("p1", [["i1", "o1", 'rb0', 'rb1']])]
        self._test_graph(graph)

    def test_wire_2parallel_1f1b(self):
        graph = [("p0", [["i0", "o0", 'wf0 init:1', 'wb1 init:1']]),
                 ("p1", [["i1", "o1", 'rf0', 'rb1']])]
        self._test_graph(graph)

    def test_triangle_ff(self):
        graph = [("p0", [["i0", "o0", 'wf0', 'rf1']]),
                 ("p1", [['rf0', 'wf1']])]
        self._test_graph(graph)

    def test_loop_1b(self):
        graph = [("p0", [["i0", "o0", "rb0", "wb0 init:1"]])]
        self._test_graph(graph)

    def test_loop_1b1f(self):
        graph = [("p0", [["i0", "o0", "rb0", "wb0 init:1", "wf1", "rf1"]])]
        self._test_graph(graph)

    def test_loop_1b_init(self):
        graph = [("p0", [["i0", "o0", "rb0", "wb0 init:1"]])]
        self._test_graph(graph)

    def test_loop_prequel(self):
        graph = [("p0", [["i0", "wf0"]]),
                 ("loop0", [["o0", "rf0", "rb1", "wb1 init:1"]])]
        self._test_graph(graph)

    def test_loop_prequelOptional(self):
        graph = [("p0", [["i0", "wf0"]]),
                 ("loop0", [["o0", "rf0 ec sw", "rb1 ec sw", "wb1 init:1"]])]
        self._test_graph(graph)

    def test_loop_2clk_1b(self):
        graph = [("p0", [["i0", "o0", "rb0", "wf1"], ["rf1", "wb0 init:1"]])]
        self._test_graph(graph)

    def test_loop_2clk_1b_init1(self):
        # [fixme] not checked because _removeValidFromReadOfBackedgeIfAlwaysContainValidData() is not executed
        # because second stage is skipable because b0 has capacity=1
        # :note: b0 has no init and must be always active, this results in a deadlock at start
        graph = [("p0", [["i0", "o0", "rb0", "wf1 init:1"], ["rf1", "wb0"]])]
        with self.assertRaises(ChannelHandshakeCycleDeadlockError):
            self._test_graph(graph)

    def test_loop_2clk_1b_wsw_init1(self):
        # :note: same problem as in test_loop_2clk_1b_init1
        graph = [("p0", [["i0", "o0", "rb0", "wf1 init:1"], ["rf1", "wb0 sw"]])]
        with self.assertRaises(ChannelHandshakeCycleDeadlockError):
            self._test_graph(graph)

    def test_loop_2clk_1b_rsw_init1(self):
        graph = [("p0", [["i0", "o0", "rb0 sw", "wf1 init:1"], ["rf1", "wb0"]])]
        self._test_graph(graph)

    def test_loop_2clk_1b_rwsw_init1(self):
        graph = [("p0", [["i0", "o0", "rb0 sw", "wf1 init:1"], ["rf1", "wb0 sw"]])]
        self._test_graph(graph)

    def test_loop_2clk_1b_init2(self):
        graph = [("p0", [["i0", "o0", "rb0", "wf1 init:2"], ["rf1", "wb0 init:1"]])]
        self._test_graph(graph)

    def test_loop_2b(self):
        graph = [("p0", [["i0", "o0", "rb0", "wb0 init:1", "rb1", "wb1 init:1"]])]
        self._test_graph(graph)

    def test_loop_2parallel(self):
        graph = [("p0", [["i0", "rb0", "wb0 init:1"]]),
                 ("p1", [["rb1", "wb1 init:1", "o0"]])
                 ]
        self._test_graph(graph)

    def test_loop_3parallel_1f(self):
        graph = [("p0", [["i0", "rb1", "wb1 init:1", "wf2"]]),
                 ("p1", [["rf2", "rb3", "wb3 init:1", "wf4"]]),
                 ("p2", [["rf4", "rb5", "wb5 init:1", "o0"]])]
        self._test_graph(graph)


if __name__ == '__main__':
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BreakHandshakeCycles_TC("test_triangle_ff")])
    suite = testLoader.loadTestsFromTestCase(BreakHandshakeCycles_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

