#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, parseMIR, parseIR, SMDiagnostic
from tests.baseSsaTest import BaseSsaTC
from tests.llvmIr.baseLlvmIrTC import generateAndAppendHwtHlsFunctionDeclarations


class VRegIfConverter_TC(BaseSsaTC):
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
        ctx._testVRegIfConverter()
        MMI = ctx.getMachineModuleInfo()
        MF = MMI.getMachineFunction(f)
        assert MF is not None
        self.assert_same_as_file(str(MF), os.path.join("data", self.__class__.__name__ + "." + nameOfMain + ".out.mir.ll"))

    def _test_ll_IR(self, irStr: str):
        irStr = generateAndAppendHwtHlsFunctionDeclarations(irStr)
        llvm = LlvmCompilationBundle("test")
        Err = SMDiagnostic()
        M = parseIR(irStr, "test", Err, llvm.ctx)
        if M is None:
            raise AssertionError(Err.str("test", True, True))
        else:
            fns = tuple(M)
            llvm.module = M
            llvm.main = fns[0]
            name = llvm.main.getName().str()

        llvm._testVRegIfConverterForIr()
        MF = llvm.getMachineFunction(llvm.main)
        assert MF
        self.assert_same_as_file(str(MF), os.path.join("data", self.__class__.__name__ + "." + name + ".out.mir.ll"))

    def test_noOptSingleBlock(self):
        ir = """\
        define void @noOptSingleBlock(i8 addrspace(2)* %o) {
          bb.0:
            %0 = call i8 @hwtHls.bitConcat.i4.i4(i4 1, i4 2) #2
            store volatile i8 %0, i8 addrspace(2)* %o, align 1
            ret void
        }
        """
        self._test_ll_IR(ir)

    def test_returnBlockMerge0(self):
        ir = """\
        define void @returnBlockMerge0(i1 addrspace(2)* %iC0, i8 addrspace(2)* %o) {
          bb.0:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            %v0 = call i8 @hwtHls.bitConcat.i4.i4(i4 1, i4 2) #2
            store volatile i8 %v0, i8 addrspace(2)* %o, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            ret void
          FBB:
            ret void
        }
        """
        self._test_ll_IR(ir)

    def test_SimpleFalse(self):
        # Same as ICSimple, but on the false path.
        ir = """\
        define void @SimpleFalse(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            ret void
          FBB:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            ret void
        }
        """
        self._test_ll_IR(ir)

    def test_simple(self):
        # Simple (split, no rejoin):
        #   EBB
        #   | \_
        #   |  |
        #   | TBB---> exit
        #   |
        #   FBB
        # BB is entry of an one split, no rejoin sub-CFG.
        ir = """\
        define void @simple(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            ret void
          FBB:
            ret void
        }
        """
        self._test_ll_IR(ir)

    def test_simpleWithTooManyBranches(self):
        # Simple (split, no rejoin):
        #   EBB
        #   | \_
        #   |  |
        #   | TBB---> L0
        #   |
        #   FBB
        #   | \
        #   FT TF
        # In this case it is not possible to merge branch of TBB to
        ir = """\
        define void @simpleWithTooManyBranches(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            br label %L0
          FBB:
            %c1 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c1, label %FTBB, label %FFBB
          FTBB:
            store volatile i8 3, i8 addrspace(3)* %o, align 1
            br label %FTBB
          FFBB:
            store volatile i8 2, i8 addrspace(3)* %o, align 1
            br label %FFBB
          L0:
            store volatile i8 1, i8 addrspace(3)* %o, align 1
            br label %L0
        }
        """
        self._test_ll_IR(ir)

    def test_simpleInDiamondLike(self):
        # Simple (split, no rejoin):
        # EntryBB
        # |   |
        # L0* EBB
        # |   | \_
        # |   |  |
        #  FBB  TBB
        #   |    |
        #   BotBB
        # * merge EBB to EntryBB, and Then TBB
        ir = """\
        define void @simpleInDiamondLike(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EntryBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %L0, label %EBB
          L0:
            %cL0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %cL0, label %L0, label %FBB
          EBB:
            %c1 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c1, label %TBB, label %FBB
          FBB:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            br label %BotBB
          TBB:
            store volatile i8 1, i8 addrspace(3)* %o, align 1
            br label %BotBB
          BotBB:
            ret void
        }
        """
        self._test_ll_IR(ir)

#    def test_TriangleFRev(self):
        # Same as ICTriangleFalse, but false path rev condition.
#    def test_TriangleRev(self):  # Same as ICTriangle, but true path rev condition.
    def test_TriangleFalse(self):  # Same as ICTriangle, but on the false path.
        ir = """\
        define void @triangleFalse(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %FBB, label %TBB
          TBB:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            br label %FBB
          FBB:
            ret void
        }
        """
        self._test_ll_IR(ir)

    def test_Triangle(self):  # BB is entry of a triangle sub-CFG.
        # Triangle:
        #   EBB
        #   | \_
        #   |  |
        #   | TBB
        #   |  /
        #   FBB
        ir = """\
        define void @triangle(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            br label %FBB
          FBB:
            ret void
        }
        """
        self._test_ll_IR(ir)

    def test_ForkedTriangle0(self):  # BB is entry of a triangle sub-CFG.
        # Triangle:
        #   EBB
        #   | \_
        #   |  |
        #   | TBB -- BBLoop
        #   |  /
        #   FBB
        ir = """\
        define void @forkedTriangle0(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            %c1 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c1, label %FBB, label %BBLoop
          FBB:
            ret void
          BBLoop:
            store volatile i8 1, i8 addrspace(3)* %o, align 1
            br label %BBLoop
        }
        """
        self._test_ll_IR(ir)

    def test_ForkedTriangle1(self):
        # test_ForkedTriangle with reordered blocks
        ir = """\
        define void @forkedTriangle1(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            %c1 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c1, label %FBB, label %BBLoop
          BBLoop:
            store volatile i8 1, i8 addrspace(3)* %o, align 1
            br label %BBLoop
          FBB:
            ret void
        }
        """
        self._test_ll_IR(ir)

    def test_Diamond0(self):
        # BB is entry of a diamond sub-CFG.
        # Diamond:
        #   EBB
        #   / \_
        #  |   |
        # TBB FBB
        #   \ /
        #  TailBB
        # Note TailBB can be empty.
        ir = """\
        define void @diamond0(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            store volatile i8 10, i8 addrspace(3)* %o, align 1
            br label %TailBB
          FBB:
            store volatile i8 11, i8 addrspace(3)* %o, align 1
            br label %TailBB
          TailBB:
            ret void
        }
        """
        self._test_ll_IR(ir)

    def test_Diamond1(self):
        # same as Diamond0 just Branch condition in EBB reversed
        ir = """\
        define void @diamond1(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            %c0_n = xor i1 %c0, true
            br i1 %c0_n, label %FBB, label %TBB
          TBB:
            store volatile i8 10, i8 addrspace(3)* %o, align 1
            br label %TailBB
          FBB:
            store volatile i8 11, i8 addrspace(3)* %o, align 1
            br label %TailBB
          TailBB:
            ret void
        }
        """
        self._test_ll_IR(ir)

#    def test_ForkedDiamond(self):# BB is entry of an almost diamond sub-CFG, with a
        # ForkedDiamond:
        # if TBB and FBB have a common tail that includes their conditional
        # branch instructions, then we can If Convert this pattern.
        #          EBB
        #         _/ \_
        #         |   |
        #        TBB  FBB
        #        / \ /   \
        #  FalseBB TrueBB FalseBB
        #
        #

    def test_mergeRegSet(self):
        self._test_ll()

    def test_linearSequenceOfBlocksWithSameTail(self):
        # while iC0 load is 1 continue upto 4x
        ir = """\
        define void @linearSequenceOfBlocksWithSameTail(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          BB0:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %BB1, label %TailBB
          BB1:
            %c1 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c1, label %BB2, label %TailBB
          BB2:
            %c2 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c2, label %BB3, label %TailBB
          BB3:
            %c3 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br label %TailBB
          TailBB:
            ret void
        }
        """
        # [todo] liveness incorrect, dead %1, %2 missing kill
        self._test_ll_IR(ir)

    def test_LoopTail0(self):
        ir = """\
        define void @LoopTail0(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          BB0:
            br label %BBL0
          BBL0:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %BBTail, label %BBExit
          BBTail:
            %c1 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c1, label %BBL0, label %BBExit
          BBExit:
            ret void
        }
        """
        self._test_ll_IR(ir)


if __name__ == "__main__":
    # from hwt.synthesizer.utils import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # u = SliceBreak3()
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([VRegIfConverter_TC('test_noOptSingleBlock')])
    suite = testLoader.loadTestsFromTestCase(VRegIfConverter_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
