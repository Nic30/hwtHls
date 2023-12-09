#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, parseMIR
from tests.baseSsaTest import BaseSsaTC


class EarlyIfConverter_TC(BaseSsaTC):
    __FILE__ = __file__

    def _test_ll(self):
        nameOfMain = self.getTestName()
        ctx = LlvmCompilationBundle(nameOfMain)

        inputFileName = Path(self.__FILE__).expanduser().resolve().parent / "dataIn" / (nameOfMain + ".in.mir.ll")
        with open(inputFileName) as f:
            parseMIR(f.read(), nameOfMain, ctx)
        assert ctx.module is not None

        f = ctx.module.getFunction(ctx.strCtx.addStringRef(nameOfMain))
        assert f is not None, (inputFileName, nameOfMain)
        ctx.main = f
        ctx._testEarlyIfConverter()
        MMI = ctx.getMachineModuleInfo()
        mf = MMI.getMachineFunction(f)
        assert mf is not None
        self.assert_same_as_file(str(mf), os.path.join("data", self.__class__.__name__ + "." + nameOfMain + ".out.mir.ll"))

    def test_mergeExitBlockOfParentLoop(self):
        self._test_ll()

    #def test_branchWithOptionalStore(self):
    #    raise NotImplementedError()
    #
    #def test_2branchesWithSameStore(self):
    #    raise NotImplementedError()


if __name__ == "__main__":
    # from hwt.synthesizer.utils import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # u = SliceBreak3()
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([EarlyIfConverter_TC('test_mergeExitBlockOfParentLoop')])
    suite = testLoader.loadTestsFromTestCase(EarlyIfConverter_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
