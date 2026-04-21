import unittest

from hwt.hdl.operatorDefs import HOperatorDef, HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.analysis.hlsNetlistSimulator import HlsNetlistSimulator
from hwtHls.netlist.transformation.simplifyExpr.cmpToSubstractMsbCheck import netlistReduceCmpToSubstractMsbCheck
from pyMathBitPrecise.bit_utils import to_signed, to_unsigned
from tests.hlsNetlist.abstractHlsNetlistTC import AbstractHlsNetlistTC


class HlsNetlistReduceCmpToSubstractMsbCheckTC(AbstractHlsNetlistTC):
    T = HBits(3)
    UMAX = T.get_max_value()
    UMIN = T.get_min_value()
    SMAX = to_unsigned(HBits(3, signed=True).get_max_value(), 3)
    SMIN = to_unsigned(HBits(3, signed=True).get_min_value(), 3)

    def _test(self, predicate: HOperatorDef):
        netlist = self.getTestNetlist()
        t = self.T
        a, b = self.generateTestNetlistInputsFromCnt(netlist, 2, t)
        builder = netlist.getHlsNetlistBuilder()
        res = builder.buildOp(predicate, None, BIT, a, b)

        o, = self.generateTestNetlistOutputs(netlist, [res, ])
        worklist = SetList()
        netlistReduceCmpToSubstractMsbCheck(res.obj, worklist)

        newO = o.dependsOn[0]
        self.assertIsNot(newO, res)
        self.assertTrue(res.obj._isMarkedRemoved)
        for _a in range(1 << 3):
            for _b in range(1 << 3):
                # print(_a, _b)
                aConst = t.from_py(_a)
                bConst = t.from_py(_b)
                ref = bool(predicate._evalFn(aConst, bConst))
                sim = HlsNetlistSimulator(netlist, (iter([]), iter([]), []))
                sim.state[a] = aConst
                sim.state[b] = bConst
                sim.evalExpr()
                res = bool(sim.getStateOf(newO))
                self.assertEqual(res, ref, (_a, _b, to_signed(_a, 3), to_signed(_b, 3)))

    def _test_rhs_const(self, predicate: HOperatorDef, RHS: int):
        netlist = self.getTestNetlist()
        t = self.T
        a, = self.generateTestNetlistInputsFromCnt(netlist, 1, t)
        builder = netlist.getHlsNetlistBuilder()
        bConst = t.from_py(RHS)
        b = builder.buildConst(bConst)
        res = builder.buildOp(predicate, None, BIT, a, b)

        o, = self.generateTestNetlistOutputs(netlist, [res, ])
        worklist = SetList()
        netlistReduceCmpToSubstractMsbCheck(res.obj, worklist)

        newO = o.dependsOn[0]
        self.assertIsNot(newO, res)
        self.assertTrue(res.obj._isMarkedRemoved)
        for _a in range(1 << 3):
            # print(_a, _b)
            aConst = t.from_py(_a)
            ref = bool(predicate._evalFn(aConst, bConst))
            sim = HlsNetlistSimulator(netlist, (iter([]), []))
            sim.state[a] = aConst
            sim.evalExpr()
            res = bool(sim.getStateOf(newO))
            self.assertEqual(res, ref, (_a, RHS, to_signed(_a, 3), to_signed(RHS, 3)))

    def test_SLT(self):
        self._test(HwtOps.SLT)

    def test_SLT_rhs_umin(self):
        self._test_rhs_const(HwtOps.SLT, self.UMIN)

    def test_SLT_rhs_umax(self):
        self._test_rhs_const(HwtOps.SLT, self.UMAX)

    def test_SLT_rhs_smin(self):
        self._test_rhs_const(HwtOps.SLT, self.SMIN)

    def test_SLT_rhs_smax(self):
        self._test_rhs_const(HwtOps.SLT, self.SMAX)

    def test_SGT(self):
        self._test(HwtOps.SGT)

    def test_SGT_rhs_umin(self):
        self._test_rhs_const(HwtOps.SGT, self.UMIN)

    def test_SGT_rhs_umax(self):
        self._test_rhs_const(HwtOps.SGT, self.UMAX)

    def test_SGT_rhs_smin(self):
        self._test_rhs_const(HwtOps.SGT, self.SMIN)

    def test_SGT_rhs_smax(self):
        self._test_rhs_const(HwtOps.SGT, self.SMAX)

    def test_SLE(self):
        self._test(HwtOps.SLE)

    def test_SLE_rhs_umin(self):
        self._test_rhs_const(HwtOps.SLE, self.UMIN)

    def test_SLE_rhs_umax(self):
        self._test_rhs_const(HwtOps.SLE, self.UMAX)

    def test_SLE_rhs_smin(self):
        self._test_rhs_const(HwtOps.SLE, self.SMIN)

    def test_SLE_rhs_smax(self):
        self._test_rhs_const(HwtOps.SLE, self.SMAX)

    def test_SGE(self):
        self._test(HwtOps.SGE)

    def test_SGE_rhs_umin(self):
        self._test_rhs_const(HwtOps.SGE, self.UMIN)

    def test_SGE_rhs_umax(self):
        self._test_rhs_const(HwtOps.SGE, self.UMAX)

    def test_SGE_rhs_smin(self):
        self._test_rhs_const(HwtOps.SGE, self.SMIN)

    def test_SGE_rhs_smax(self):
        self._test_rhs_const(HwtOps.SGE, self.SMAX)

    def test_ULT(self):
        self._test(HwtOps.ULT)

    def test_ULT_rhs_umin(self):
        self._test_rhs_const(HwtOps.ULT, self.UMIN)

    def test_ULT_rhs_umax(self):
        self._test_rhs_const(HwtOps.ULT, self.UMAX)

    def test_ULT_rhs_smin(self):
        self._test_rhs_const(HwtOps.ULT, self.SMIN)

    def test_ULT_rhs_smax(self):
        self._test_rhs_const(HwtOps.ULT, self.SMAX)

    def test_UGT(self):
        self._test(HwtOps.UGT)

    def test_UGT_rhs_umin(self):
        self._test_rhs_const(HwtOps.UGT, self.UMIN)

    def test_UGT_rhs_umax(self):
        self._test_rhs_const(HwtOps.UGT, self.UMAX)

    def test_UGT_rhs_smin(self):
        self._test_rhs_const(HwtOps.UGT, self.SMIN)

    def test_UGT_rhs_smax(self):
        self._test_rhs_const(HwtOps.UGT, self.SMAX)

    def test_ULE(self):
        self._test(HwtOps.ULE)

    def test_ULE_rhs_umin(self):
        self._test_rhs_const(HwtOps.ULE, self.UMIN)

    def test_ULE_rhs_umax(self):
        self._test_rhs_const(HwtOps.ULE, self.UMAX)

    def test_ULE_rhs_smin(self):
        self._test_rhs_const(HwtOps.ULE, self.SMIN)

    def test_ULE_rhs_smax(self):
        self._test_rhs_const(HwtOps.ULE, self.SMAX)

    def test_UGE(self):
        self._test(HwtOps.UGE)

    def test_UGE_rhs_umin(self):
        self._test_rhs_const(HwtOps.UGE, self.UMIN)

    def test_UGE_rhs_umax(self):
        self._test_rhs_const(HwtOps.UGE, self.UMAX)

    def test_UGE_rhs_smin(self):
        self._test_rhs_const(HwtOps.UGE, self.SMIN)

    def test_UGE_rhs_smax(self):
        self._test_rhs_const(HwtOps.UGE, self.SMAX)


if __name__ == '__main__':

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistReduceCmpToSubstractMsbCheckTC("test_ULT")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistReduceCmpToSubstractMsbCheckTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
