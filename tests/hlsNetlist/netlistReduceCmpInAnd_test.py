#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Tuple
import unittest

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.defs import BIT
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import link_hls_nodes, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifyExpr.cmpInAnd import netlistReduceCmpInAnd
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.types.ctypes import uint8_t


class HlsNetlistReduceCmpInAndTC(unittest.TestCase):

    @staticmethod
    def _createNetlist() -> Tuple[HlsNetlistCtx, HlsNetlistBuilder]:
        netlist = HlsNetlistCtx(None, int(100e6), "test", platform=VirtualHlsPlatform())
        b = HlsNetlistBuilder(netlist)
        netlist._setBuilder(b)
        return netlist, b

    def _r(self, netlist: HlsNetlistCtx):
        r = HlsNetNodeRead(netlist, None, dtype=uint8_t)
        netlist.inputs.append(r)
        return r._outputs[0]

    def _w(self, src: HlsNetNodeOut):
        netlist = src.obj.netlist
        w = HlsNetNodeWrite(netlist, None, None)
        netlist.outputs.append(w)
        link_hls_nodes(src, w._inputs[0])
        return w

    def test_reduceEqTo0(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)
        
        res = b.buildAnd(
            b.buildEq(r0, b.buildConstPy(uint8_t, 0)),
            b.buildEq(r0, b.buildConstPy(uint8_t, 1))
        )
        w = self._w(res)
        
        netlistReduceCmpInAnd(res.obj, [], set())
        resOpt = w.dependsOn[0].obj
        self.assertIsInstance(resOpt, HlsNetNodeConst)
        self.assertEqual(int(resOpt.val), 0)

    def test_reduceNe(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)
        
        eq = b.buildEq(r0, b.buildConstPy(uint8_t, 0))
        res = b.buildAnd(
            eq,
            b.buildNe(r0, b.buildConstPy(uint8_t, 1))
        )
        w = self._w(res)
        
        netlistReduceCmpInAnd(res.obj, [], set())
        resOpt = w.dependsOn[0].obj
        self.assertIs(resOpt, eq.obj)

    def test_reduceRangesToEq(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)
        
        e0 = b.buildOp(AllOps.LE, BIT, r0, b.buildConstPy(uint8_t, 10))
        e1 = b.buildOp(AllOps.GE, BIT, r0, b.buildConstPy(uint8_t, 10))
        res = b.buildAnd(
            e0,
            e1,
        )
        w = self._w(res)
        
        netlistReduceCmpInAnd(res.obj, [], set())
        resOpt = w.dependsOn[0].obj
        self.assertIsInstance(resOpt, HlsNetNodeOperator)
        self.assertEqual(resOpt.operator, AllOps.EQ)
        
        o0, o1 = resOpt.dependsOn
        self.assertIs(o0, r0)

        self.assertIsInstance(o1.obj, HlsNetNodeConst)
        self.assertEqual(int(o1.obj.val), 10)

    def test_reduceLtGtTo0(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)
        
        e0 = b.buildOp(AllOps.LT, BIT, r0, b.buildConstPy(uint8_t, 10))
        e1 = b.buildOp(AllOps.GT, BIT, r0, b.buildConstPy(uint8_t, 10))
        res = b.buildAnd(
            e0,
            e1,
        )
        w = self._w(res)
        
        netlistReduceCmpInAnd(res.obj, [], set())
        resOpt = w.dependsOn[0].obj
        self.assertIsInstance(resOpt, HlsNetNodeConst)
        self.assertEqual(int(resOpt.val), 0)
    
    def test_reduceNeLtToLt(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)
        
        e0 = b.buildOp(AllOps.LT, BIT, r0, b.buildConstPy(uint8_t, 10))
        e1 = b.buildNe(r0, b.buildConstPy(uint8_t, 15))
        res = b.buildAnd(
            e0,
            e1,
        )
        w = self._w(res)
        
        netlistReduceCmpInAnd(res.obj, [], set())
        resOpt = w.dependsOn[0]
        self.assertIs(resOpt, e0)

    def test_reduceNeLtToNe(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)
        
        e0 = b.buildOp(AllOps.LE, BIT, r0, b.buildConstPy(uint8_t, 255))
        c15 = b.buildConstPy(uint8_t, 15)
        e1 = b.buildNe(r0, c15)
        res = b.buildAnd(
            e0,
            e1,
        )
        w = self._w(res)
        
        netlistReduceCmpInAnd(res.obj, [], set())
        resOpt = w.dependsOn[0]
        self.assertIs(resOpt, b.buildNot(b.buildEq(r0, c15)))
    

if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistReduceCmpInAndTC("test_reduceNeLtToNe")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistReduceCmpInAndTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
