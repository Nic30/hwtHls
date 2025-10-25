#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.operatorDefs import HwtOps
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.ops import OP_INDEX_CONST
from hwtHls.netlist.transformation.simplifyExpr.simplifyMul import netlistReduceMulConst
from tests.hlsNetlist.netlistReduceCmpUsingLlvm_test import b8_t
from tests.hlsNetlist.netlistReduceMux_test import HlsNetlistReduceMuxTC
from tests.hlsNetlist.utils import BaseHlsNetlistReduceTC, exprToTestExprTy


class HlsNetlistReduceMulTC(BaseHlsNetlistReduceTC):

    def _r(self, netlist: HlsNetlistCtx, dtype=b8_t):
        return HlsNetlistReduceMuxTC._r(self, netlist, dtype)

    def test_netlistReduceMulConst_mul5(self):
        netlist, b = self._createNetlist()
        v0 = self._r(netlist)

        res = b.buildOp(HwtOps.MUL, None, b8_t,
            v0,
            b.buildConstPy(b8_t, 5),
        )
        write = self._w(res)
        netlistReduceMulConst(res.obj, [])

        self.assertEqual(
            exprToTestExprTy(write.dependsOn[0]),
            (HwtOps.ADD, v0, (HwtOps.CONCAT, 0, (HwtOps.INDEX, v0, slice(6, 0, -1))))
        )

    def test_netlistReduceMulConst_mul7(self):
        netlist, b = self._createNetlist()
        v0 = self._r(netlist)

        res = b.buildOp(HwtOps.MUL, None, b8_t,
            v0,
            b.buildConstPy(b8_t, 7),
        )
        write = self._w(res)
        netlistReduceMulConst(res.obj, [])

        self.assertEqual(
            exprToTestExprTy(write.dependsOn[0]),
           (HwtOps.ADD, (HwtOps.ADD, v0, (HwtOps.CONCAT, 0, (OP_INDEX_CONST, v0, slice(7, 0, -1)))),
                   (HwtOps.CONCAT, 0, (OP_INDEX_CONST, v0, slice(6, 0, -1))))

        )


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistReduceMulTC("test_netlistReduceMulConst")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistReduceMulTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
