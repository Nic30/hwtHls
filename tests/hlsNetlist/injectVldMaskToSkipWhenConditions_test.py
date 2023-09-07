#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from io import StringIO
import os
import unittest

from hwt.hdl.types.defs import BIT
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.orderable import HVoidData
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.translation.dumpNodesDot import HlsNetlistPassDumpNodesDot
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.examples.base_serialization_TC import BaseSerializationTC
from hwtLib.types.ctypes import uint8_t
from hwt.hdl.types.bits import Bits


class HlsNetlistPassInjectVldMaskToSkipWhenConditionsTC(BaseSerializationTC):
    __FILE__ = __file__

    @staticmethod
    def _createNetlist():
        netlist = HlsNetlistCtx(None, int(100e6), "test", platform=VirtualHlsPlatform())
        b = HlsNetlistBuilder(netlist)
        netlist._setBuilder(b)
        return netlist, b

    def assert_netlist_same_as_file(self, netlist:HlsNetlistCtx, name: str):
        nodesDot = StringIO()
        HlsNetlistPassDumpNodesDot(lambda name: (nodesDot, False)).apply(None, netlist)
        file_name = os.path.join("data", name + ".dot")
        self.assert_same_as_file(nodesDot.getvalue(), file_name)

    def assert_netlist_same_as_expected_file(self, netlist:HlsNetlistCtx):
        self.assert_netlist_same_as_file(netlist, self.getTestName())

    def test_linear0(self):
        # v = r.read()
        # if v != 0:
        #    w.write(v)
        netlist, b = self._createNetlist()
        b: HlsNetlistBuilder
        r = HlsNetNodeRead(netlist, None, dtype=uint8_t)
        w = HlsNetNodeWrite(netlist, None, None)
        netlist.nodes.extend((r, w))
        rEq0 = b.buildEq(r._outputs[0], b.buildConstPy(uint8_t, 0))
        link_hls_nodes(r._outputs[0], w._inputs[0])
        w.addControlSerialSkipWhen(rEq0)
        # link_hls_nodes(rEq0, w.skipWhen)
        HlsNetlistPassInjectVldMaskToSkipWhenConditions().apply(None, netlist)
        self.assert_netlist_same_as_expected_file(netlist)

    def test_mux(self):
        netlist, b = self._createNetlist()
        b: HlsNetlistBuilder

        r0 = HlsNetNodeRead(netlist, None, dtype=HVoidData)
        r1 = HlsNetNodeRead(netlist, None, dtype=uint8_t)
        r2 = HlsNetNodeRead(netlist, None, dtype=uint8_t)

        mux = b.buildMux(uint8_t, (r1._outputs[0], r0.getValidNB(), r2._outputs[0]))
        muxEq0 = b.buildEq(mux, b.buildConstPy(uint8_t, 0))

        w = HlsNetNodeWrite(netlist, None, None)
        w.addControlSerialSkipWhen(muxEq0)

        netlist.nodes.extend((r0, r1, r2, w))
        HlsNetlistPassInjectVldMaskToSkipWhenConditions().apply(None, netlist)
        self.assert_netlist_same_as_expected_file(netlist)

    def test_eq_not(self):
        netlist, b = self._createNetlist()
        b: HlsNetlistBuilder

        u8 = Bits(8)
        r0 = HlsNetNodeRead(netlist, None, dtype=u8)

        w = HlsNetNodeWrite(netlist, None, None)

        en = b.buildEq(r0._outputs[0], b.buildConstPy(u8, 11))
        w.addControlSerialExtraCond(en)
        # :note: extraCond and skipWhen should be 9 if input data was not valid
        w.addControlSerialSkipWhen(b.buildNot(en))

        netlist.nodes.extend((r0, w))
        HlsNetlistPassInjectVldMaskToSkipWhenConditions().apply(None, netlist)
        self.assert_netlist_same_as_expected_file(netlist)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistPassInjectVldMaskToSkipWhenConditionsTC("test_linear0")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistPassInjectVldMaskToSkipWhenConditionsTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
