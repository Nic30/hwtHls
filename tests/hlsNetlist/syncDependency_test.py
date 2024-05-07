#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.types.ctypes import uint8_t


class SyncDependencyTC(unittest.TestCase):

    @staticmethod
    def _createNetlist():
        netlist = HlsNetlistCtx(None, int(100e6), "test", platform=VirtualHlsPlatform())
        b = HlsNetlistBuilder(netlist)
        netlist._setBuilder(b)
        return netlist, b

    def test_linear0(self):
        # r->w
        netlist, _ = self._createNetlist()
        r = HlsNetNodeRead(netlist, None, dtype=uint8_t)
        w = HlsNetNodeWrite(netlist, None)
        link_hls_nodes(r._outputs[0], w._inputs[0])
        netlist.nodes.extend((r, w))
        reachDb = HlsNetlistAnalysisPassReachability()
        reachDb.runOnHlsNetlist(netlist)
        self.assertDictEqual(reachDb._dataSuccessors, {r: {r._outputs[0], w._inputs[0], w},
                                                       r._outputs[0]: {w._inputs[0], w},
                                                       w._inputs[0]: {w, },
                                                       w: set()})

    def test_linear1(self):
        # r->sync->w
        netlist, _ = self._createNetlist()
        r = HlsNetNodeRead(netlist, None, dtype=uint8_t)
        sync = HlsNetNodeExplicitSync(netlist, uint8_t)
        w = HlsNetNodeWrite(netlist, None)
        link_hls_nodes(r._outputs[0], sync._inputs[0])
        link_hls_nodes(sync._outputs[0], w._inputs[0])
        netlist.nodes.extend((r, sync, w))
        reachDb = HlsNetlistAnalysisPassReachability()
        reachDb.runOnHlsNetlist(netlist)
        depSeq = [r, r._outputs[0], sync._inputs[0], sync, sync._outputs[0], w._inputs[0], w]
        ref = {}
        for i, obj in enumerate(depSeq):
            ref[obj] = set(depSeq[i + 1:])
            
        self.assertDictEqual(reachDb._dataSuccessors, ref)
    
    def test_join(self):
        # r0 and r1 -> w
        netlist, b = self._createNetlist()
        r0 = HlsNetNodeRead(netlist, None, dtype=uint8_t)
        r1 = HlsNetNodeRead(netlist, None, dtype=uint8_t)
        w = HlsNetNodeWrite(netlist, None)
        r0AndR1 = b.buildAnd(r0._outputs[0], r1._outputs[0])
        link_hls_nodes(r0AndR1, w._inputs[0])
        netlist.nodes.extend((r0, r1, w))
        reachDb = HlsNetlistAnalysisPassReachability()
        reachDb.runOnHlsNetlist(netlist)
        
        depSeq0 = [r0, r0._outputs[0], r0AndR1.obj._inputs[0], r0AndR1.obj, r0AndR1.obj._outputs[0], w._inputs[0], w]
        depSeq1 = [r1, r1._outputs[0], r0AndR1.obj._inputs[1], r0AndR1.obj, r0AndR1.obj._outputs[0], w._inputs[0], w]
        ref = {}
        for depSeq in (depSeq0, depSeq1):
            for i, obj in enumerate(depSeq):
                ref[obj] = set(depSeq[i + 1:])
            
        self.assertDictEqual(reachDb._dataSuccessors, ref)

        
if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SyncDependencyTC("test_linear0")])
    suite = testLoader.loadTestsFromTestCase(SyncDependencyTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
