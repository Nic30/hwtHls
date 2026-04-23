#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from random import Random
import unittest

from hwt.hdl.types.defs import BIT
from hwt.pyUtils.arrayQuery import balanced_reduce
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.techmap.hlsNetlistToCppTranslator import HlsNetlistToCppTranslator
from hwtHls.netlist.techmap.techmap import HlsNetNode as HlsNetNodeCpp, \
    FlowmapWorker, scheduleLutAlap
from hwtHls.netlist.translation.dumpNodesLutDot import HwtHlsNetlistLutToGraphviz
from tests.hlsNetlist.cmpToSubstractMsbCheck_test import AbstractHlsNetlistTC
from tests.hlsNetlist.utilsRandomDag import hlsNetlistGenerateRandomDag
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class LutMappingTC(AbstractHlsNetlistTC):

    def runFlowmapWorker(self, nodes: SetList[HlsNetNode],
                         normalizedClkPeriod: SchedTime=100, schedFFSetupTime: SchedTime=10, maxLutInputs=3) \
            ->tuple[HlsNetlistToCppTranslator, FlowmapWorker, dict[HlsNetNodeCpp, HlsNetNode]]:
        tr = HlsNetlistToCppTranslator(normalizedClkPeriod, schedFFSetupTime)
        inputs: SetList[HlsNetNode] = SetList()
        outputs: SetList[HlsNetNode] = SetList()
        for n in nodes:
            if isinstance(n, HlsNetNodeRead):
                inputs.append(n)
            elif isinstance(n, HlsNetNodeWrite):
                outputs.append(n)

        tr.translate(nodes, inputs, outputs)

        fmw = FlowmapWorker([tr.nodeMap[n] for n in nodes],
                            [tr.nodeMap[n] for n in inputs],
                            [tr.nodeMap[n] for n in outputs],
                            order=maxLutInputs)
        fmw.label_nodes()
        fmw.map_luts()
        cppToPy: dict[HlsNetNodeCpp, HlsNetNode] = {tr.nodeMap[n]: n for n in tr.nodeOrdered}
        return tr, fmw, cppToPy

    def printLuts(self, fmw, cppToPy):
        for lut in fmw.lut_nodes:
            print(lut)
            for node in fmw.lut_gates[lut]:
                nodeCpp = cppToPy[node]
                if nodeCpp.scheduledZero is not None:
                    print("   ", nodeCpp.scheduledZero, node, nodeCpp)
                else:
                    print("   ", node, nodeCpp)

    def test_1Lut_1and(self):
        netlist = self.getTestNetlist()
        b = netlist.getHlsNetlistBuilder()

        i0, i1 = self.generateTestNetlistInputsFromCnt(netlist, 2, BIT)
        _o0 = b.buildAnd(i0, i1)

        o0, = self.generateTestNetlistOutputs(netlist, [_o0, ])
        tr, fmw, cppToPy = self.runFlowmapWorker(SetList(netlist.subNodes))

        self.assertEqual(fmw.lut_nodes.size(), 1)
        # self.printLuts(fmw, cppToPy)

        # toGw = HwtHlsNetlistToGraphviz("test", )

        # toGw.

        # if fmw.relax:
        #    # log("\n");
        #    # log("Optimizing area.\n");
        #    fmw.optimize_area(depth, fmw.optarea);

        # log("\n");
        # log("Packing cells.\n");
        # fmw.pack_cells(fmw.minlut);

    def test_1Lut_2and(self):
        netlist = self.getTestNetlist()
        b = netlist.getHlsNetlistBuilder()

        i0, i1, i2 = self.generateTestNetlistInputsFromCnt(netlist, 3, BIT)
        _o0 = b.buildAnd(i0, i1)
        _o1 = b.buildAnd(_o0, i2)

        o0 = self.generateTestNetlistOutputs(netlist, [_o1, ])
        tr, fmw, cppToPy = self.runFlowmapWorker(SetList(netlist.subNodes))

        self.assertEqual(fmw.lut_nodes.size(), 1)
        # self.printLuts(fmw, cppToPy)

    def test_4Lut_8inputAndTree(self):
        netlist = self.getTestNetlist()
        b = netlist.getHlsNetlistBuilder()

        inputs = self.generateTestNetlistInputsFromCnt(netlist, 8, BIT)
        _o0 = balanced_reduce(inputs, b.buildAnd)

        o0w, = self.generateTestNetlistOutputs(netlist, [_o0])
        tr, fmw, cppToPy = self.runFlowmapWorker(SetList(netlist.subNodes), maxLutInputs=4)

        self.assertEqual(fmw.lut_nodes.size(), 3)
        # self.printLuts(fmw, cppToPy)

    def test_4Lut_8inputAndTree_2outputs(self):
        netlist = self.getTestNetlist()
        b = netlist.getHlsNetlistBuilder()

        inputs = self.generateTestNetlistInputsFromCnt(netlist, 8, BIT)
        _o0 = balanced_reduce(inputs, b.buildAnd)
        _o1 = balanced_reduce(inputs[:-1], b.buildAnd)

        owNodes = self.generateTestNetlistOutputs(netlist, [_o0, _o1])

        inputNodes = set(i.obj for i in inputs)
        tr, fmw, cppToPy = self.runFlowmapWorker(SetList(netlist.subNodes),
                                                         maxLutInputs=4)

        # self.printLuts(fmw, cppToPy)
        self.assertEqual(fmw.lut_nodes.size(), 5)

    def test_3in_3out(self):
        netlist = self.getTestNetlist()
        b = netlist.getHlsNetlistBuilder()

        i = self.generateTestNetlistInputsFromCnt(netlist, 3, BIT)
        i0n = b.buildNot(i[0], opt=False)
        o0 = b.buildOr(i0n, i[1], opt=False)
        o1 = i0n
        o2 = b.buildOr(i0n, i[2], opt=False)
        owNodes = self.generateTestNetlistOutputs(netlist, [o0, o1, o2])
        tr, fmw, cppToPy = self.runFlowmapWorker(SetList(netlist.subNodes),
                                                         maxLutInputs=4)
        # self.printLuts(fmw, cppToPy)
        self.assertEqual(fmw.lut_nodes.size(), 3)

    def test_32Lut_32inputRand_0(self):
        netlist = self.getTestNetlist()
        b = netlist.getHlsNetlistBuilder()
        random = Random(0)
        inputs = self.generateTestNetlistInputsFromCnt(netlist, 16, BIT)
        outputs = hlsNetlistGenerateRandomDag(random, 64, inputs, b, depthFactor=1.2, avoidSameInputs=True)
        owNodes = self.generateTestNetlistOutputs(netlist, outputs)
        for ow in owNodes:
            ow.resolveRealization()
            ow._setScheduleZeroTimeSingleClock(80)

        tr, fmw, cppToPy = self.runFlowmapWorker(SetList(netlist.subNodes),
                                                         maxLutInputs=4)
        #self.printLuts(fmw, cppToPy)
        self.assertEqual(fmw.lut_nodes.size(), 57)

        # toGraphviz = HwtHlsNetlistLutToGraphviz("test", fmw.lut_nodes, fmw.lut_gates, cppToPy)
        # toGraphviz.construct()
        # with open("tmp/test_32Lut_64inputRand_0.dot", "w") as out:
        #     out.write(toGraphviz.dumps())
        # 
        # lutDelay = 40
        # endOfLastClk = 100
        # scheduleLutAlap(fmw, lutDelay, endOfLastClk)
        # toGraphviz = HwtHlsNetlistLutToGraphviz("test", fmw.lut_nodes, fmw.lut_gates, cppToPy)
        # toGraphviz.construct()
        # with open("tmp/test_32Lut_64inputRand_0_sched.dot", "w") as out:
        #    out.write(toGraphviz.dumps())


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(LutMappingTC)
    # suite = unittest.TestSuite([LutMappingTC("test_3in_3out")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
