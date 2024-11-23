#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.defs import BIT
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyExpr.simplifyAbc import runAbcControlpathOpt
from hwtHls.netlist.transformation.simplifyExpr.simplifyMux import netlistReduceMux
from tests.hlsNetlist.utils import BaseHlsNetlistReduceTC


class HlsNetlistReduceMuxTC(BaseHlsNetlistReduceTC):

    def assertIsNotOf(self, res: HlsNetNodeOut, notOf: HlsNetNodeOut):
        """
        Check that resOpt = ~notOf
        """
        resObj = res.obj
        self.assertIsInstance(resObj, HlsNetNodeOperator)
        self.assertIs(resObj.operator, HwtOps.NOT)
        self.assertEqual(resObj.dependsOn[0], notOf)

    def get_0ifCElse1(self, opt=False):
        netlist, b = self._createNetlist()
        c0 = self._r(netlist)

        res = b.buildMux(BIT,
            (
                b.buildConstBit(0),
                c0,
                b.buildConstBit(1),
            ),
            opt=opt
        )
        return netlist, b, c0, res

    def test_reduce_0ifCElse1_to_notC_builder(self):
        _, _, c0, res = self.get_0ifCElse1(opt=True)
        self.assertIsNotOf(res, c0)

    def test_reduce_0ifCElse1_to_notC_netlist(self):
        _, _, c0, res = self.get_0ifCElse1()
        w = self._w(res)
        netlistReduceMux(res.obj, [])
        self.assertIsNotOf(w.dependsOn[0], c0)

    def test_reduce_0ifCElse1_to_notC_abc(self):
        netlist, b, c0, res = self.get_0ifCElse1()
        w = self._w(res)
        runAbcControlpathOpt(b, [], netlist.iterAllNodes())
        self.assertIsNotOf(w.dependsOn[0], c0)

    def get_1ifCElse0(self, opt=False):
        netlist, b = self._createNetlist()
        c0 = self._r(netlist)
        res = b.buildMux(BIT,
            (
                b.buildConstBit(1),
                c0,
                b.buildConstBit(0),
            ),
            opt=opt
        )
        return netlist, b, c0, res

    def test_reduce_1ifCElse0_to_C_builder(self):
        _, _, c0, res = self.get_1ifCElse0(opt=True)
        self.assertIs(res, c0)

    def test_reduce_1ifCElse0_to_C_netlist(self):
        _, _, c0, res = self.get_1ifCElse0(opt=False)
        w = self._w(res)

        netlistReduceMux(res.obj, [])
        resOpt = w.dependsOn[0]
        self.assertIs(resOpt, c0)

    def test_reduce_1ifCElse0_to_C_abc(self):
        netlist, b, c0, res = self.get_1ifCElse0()
        w = self._w(res)

        runAbcControlpathOpt(b, [], netlist.iterAllNodes())

        resOpt = w.dependsOn[0]
        self.assertIs(resOpt, c0)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistReduceMuxTC("test_reduce_0ifCElse1_to_not")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistReduceMuxTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
