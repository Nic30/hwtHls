#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, parseIR, SMDiagnostic, Function
from tests.llvmIr.baseLlvmIrTC import generateAndAppendHwtHlsFunctionDeclarations
from tests.llvmMir.baseLlvmMirTC import BaseLlvmMirTC


class VRegIfConverter_TC(BaseLlvmMirTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        llvm._testVRegIfConverter()

    def _test_ll(self, irStr: str, lowerSsaToNonSsa=False):
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

        llvm._testVRegIfConverterForIr(lowerSsaToNonSsa)
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
        self._test_ll(ir)

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
        self._test_ll(ir)

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
        self._test_ll(ir)

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
        self._test_ll(ir)

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
        self._test_ll(ir)

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
        self._test_ll(ir)

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
        self._test_ll(ir)

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
        self._test_ll(ir)

    def test_TriangleWithLiveoutSsa(self):
        # same as test_Triangle but with phi at end
        ir = """\
        define void @triangleWithLiveoutSsa(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            br label %FBB
          FBB:
            %res = phi i8 [ 2, %EBB ], [ 3, %TBB ]
            store volatile i8 %res, i8 addrspace(3)* %o, align 1
            ret void
        }
        """
        self._test_ll(ir)

    def test_TriangleWithLiveout(self):
        # same as test_TriangleWidthLiveoutSsa just with lowering to non-SSA
        ir = """\
        define void @triangleWithLiveout(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            br label %FBB
          FBB:
            %res = phi i8 [ 2, %EBB ], [ 3, %TBB ]
            store volatile i8 %res, i8 addrspace(3)* %o, align 1
            ret void
        }
        """
        self._test_ll(ir, lowerSsaToNonSsa=True)

    def test_TriangleWithLiveoutStoredMultipletimes(self):
        # same as test_TriangleWithLiveout just register is written multipletimes
        # in if-converted block
        self._test_mir_file()

    def test_ForkedTriangle0(self):  # BB is entry of a triangle sub-CFG.
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
        self._test_ll(ir)

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
        self._test_ll(ir)

    def test_ForkedTriangleInLoop(self):  # BB is entry of a triangle sub-CFG.
        #   BBLoopHead <--+
        #   |             |
        #   EBB           |
        #   |  \_         |
        #   | TBB -+      |
        #   |  /   |      |
        #   FBB    |      |
        #   |      v      |
        #   BBLoopTail----+

        ir = """\
        define void @forkedTriangleInLoop(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          BBEntry:
            br label %BBLoopHead
          BBLoopHead:
            br label %EBB
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            %c1 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            store volatile i8 1, i8 addrspace(3)* %o, align 1
            br i1 %c1, label %FBB, label %BBLoopTail
          FBB:
            store volatile i8 2, i8 addrspace(3)* %o, align 1
            br label %BBLoopTail
          BBLoopTail:
            store volatile i8 3, i8 addrspace(3)* %o, align 1
            br label %BBLoopHead
        }
        """
        self._test_ll(ir)

    def test_ForkedTriangleWhichIsLoopInLoop0(self):  # BB is entry of a triangle sub-CFG.
        #   BBLoopHead <--+
        #   |             |
        #   EBB <---------+
        #   |  \_         |
        #   | TBB -+      |
        #   |  /   |      |
        #   FBB    |      |
        #   |      v      |
        #   BBLoopTail----+

        ir = """\
        define void @forkedTriangleWhichIsLoopInLoop0(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          BBEntry:
            br label %BBLoopHead
          BBLoopHead:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            br label %EBB
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            store volatile i8 1, i8 addrspace(3)* %o, align 1
            br i1 %c0, label %TBB, label %FBB
          TBB:
            %c1 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            store volatile i8 2, i8 addrspace(3)* %o, align 1
            br i1 %c1, label %FBB, label %BBLoopTail
          FBB:
            store volatile i8 3, i8 addrspace(3)* %o, align 1
            br label %BBLoopTail
          BBLoopTail:
            store volatile i8 4, i8 addrspace(3)* %o, align 1
            %c2 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c2, label %EBB, label %BBLoopHead
        }
        """
        self._test_ll(ir)

    def test_ForkedTriangleWhichIsLoopInLoop1(self):  # BB is entry of a triangle sub-CFG.
        # forkedTriangleWhichIsLoopInLoop0 with modified branch order
        ir = """\
        define void @forkedTriangleWhichIsLoopInLoop1(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
          BBEntry:
            br label %BBLoopHead
          BBLoopHead:
            store volatile i8 0, i8 addrspace(3)* %o, align 1
            br label %EBB
          EBB:
            %c0 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            store volatile i8 1, i8 addrspace(3)* %o, align 1
            br i1 %c0, label %FBB, label %TBB
          TBB:
            %c1 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            store volatile i8 2, i8 addrspace(3)* %o, align 1
            br i1 %c1, label %FBB, label %BBLoopTail
          FBB:
            store volatile i8 3, i8 addrspace(3)* %o, align 1
            br label %BBLoopTail
          BBLoopTail:
            store volatile i8 4, i8 addrspace(3)* %o, align 1
            %c2 = load volatile i1, i1 addrspace(2)* %iC0, align 1
            br i1 %c2, label %BBLoopHead, label %EBB
        }
        """
        self._test_ll(ir)

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
        self._test_ll(ir)

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
        self._test_ll(ir)

    def test_Diamond0withLiveout(self):
        # same as Diamond0 just with extra live registers on entry to TailBB
        ir = """\
        define void @diamond0withLiveout(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
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
            %res = phi i8 [ 2, %TBB ], [ 3, %FBB ]
            store volatile i8 %res, i8 addrspace(3)* %o, align 1
            ret void
        }
        """
        self._test_ll(ir, lowerSsaToNonSsa=True)

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
        self._test_mir_file()

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
        self._test_ll(ir)

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
        self._test_ll(ir)

    def test_LoopOptionalTail(self):
        ir = """\
        define void @LoopOptionalTail(ptr addrspace(1) %i, ptr addrspace(2) %o) {
          HlsPythonHwWhile3.mainThread:
            br label %bb1
          
          bb1:
            %"i0(i_read)" = load volatile i8, ptr addrspace(1) %i, align 1
            %"1.not" = icmp eq i8 %"i0(i_read)", 1
            br i1 %"1.not", label %bb3, label %bb2
          
          bb2:
            %"i2(i_read)" = load volatile i8, ptr addrspace(1) %i, align 1
            store volatile i8 %"i2(i_read)", ptr addrspace(2) %o, align 1
            %"4.not" = icmp eq i8 %"i2(i_read)", 2
            br i1 %"4.not", label %bb1, label %bb3
          
          bb3:
            store volatile i8 99, ptr addrspace(2) %o, align 1
            br label %bb1
        }
        """
        self._test_ll(ir)

    def test_switchInLoop0(self):
        ir = """\
        define void @ShifterLeftUsingHwLoopWithWhileNot0.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o, ptr addrspace(3) %sh) {
          ShifterLeftUsingHwLoopWithWhileNot0.mainThread:
            br label %bb0
          
          bb0:
            %"i0(i_read)" = load volatile i8, ptr addrspace(1) %i, align 1
            %0 = call i7 @hwtHls.bitRangeGet.i8.i4.i7.0(i8 %"i0(i_read)", i4 0) #2
            %"sh1(sh_read)" = load volatile i3, ptr addrspace(3) %sh, align 1
            switch i3 %"sh1(sh_read)", label %bb0.crit_edge [
              i3 0, label %bb
              i3 1, label %bb.loopexit
              i3 2, label %bb.loopexit.fold.split2
              i3 3, label %bb.loopexit.fold.split3
              i3 -4, label %bb.loopexit.fold.split4
              i3 -3, label %bb.loopexit.fold.split5
              i3 -2, label %bb.loopexit.fold.split6
              i3 -1, label %bb.loopexit.fold.split7
            ]
          
          bb0.crit_edge:
            unreachable
          
          bb.loopexit.fold.split2:
            %1 = call i6 @hwtHls.bitRangeGet.i8.i4.i6.0(i8 %"i0(i_read)", i4 0) #2
            %2 = call i7 @hwtHls.bitConcat.i1.i6(i1 false, i6 %1) #2
            br label %bb.loopexit
          
          bb.loopexit.fold.split3:
            %3 = call i5 @hwtHls.bitRangeGet.i8.i4.i5.0(i8 %"i0(i_read)", i4 0) #2
            %4 = call i7 @hwtHls.bitConcat.i2.i5(i2 0, i5 %3) #2
            br label %bb.loopexit
          
          bb.loopexit.fold.split4:
            %5 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.0(i8 %"i0(i_read)", i4 0) #2
            %6 = call i7 @hwtHls.bitConcat.i3.i4(i3 0, i4 %5) #2
            br label %bb.loopexit
          
          bb.loopexit.fold.split5:
            %7 = call i3 @hwtHls.bitRangeGet.i8.i4.i3.0(i8 %"i0(i_read)", i4 0) #2
            %8 = call i7 @hwtHls.bitConcat.i4.i3(i4 0, i3 %7) #2
            br label %bb.loopexit
          
          bb.loopexit.fold.split6:
            %9 = call i2 @hwtHls.bitRangeGet.i8.i4.i2.0(i8 %"i0(i_read)", i4 0) #2
            %10 = call i7 @hwtHls.bitConcat.i5.i2(i5 0, i2 %9) #2
            br label %bb.loopexit
          
          bb.loopexit.fold.split7:
            %11 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.0(i8 %"i0(i_read)", i4 0) #2
            %12 = call i7 @hwtHls.bitConcat.i6.i1(i6 0, i1 %11) #2
            br label %bb.loopexit
          
          bb.loopexit:
            %.phiConc36 = phi i7 [ %0, %bb0 ], [ %2, %bb.loopexit.fold.split2 ], [ %4, %bb.loopexit.fold.split3 ], [ %6, %bb.loopexit.fold.split4 ], [ %8, %bb.loopexit.fold.split5 ], [ %10, %bb.loopexit.fold.split6 ], [ %12, %bb.loopexit.fold.split7 ]
            %13 = call i8 @hwtHls.bitConcat.i1.i7(i1 false, i7 %.phiConc36) #2
            br label %bb
          
          bb:
            %.phiConc38 = phi i8 [ %"i0(i_read)", %bb0 ], [ %13, %bb.loopexit ]
            store volatile i8 %.phiConc38, ptr addrspace(2) %o, align 1
            br label %bb0
        }
        """
        self._test_ll(ir, lowerSsaToNonSsa=True)

    def test_switchInLoop1(self):
        ir = """\
        define void @SwitchInLoop1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
          t0_AxiSParse2IfAndSequel:
            br label %bb0
          
          bb0:
            %c = load volatile i16, ptr addrspace(1) %i, align 2
            switch i16 %c, label %bb3 [
              i16 2, label %bb2
              i16 1, label %bb1
            ]
        
          bb1:
            br label %bb2
          
          bb2:
            %ph0 = phi i1 [ true, %bb0 ], [ false, %bb1 ]
            store volatile i1 %ph0, ptr addrspace(2) %o, align 2
            br label %bb3
          
          bb3:
            br label %bb0
        }
        """

        self._test_ll(ir, lowerSsaToNonSsa=True)

    def test_switchInLoop2(self):
        ir = """\
        define void @SwitchInLoop2(ptr addrspace(1) %i, ptr addrspace(2) %o) {
          t0_AxiSParse2IfAndSequel:
            br label %bb0
          
          bb0:
            %c = load volatile i16, ptr addrspace(1) %i, align 2
            switch i16 %c, label %bb3 [
              ; values 3, 7 are picked to have space between otherwise
              ; this interval would get merged and sub, UGT would be used
              i16 3, label %bb2 
              i16 7, label %bb1
            ]
        
          bb1:
            br label %bb2
          
          bb2:
            br label %bb3
          
          bb3:
            %phi0 = phi i8 [ 10, %bb0 ], [ 20, %bb2 ]
            store volatile i8 %phi0, ptr addrspace(2) %o, align 4
            br label %bb0
        }
        """

        self._test_ll(ir, lowerSsaToNonSsa=True)

    def test_switchInLoop3(self):
        ir = """\
        define void @SwitchInLoop3(ptr addrspace(1) %i, ptr addrspace(2) %o) {
          t0_AxiSParse2IfAndSequel:
            br label %bb0
          
          bb0:
            %c = load volatile i16, ptr addrspace(1) %i, align 2
            switch i16 %c, label %bb3 [
              ; will reduce to %c sub 3 UGT 1
              i16 3, label %bb2 
              i16 4, label %bb1
            ]
        
          bb1:
            br label %bb2
          
          bb2:
            br label %bb3
          
          bb3:
            %phi0 = phi i8 [ 10, %bb0 ], [ 20, %bb2 ]
            store volatile i8 %phi0, ptr addrspace(2) %o, align 4
            br label %bb0
        }
        """

        self._test_ll(ir, lowerSsaToNonSsa=True)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([VRegIfConverter_TC('test_ForkedTriangle0')])
    suite = testLoader.loadTestsFromTestCase(VRegIfConverter_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
