#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest

from hwt.hdl.operatorDefs import HwtOps
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.transformation.simplifyExpr.simplifyBitwise import netlistReduceAndOrXor
from tests.hlsNetlist.netlistReduceCmpUsingLlvm_test import b8_t
from tests.hlsNetlist.netlistReduceMux_test import HlsNetlistReduceMuxTC
from tests.hlsNetlist.utils import BaseHlsNetlistReduceTC, exprToTestExprTy


class HlsNetlistReduceBitwiseTC(BaseHlsNetlistReduceTC):

    def _r(self, netlist: HlsNetlistCtx, dtype=b8_t):
        return HlsNetlistReduceMuxTC._r(self, netlist, dtype)

    def test_netlistReduceMulConst_netlistReduceAndOrXor(self, builderOpt=True):
        netlist, b = self._createNetlist()
        B = self._r(netlist)
        C = self._r(netlist)
        D = self._r(netlist)

        # C ^ (B | ~D)
        if builderOpt:
            op = b.buildOpWithOpt
        else:
            op = b.buildOp
        res = op(HwtOps.XOR, None, b8_t,
            C,
            op(HwtOps.OR, None, b8_t, B, b.buildNot(D)),
        )
        write = self._w(res)
        netlistReduceAndOrXor(res.obj, [])

        self.assertEqual(
            exprToTestExprTy(write.dependsOn[0]),
            (HwtOps.XOR, C, (HwtOps.OR, B, (HwtOps.NOT, D)))
        )

    def test_netlistReduceMulConst_netlistReduceAndOrXor_noBuilderOpt(self):
        self.test_netlistReduceMulConst_netlistReduceAndOrXor(builderOpt=False)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistReduceBitwiseTC("test_netlistReduceMulConst")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistReduceBitwiseTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
