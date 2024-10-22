#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.types.bits import HBits
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform


class SyncDependencyTC(unittest.TestCase):

    @staticmethod
    def _createNetlist():
        netlist = HlsNetlistCtx(None, int(100e6), "test", {}, platform=VirtualHlsPlatform())
        return netlist, netlist.builder

    def test_linear0(self):
        # r->w
        netlist, _ = self._createNetlist()
        r = HlsNetNodeRead(netlist, None, dtype=HBits(8))
        w = HlsNetNodeWrite(netlist, None)
        r._portDataOut.connectHlsIn(w._portSrc)
        netlist.addNodes((r, w))
        reachDb = HlsNetlistAnalysisPassReachability()
        reachDb.runOnHlsNetlist(netlist)
        self.assertDictEqual(reachDb._successors, {r: {r._portDataOut, w._portSrc, w},
                                                   r._portDataOut: {w._portSrc, w},
                                                   w._portSrc: {w, },
                                                   w: set()})

    def test_join(self):
        # r0 and r1 -> w
        netlist, b = self._createNetlist()
        r0 = HlsNetNodeRead(netlist, None, dtype=HBits(8))
        r1 = HlsNetNodeRead(netlist, None, dtype=HBits(8))
        w = HlsNetNodeWrite(netlist, None)
        r0AndR1 = b.buildAnd(r0._outputs[0], r1._outputs[0])
        r0AndR1.connectHlsIn(w._portSrc)
        netlist.addNodes((r0, r1, w))
        reachDb = HlsNetlistAnalysisPassReachability()
        reachDb.runOnHlsNetlist(netlist)

        depSeq0 = [r0, r0._outputs[0], r0AndR1.obj._inputs[0], r0AndR1.obj, r0AndR1.obj._outputs[0], w._portSrc, w]
        depSeq1 = [r1, r1._outputs[0], r0AndR1.obj._inputs[1], r0AndR1.obj, r0AndR1.obj._outputs[0], w._portSrc, w]
        ref = {}
        for depSeq in (depSeq0, depSeq1):
            for i, obj in enumerate(depSeq):
                ref[obj] = set(depSeq[i + 1:])

        self.assertDictEqual(reachDb._successors, ref)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SyncDependencyTC("test_linear0")])
    suite = testLoader.loadTestsFromTestCase(SyncDependencyTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
