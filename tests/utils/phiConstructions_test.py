import unittest

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.unit import Unit
from hwt.synthesizer.utils import to_rtl_str
from hwtHls.hlsStreamProc.statements import HlsStreamProcWhile, HlsStreamProcIf
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.transformation.runFn import SsaPassRunFn
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.translation.fromPython.fromPython import HlsStreamProcPyThread
from hwtLib.types.ctypes import uint8_t
from tests.baseSsaTest import TestFinishedSuccessfuly
from hwtHls.ssa.translation.toGraphwiz import SsaPassDumpToDot
from hwtHls.platform.fileUtils import outputFileGetter


class PhiConstruction_TC(unittest.TestCase):

    def testAstWhileCondWrite(self):
        ssaCtx = SsaContext()
        toSsa = AstToSsa(ssaCtx, "entry", None)
        toSsa._onAllPredecsKnown(toSsa.start)
        netlist = RtlNetlist()
        
        # i = 0
        # while True:
        #    if i < 3:
        #       i += 1
        i = netlist.sig("i", uint8_t)
        toSsa.visit_CodeBlock_list(toSsa.start, [
            i(0),
            HlsStreamProcWhile(None, BIT.from_py(1),
                               [
                                    HlsStreamProcIf(None, i < 3,
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
                hls = HlsStreamProc(self)

                def main():
                    i = uint8_t.from_py(0)
                    while BIT.from_py(1):
                        hls.write(i, self.o)
                        if i < 3:
                            i += 1

                hls.thread(HlsStreamProcPyThread(hls, main))
                hls.compile()
        try:
            to_rtl_str(U0(), target_platform=VirtualHlsPlatform(ssa_passes=[
                SsaPassDumpToDot(outputFileGetter("tmp", "0.dot"), extractPipeline=False),
                SsaPassConsystencyCheck(),
                SsaPassRunFn(TestFinishedSuccessfuly.raise_)
            ]))
        except TestFinishedSuccessfuly:
            pass


if __name__ == '__main__':
    unittest.main()
