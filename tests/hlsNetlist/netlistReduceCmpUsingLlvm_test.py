from typing import Tuple
import unittest

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyExpr.simplifyLlvmIrExpr import runLlvmCmpOpt
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


b8_t = HBits(8)


class HlsNetlistReduceCmpUsingLlvmTC(unittest.TestCase):


    @staticmethod
    def _createNetlist() -> Tuple[HlsNetlistCtx, HlsNetlistBuilder]:
        netlist = HlsNetlistCtx(None, int(100e6), "test", {}, platform=VirtualHlsPlatform())
        return netlist, netlist.builder

    def _r(self, netlist: HlsNetlistCtx, dtype=b8_t):
        r = HlsNetNodeRead(netlist, None, dtype=dtype)
        netlist.addNode(r)
        return r._outputs[0]

    def _w(self, src: HlsNetNodeOut):
        netlist = src.obj.netlist
        w = HlsNetNodeWrite(netlist, None)
        netlist.addNode(w)
        src.connectHlsIn(w._inputs[0])
        return w


    def test_reduceEqTo0(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)

        res = b.buildAnd(
            b.buildEq(r0, b.buildConstPy(b8_t, 0)),
            b.buildEq(r0, b.buildConstPy(b8_t, 1))
        )
        w = self._w(res)

        runLlvmCmpOpt(b, [], netlist.iterAllNodes())
        resOpt = w.dependsOn[0].obj
        self.assertIsInstance(resOpt, HlsNetNodeConst)
        self.assertEqual(int(resOpt.val), 0)

    def test_reduceNe(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)

        eq = b.buildEq(r0, b.buildConstPy(b8_t, 0))
        res = b.buildAnd(
            eq,
            b.buildNe(r0, b.buildConstPy(b8_t, 1))
        )
        w = self._w(res)

        runLlvmCmpOpt(b, [], netlist.iterAllNodes())
        resOpt = w.dependsOn[0].obj
        self.assertIs(resOpt, eq.obj)


    def test_reduceRangesToEq(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)

        e0 = b.buildOp(HwtOps.ULE, None, BIT, r0, b.buildConstPy(b8_t, 10))
        e1 = b.buildOp(HwtOps.UGE, None, BIT, r0, b.buildConstPy(b8_t, 10))
        res = b.buildAnd(
            e0,
            e1,
        )
        w = self._w(res)

        runLlvmCmpOpt(b, [], netlist.iterAllNodes())
        resOpt = w.dependsOn[0].obj
        self.assertIsInstance(resOpt, HlsNetNodeOperator)
        self.assertEqual(resOpt.operator, HwtOps.EQ)

        o0, o1 = resOpt.dependsOn
        self.assertIs(o0, r0)

        self.assertIsInstance(o1.obj, HlsNetNodeConst)
        self.assertEqual(int(o1.obj.val), 10)

    def test_reduceLtGtTo0(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)

        e0 = b.buildOp(HwtOps.ULT, None, BIT, r0, b.buildConstPy(b8_t, 10))
        e1 = b.buildOp(HwtOps.UGT, None, BIT, r0, b.buildConstPy(b8_t, 10))
        res = b.buildAnd(
            e0,
            e1,
        )
        w = self._w(res)
        
        runLlvmCmpOpt(b, [], netlist.iterAllNodes())
        resOpt = w.dependsOn[0].obj
        self.assertIsInstance(resOpt, HlsNetNodeConst)
        self.assertEqual(int(resOpt.val), 0)

    def test_reduceNeLtToLt(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)

        e0 = b.buildOp(HwtOps.ULT, None, BIT, r0, b.buildConstPy(b8_t, 10))
        e1 = b.buildNe(r0, b.buildConstPy(b8_t, 15))
        res = b.buildAnd(
            e0,
            e1,
        )
        w = self._w(res)

        runLlvmCmpOpt(b, [], netlist.iterAllNodes())
        resOpt = w.dependsOn[0]
        self.assertIs(resOpt, e0)

    def test_reduceNeLtToNe(self):
        netlist, b = self._createNetlist()
        r0 = self._r(netlist)

        e0 = b.buildOp(HwtOps.ULE, None, BIT, r0, b.buildConstPy(b8_t, 255))
        c15 = b.buildConstPy(b8_t, 15)
        e1 = b.buildNe(r0, c15)
        res = b.buildAnd(
            e0,
            e1,
        )
        w = self._w(res)
        
        runLlvmCmpOpt(b, [], netlist.iterAllNodes())
        resOpt = w.dependsOn[0]
        self.assertIs(resOpt, b.buildNot(b.buildEq(r0, c15)))

if __name__ == '__main__':

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistReduceCmpUsingLlvmTC("test_ReadNonBlockingHwModule")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistReduceCmpUsingLlvmTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
