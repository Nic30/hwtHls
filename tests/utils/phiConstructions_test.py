#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.unit import Unit
from hwt.synthesizer.utils import to_rtl_str
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.ast.statements import HlsStmWhile, HlsStmIf
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.translation.toGraphwiz import SsaPassDumpToDot
from hwtLib.types.ctypes import uint8_t
from tests.baseSsaTest import TestFinishedSuccessfuly


class PhiConstruction_TC(unittest.TestCase):

    def testAstWhileCondWrite(self):
        ssaCtx = SsaContext()
        toSsa = HlsAstToSsa(ssaCtx, "entry", None, None)
        toSsa._onAllPredecsKnown(toSsa.start)
        netlist = RtlNetlist()

        # i = 0
        # while True:
        #    if i < 3:
        #       i += 1
        i = netlist.sig("i", uint8_t)
        toSsa.visit_CodeBlock_list(toSsa.start, [
            i(0),
            HlsStmWhile(None, BIT.from_py(1),
                               [
                                    HlsStmIf(None, i < 3,
                                                    [
                                                        i(i + 1)
                                                    ]
                                    )
                ]
            ),
        ])
        # asserts that phi for i has correct format
        whileHeaderBlock = toSsa.start.successors.targets[0][1]
        self.assertEqual(len(whileHeaderBlock.predecessors), 2)
        self.assertEqual(len(whileHeaderBlock.phis[0].operands), 2)

    def testPyBytecodeWhileCondWrite(self):

        class U0(Unit):

            def _declr(self) -> None:
                addClkRstn(self)
                self.o = VectSignal(8, signed=True)._m()

            def _impl(self):
                hls = HlsScope(self)

                @hlsBytecode
                def main():
                    i = uint8_t.from_py(0)
                    while BIT.from_py(1):
                        hls.write(i, self.o)
                        if i < 3:
                            i += 1

                hls.addThread(HlsThreadFromPy(hls, main))
                hls.compile()

        class TestPlatform(VirtualHlsPlatform):

            def runSsaPasses(self, hls:"HlsScope", toSsa:HlsAstToSsa):
                SsaPassDumpToDot(hls, outputFileGetter("tmp", "0.dot"), extractPipeline=False).runOnSsaModule(toSsa)
                SsaPassConsystencyCheck(hls).runOnSsaModule(toSsa)
                raise TestFinishedSuccessfuly()

        try:
            to_rtl_str(U0(), target_platform=TestPlatform())
        except TestFinishedSuccessfuly:
            pass


if __name__ == '__main__':
    unittest.main()
