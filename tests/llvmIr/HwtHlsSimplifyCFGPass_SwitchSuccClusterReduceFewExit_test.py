#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.HwtHlsSimplifyCFGPass_test import HwtHlsSimplifyCFGPass_TC
from tests.stripInstructionsUnrelatedToCrash import llmIrStripInstrucionsUnrelatedToCrash


class HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        return HwtHlsSimplifyCFGPass_TC._runTestOpt(self, llvm, *args, **kwargs)

    def test_SwitchSuccClusterReduceFewExit_0(self):
        #                      +-----------------------+
        #                      |                       |
        #                      |    +---------------+  |
        #   +------------------+    |   bb.entry    |  |
        #   |                       +---------------+  |
        #   |                         v                v
        #   |                       +-------------------------+
        #   |                  +--> |      bb.loop0.head      | <+
        #   |                  |    +-------------------------+  |
        #   |                  |      |                          |
        #   |                  |      v                          |
        # +------------+       |    +-------------------------+  |       +------------------+
        # | bb.swJump1 | <-----+--- |          bb.sw          |  |       | bb.swUnreachable |
        # +------------+       |    +-------------------------+  |       +------------------+
        #   |                  |      |                |    |    |         ^
        #   |                  |      |                |    +----+---------+
        #   |                  |      v                |         |
        #   |                  |    +---------------+  |         |
        #   |                  +--- |  bb.swJump2   |  |         |
        #   |                       +---------------+  |         |
        #   |                         v                |         |
        #   |                       +---------------+  |         |
        #   +---------------------> |  bb.swJump0   | <+         |
        #                           +---------------+            |
        #                             v                          |
        #                           +---------------+            |
        #                      +--- |               |            |
        #                      |    | bb.loop1.head |            |
        #                      +--> |               | -----------+
        #                           +---------------+
        # 
        llvmIr = """\
        define void @test_SwitchSuccClusterReduceFewExit_0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.entry:
          br label %bb.loop0.head

        bb.loop0.head:
          %e0 = load volatile i1, ptr addrspace(1) %i, align 4
          %c0 = load volatile i2, ptr addrspace(1) %i, align 4
          br label %bb.sw

        bb.sw:                         ; preds = %bb.loop0.head
          switch i2 %c0, label %bb.swUnreachable [
            i2 0, label %bb.swJump0
            i2 1, label %bb.swJump1
            i2 -2, label %bb.swJump2
          ]
        
        bb.swJump1:                               ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump2:                             ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump0:                          ; preds = %bb.sw, %bb.swJump2, %bb.swJump1
          br label %bb.loop1.head
        
        bb.loop1.head:                                    ; preds = %bb.swJump0, %bb.loop1.head
          %e1 = load volatile i1, ptr addrspace(1) %i, align 4
          br i1 %e1, label %bb.loop0.head, label %bb.loop1.head
        
        bb.swUnreachable:                        ; preds = %bb.sw
          unreachable
        }
        """
        self._test_ll(llvmIr)

    def test_SwitchSuccClusterReduceFewExit_2exit0(self):
        #                         +--------+
        #                         |  bb0   |
        #                         +--------+
        #                           v
        #             +-----+     +-------------+
        #             | bb9 | <-- |     bb1     | <+
        #             +-----+     +-------------+  |
        #                           v         |    |
        #                         +--------+  |    |
        #                      +- |  bb2   |  |    |
        #                      |  +--------+  |    |
        #                      |    v         |    |
        #       +-----+        |  +--------+  |    |
        #       | bb5 | <------+- |  bb4   |  |    |
        #       +-----+        |  +--------+  |    |
        #         |            |    v         |    |
        #         |            |  +--------+  |    |
        #         |            |  | bb6.e0 | <+    |
        #         |            |  +--------+       |
        #         |            |    v              |
        #         |            |  +--------+       |
        #         |            +> |  bb3   |       |
        #         |               +--------+       |
        #         |                 v              |
        #         |               +--------+       |
        #         +-------------> | bb7.e1 |       |
        #                         +--------+       |
        #                           v              |
        #                         +--------+       |
        #                         |  bb8   | ------+
        #                         +--------+        
        llvmIr = """\
        define void @test_SwitchSuccClusterReduceFewExit_2exit0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          %st = alloca i2, align 1
          store i2 0, ptr %st, align 1
          br label %bb1
        
        bb1:                    ; preds = %bb8, %bb0
          %c0 = load i2, ptr %st, align 1
          %1 = load volatile i10, ptr addrspace(1) %i, align 2
          %c1 = load volatile i1, ptr addrspace(1) %i, align 2
          %v0 = load volatile i8, ptr addrspace(1) %i, align 2
          %v1 = load volatile i8, ptr addrspace(1) %i, align 2
          %c2 = icmp eq i8 %v0, 2
          switch i2 %c0, label %bb9 [
            i2 0, label %bb2
            i2 1, label %bb6.e0
          ]
        
        bb2:                                              ; preds = %bb1
          br i1 %c1, label %bb4, label %bb3
        
        bb3:                                     ; preds = %bb2, %bb6.e0
          br label %bb7.e1
        
        bb4:                          ; preds = %bb2
          br i1 %c2, label %bb5, label %bb6.e0
        
        bb5:                                ; preds = %bb4
          br label %bb7.e1
        
        bb6.e0:                                   ; preds = %bb1, %bb4
          %v2 = phi i8 [ %v1, %bb1 ], [ %v0, %bb4 ]
          store volatile i8 %v2, ptr addrspace(2) %o, align 1
          br label %bb3
        
        bb7.e1:          ; preds = %bb3, %bb5
          %v3 = phi i2 [ 1, %bb5 ], [ 0, %bb3 ]
          store i2 %v3, ptr %st, align 1
          br label %bb8
        
        bb8:                     ; preds = %bb7.e1
          br label %bb1
        
        bb9:                   ; preds = %bb1
          unreachable
        }
        """
        self._test_ll(llvmIr)
    
    def test_2exits_conditionInExit0(self):
        #               +-------+
        #               |  bb0  |
        #               +-------+
        #                 v
        # +-------+     +-----------------+     +--------+
        # | bb.c0 | <-- |                 | --> | bb.def |
        # +-------+     |       bb1       |     +--------+
        #   |           |                 | <+
        #   |           +-----------------+  |
        #   |             v        |    |    |
        #   |           +-------+  |    |    |
        #   |        +- | bb.c2 |  |    |    |
        #   |        |  +-------+  |    |    |
        #   |        |    v        |    |    |
        #   |        |  +-------+  |    |    |
        #   |        |  | bb.c3 | <+    |    |
        #   |        |  +-------+       |    |
        #   |        |    v             v    |
        #   |        |  +-----------------+  |
        #   |        +> |    bb.latch     | -+
        #   |           +-----------------+
        #   |             ^
        #   +-------------+

        # :note: based on Axi4SParse2IfAndSequel_NO_FOOTER_16b_100MHz
        llvmIr = """\
        define void @test_2exits_conditionInExit0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          br label %bb1
        

        bb1:                                             ; preds = %bb0, %bb.latch
          %swCond = phi i3 [ %swCond.phi, %bb.latch ], [ 0, %bb0 ]
          %c0 = load volatile i3, ptr addrspace(1) %i, align 4
          %c1 = load volatile i3, ptr addrspace(1) %i, align 4
          %c2 = icmp eq i3 %c1, 0
          switch i3 %c0, label %bb.def [
            i3 0, label %bb.c0
            i3 1, label %bb.latch
            i3 2, label %bb.c2
            i3 3, label %bb.c3
          ]
        
        bb.c0:                                              ; preds = %bb1
          br label %bb.latch

        bb.c2:                                              ; preds = %bb1
          store volatile i32 10, ptr addrspace(2) %o, align 4
          br i1 %c2, label %bb.latch, label %bb.c3
                
        bb.c3:                                             ; preds = %bb1, %bb.c2
          br label %bb.latch
        
        bb.latch:                                             ; preds = %bb.c0, %bb.c2, %bb1, %bb.c3
          %swCond.phi = phi i3 [ 2, %bb1 ], [ 0, %bb.c3 ], [ 3, %bb.c2 ], [ %c0, %bb.c0 ]
          store volatile i3 %swCond.phi, ptr addrspace(2) %o, align 4
          br label %bb1
        
        bb.def:                                             ; preds = %bb1
          unreachable
        }
        """
        self._test_ll(llvmIr, passKwArgs=dict(
            RunEarlyCSEPass=False,
            RunRomExtractPass=False,
            RunHwtHlsInstCombinePass=False,
            RunTrivialSimplifyCFGPass=False,
            RunSimplifyCFGPass=False,
            RunBitcountMergePass=False,
            )
        )

    def test_2exits_and_header(self):
        # :note: based on Axi4SSParse2If Axi4SSParseIf_2Seg_TC test_Axi4SParse2If_48b_100MHz
        #               ┌───────┐
        #               │  bb0  │
        #               └───────┘
        #                 ▼
        # ┌───────┐     ┌─────────────────┐     ┌────────┐
        # │ bb.c0 │ ◀── │                 │ ──▶ │ bb.def │
        # └───────┘     │       bb1       │     └────────┘
        #   │           │                 │ ◀┐
        #   │           └─────────────────┘  │
        #   │             ▼        │    │    │
        #   │           ┌───────┐  │    │    │
        #   │        ┌─ │ bb.c2 │  │    │    │
        #   │        │  └───────┘  │    │    │
        #   │        │    ▼        │    │    │
        #   │        │  ┌───────┐  │    │    │
        #   │        │  │ bb.c3 │ ◀┘    │    │
        #   │        │  └───────┘       │    │
        #   │        │    ▼             ▼    │
        #   │        │  ┌─────────────────┐  │
        #   │        └▶ │    bb.latch     │ ─┘
        #   │           └─────────────────┘
        #   │             ▲
        #   └─────────────┘        
        #         
        llvmIr = """\
        define void @test_2exits_and_header(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          br label %bb3
        
        bb3:                                              ; preds = %bb0, %bb5, %bb3
          %c0 = load volatile i1, ptr addrspace(1) %i, align 8
          %v0 = load volatile i16, ptr addrspace(1) %i, align 8

          br i1 %c0, label %bb3.sw, label %bb3
        
        bb3.sw:                          ; preds = %bb3
          switch i16 %v0, label %bb9 [
            i16 2, label %bb4
            i16 4, label %bb5.e1
          ]
        
        bb4:                                              ; preds = %bb3.sw
          br label %bb5.e1
        
        bb5.e1:                                   ; preds = %bb4, %bb3.sw
          %phi0 = phi i16 [ 0, %bb4 ], [ %v0, %bb3.sw ]
          store volatile i16 %phi0, ptr addrspace(2) %o, align 4
          br label %bb5
        
        bb5:                                              ; preds = %bb9, %bb5.e1
          br label %bb3
        
        bb9:                                              ; preds = %bb3.sw
          br label %bb5
        }
        """
        self._test_ll(llvmIr, passKwArgs=dict(
            RunEarlyCSEPass=False,
            RunRomExtractPass=False,
            RunHwtHlsInstCombinePass=False,
            RunTrivialSimplifyCFGPass=False,
            RunSimplifyCFGPass=False,
            RunBitcountMergePass=False,
            )
        )

    def test_2exits_and_header_and_exit01phis(self):
        # :note: based on Axi4SSParseIf_1Seg_TC("test_Axi4SParse2IfAndSequel_NO_FOOTER_16b_100MHz")
        #     bb.header ---> bb.unreach
        #   / |    \  \  \  
        #   | |    \  bb4 |
        #   | |    \  /   |
        #   | |  bb.e0    |
        #   | |   / |     |
        # bb3 |  / bb2 <--+
        #   | | / /
        #   | |/ /
        #  bb.e1 
        #
        # It will be rewritten into format
        #  bb.header
        #    |    \
        #    |  bb.e0
        #    |   / |
        #    |  / bb2
        #    | / /
        #    |/ /
        #  bb.e1
        # The bug because of which this test was written was that %state.sink
        # was missing final select for path bb.header->bb2->bb.e1

        llvmIr = """\
define void @test_2exits_and_header_and_exit01phis(ptr addrspace(1) %i, ptr addrspace(2) %o)  {
bb0:
  br label %bb.header

bb.header:                                             ; preds = %bb0, %bb.e1
  %state = phi i3 [ %state.sink, %bb.e1 ], [ 0, %bb0 ]
  %d0 = load volatile i18, ptr addrspace(1) %i, align 4
  %s0 = load volatile i3, ptr addrspace(1) %i, align 4
  %s1 = load volatile i3, ptr addrspace(1) %i, align 4
  %s2 = load volatile i3, ptr addrspace(1) %i, align 4
  %s3 = load volatile i3, ptr addrspace(1) %i, align 4
  %s4 = load volatile i3, ptr addrspace(1) %i, align 4
  switch i3 %state, label %bb.unreach [
    i3 0, label %bb3
    i3 1, label %bb.e1
    i3 2, label %bb4
    i3 3, label %bb.e0
    i3 -4, label %bb2
  ]

bb3:                                              ; preds = %bb.header
  br label %bb.e1

bb.e0:                                             ; preds = %bb.header, %bb4
  %state.0 = phi i3 [ %s0, %bb.header ], [ %s1, %bb4 ]
  store volatile i32 0, ptr addrspace(2) %o, align 4
  %c0 = load volatile i1, ptr addrspace(1) %i, align 4
  br i1 %c0, label %bb.e1, label %bb2

bb2:                                             ; preds = %bb.header, %bb.e0
  br label %bb.e1

bb4:                                              ; preds = %bb.header
  br label %bb.e0

bb.e1:                                             ; preds = %bb3, %bb.e0, %bb.header, %bb2
  %state.sink = phi i3 [ %s2, %bb3 ], [ %state.0, %bb.e0 ], [ %s4, %bb.header ], [ %s3, %bb2 ]
  br label %bb.header

bb.unreach:                                             ; preds = %bb.header
  unreachable
}
        """
        self._test_ll(llvmIr, passKwArgs=dict(
            RunEarlyCSEPass=False,
            RunRomExtractPass=False,
            RunHwtHlsInstCombinePass=False,
            RunTrivialSimplifyCFGPass=False,
            RunSimplifyCFGPass=False,
            RunBitcountMergePass=False,
            )
        )

    def test_multiPhi3(self):
        # :note: based on Axi4SSParse2IfAndSequel.mainThread, SEGMENT_CNT=2, SEGMENT_WIDTH=16
        # .. code-block:: text
        #                    ┌──────┐
        #                    │ bb0  │
        #                    └──────┘
        #                      ▼
        #                    ┌──────┐
        #            ┌─────▶ │ bb27 │ ─┐
        #            │       └──────┘  │
        #            │         ▼       │
        #            │       ┌──────┐  │
        #            │       │ bb32 │  │
        #            │       └──────┘  │
        #            │         ▼       ▼
        #            │       ┌────────────────┐     ┌──────┐
        #            │       │                │ ──▶ │ bb25 │
        #            │       │                │     └──────┘
        #            │       │      bb44      │ ───────────────────┐
        #            │       │                │     ┌──────┐       │
        #            │       │                │ ──▶ │ bb41 │       │
        #            │       └────────────────┘     └──────┘       │
        #            │         ▼       │    │         ▼            ▼
        #            │       ┌──────┐  │    │       ┌──────┐     ┌──────┐
        #            │    ┌─ │ bb31 │  │    └─────▶ │ bb35 │ ──▶ │ bb39 │
        #            │    │  └──────┘  │            └──────┘     └──────┘
        #            │    │    │       │              │            │
        #      *     │    │    ▼ bb0   │              │            │
        # ┌──────┐   │    │  ┌──────┐  │              │            │
        # │ bb43 │ ◀─┼────┼─ │ bb33 │ ─┼────┐         │            │
        # └──────┘   │    │  └──────┘  │    │         │            │
        #   │        │    │    │       │    │         │            │
        #   │        │    │    ▼ e0    │    │         │            │
        #   │        │    │  ┌──────┐  │    │         │            │
        #   │        │    │  │ bb37 │ ◀┼────┼─────────┘            │
        #   │        │    │  └──────┘  │    │                      │
        #   │        │    │    │       │    │                      │
        #   │        │    │    ▼ e1    ▼    ▼                      │
        #   │        │    │  ┌────────────────┐                    │
        #   │        │    └▶ │                │ ◀──────────────────┘
        #   │        └────── │      bb45      │
        #   └──────────────▶ │                │
        #                    └────────────────┘
        # 
        # 

        llvmIr = """\
define void @test_multiPhi3(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb27

bb27:                                             ; preds = %bb45, %bb0
  %0 = load volatile i38, ptr addrspace(1) %i, align 8
  %1 = trunc i38 %0 to i1
  %2 = trunc i38 %0 to i1
  %3 = trunc i38 %0 to i16
  br i1 %2, label %bb32, label %bb44

bb31:                                             ; preds = %bb44
  br i1 %1, label %bb33, label %bb45

bb32:                                             ; preds = %bb27
  br label %bb44

bb33:                                             ; preds = %bb31
  switch i16 %3, label %bb37 [
    i16 3, label %bb45
    i16 4, label %bb43
  ]

bb35:                                             ; preds = %bb44, %bb41
  %iDataOffset.1.1lane = phi i1 [ true, %bb41 ], [ false, %bb44 ]
  br i1 %iDataOffset.1.1lane, label %bb37, label %bb39

bb37:                                             ; preds = %bb35, %bb33
  br label %bb45

bb39:                                             ; preds = %bb44, %bb35
  br label %bb45

bb41:                                             ; preds = %bb44
  br label %bb35

bb43:                                             ; preds = %bb33
  br label %bb45

bb44:                                             ; preds = %bb32, %bb27
  %.sink.0lane = phi i3 [ -4, %bb32 ], [ 0, %bb27 ]
  switch i3 %.sink.0lane, label %bb25 [
    i3 0, label %bb31
    i3 1, label %bb45
    i3 2, label %bb41
    i3 3, label %bb35
    i3 -4, label %bb39
  ]

bb45:                                             ; preds = %bb44, %bb43, %bb39, %bb37, %bb33, %bb31
  br label %bb27

bb25:                                             ; preds = %bb44
  unreachable
}
"""
        # llvm = llmIrStripInstrucionsUnrelatedToCrash(llvmIr, lambda llvm: self._runTestOpt(llvm))
        # print(str(llvm.main))
        self._test_ll(llvmIr, passKwArgs=dict(
            RunEarlyCSEPass=False,
            RunRomExtractPass=False,
            RunHwtHlsInstCombinePass=False,
            RunTrivialSimplifyCFGPass=False,
            RunSimplifyCFGPass=False,
            RunBitcountMergePass=False,
            )
        )
        
    def test_multiPhi2(self):
        # :note: based on Axi4SSParse2IfAndSequel.mainThread, SEGMENT_CNT=2, SEGMENT_WIDTH=16
        #               ┌──────┐
        #               │ bb0  │
        #               └──────┘
        #                 ▼
        #               ┌──────┐
        #            ┌▶ │ bb27 │ ─┐
        #            │  └──────┘  │
        #            │    ▼       │
        #            │  ┌──────┐  │
        #            │  │ bb32 │  │
        #            │  └──────┘  │
        #            │    ▼       ▼
        #            │  ┌───────────────────┐
        #            │  │                   │ ─────────────────────┐
        #            │  │       bb44        │ ────────────────┐    │
        #            │  │                   │ ───────────┐    │    │
        #            │  └───────────────────┘            │    │    │
        #            │    ▼       │    ▼                 │    │    │
        #            │  ┌──────┐  │  ┌──────┐            │    │    │
        #       ┌────┼─ │ bb31 │  │  │ bb25 │            │    │    │
        #       │    │  └──────┘  │  └──────┘            │    │    │
        #       │    │    ▼       │                      │    │    │
        #       │    │  ┌──────┐  │                      │    │    │
        #       │    │  │ bb33 │ ─┼─────────────────┐    │    │    │
        #       │    │  └──────┘  │                 │    │    │    │
        #  ┌────┘    │    │       └────────────┐    │    │    │    │
        #  │         │    ▼                    │    │    │    │    │
        #  │         │  ┌──────┐     ┌──────┐  │    │    │    │    │
        #  │    ┌────┼▶ │ bb37 │ ◀── │ bb35 │  │    │    │    │    │
        #  │    │    │  └──────┘     └──────┘  │    │    │    │    │
        #  │    │    │    ▼            ▼       │    │    │    │    │
        #  │    │    │  ┌───────────────────┐  │    │    │    │    │
        #  │    │    └─ │                   │ ◀┼────┘    │    │    │
        #  └────┼─────▶ │       bb45        │ ◀┼─────────┘    │    │
        #       │       │                   │ ◀┼──────────────┘    │
        #       │       └───────────────────┘  │                   │
        #       │                      ▲       │                   │
        #       └──────────────────────┼───────┘                   │
        #                              └───────────────────────────┘
        #        
        llvmIr = """\
define void @test_multiPhi2(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb27

bb27:                                             ; preds = %bb45, %bb0
  %0 = load volatile i38, ptr addrspace(1) %i, align 8
  %1 = trunc i38 %0 to i1
  %2 = trunc i38 %0 to i1
  %3 = trunc i38 %0 to i16
  br i1 %2, label %bb32, label %bb44

bb31:                                             ; preds = %bb44
  br i1 %1, label %bb33, label %bb45

bb32:                                             ; preds = %bb27
  br label %bb44

bb33:                                             ; preds = %bb31
  br i1 %fewExitSw.sucSel.en.bb33.bb37, label %bb37, label %bb45

bb35:                                             ; No predecessors!
  %4 = load i1, ptr poison, align 1
  br i1 %4, label %bb37, label %bb45

bb37:                                             ; preds = %bb44, %bb33, %bb35
  %5 = phi i1 [ false, %bb44 ], [ %fewExitSw.sucSel.en.bb33.bb37, %bb33 ], [ false, %bb35 ]
  br label %bb45

bb44:                                             ; preds = %bb32, %bb27
  %.sink.0lane = phi i3 [ -4, %bb32 ], [ 0, %bb27 ]
  %6 = icmp eq i16 %3, 3
  %7 = icmp eq i16 %3, 4
  %8 = or i1 %6, %7
  %9 = xor i1 %8, true
  %fewExitSw.sucSel.en.bb33.bb37 = or i1 false, %9
  %fewExitSw.sucSel.en.bb33.bb43 = icmp eq i16 %3, 4
  %br.bb43.enFor.bb45 = and i1 %fewExitSw.sucSel.en.bb33.bb43, true
  %fewExitSw.sucSel.en.bb33.bb45 = icmp eq i16 %3, 3
  switch i3 %.sink.0lane, label %bb25 [
    i3 0, label %bb31
    i3 1, label %bb45
    i3 2, label %bb37
    i3 3, label %bb45
    i3 -4, label %bb45
  ]

bb45:                                             ; preds = %bb44, %bb35, %bb44, %bb33, %bb44, %bb37, %bb31
  %10 = phi i1 [ false, %bb44 ], [ false, %bb35 ], [ false, %bb44 ], [ %fewExitSw.sucSel.en.bb33.bb37, %bb33 ], [ false, %bb44 ], [ %5, %bb37 ], [ false, %bb31 ]
  br label %bb27

bb25:                                             ; preds = %bb44
  unreachable

}
"""
        # llvm = llmIrStripInstrucionsUnrelatedToCrash(llvmIr, lambda llvm: self._runTestOpt(llvm))
        # print(str(llvm.main))
        self._test_ll(llvmIr, passKwArgs=dict(
            RunEarlyCSEPass=False,
            RunRomExtractPass=False,
            RunHwtHlsInstCombinePass=False,
            RunTrivialSimplifyCFGPass=False,
            RunSimplifyCFGPass=False,
            RunBitcountMergePass=False,
            )
        )

    def test_multiPhi1(self):
        llvmIr = """\
define void @test_multiPhi1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb27

bb27:                                             ; preds = %bb45, %bb0
  %i_read3.r0.eof.reg2mem.0.reg2mem.0 = phi i1 [ %i_read3.r0.eof.reg2mem.1.ph.1lane, %bb45 ], [ undef, %bb0 ]
  %0 = load volatile i38, ptr addrspace(1) %i, align 8
  %1 = trunc i38 %0 to i1
  %2 = trunc i38 %0 to i1
  %3 = trunc i38 %0 to i16
  %4 = call i16 @hwtHls.bitRangeGet.i38.i7.i16.0(i38 0, i7 0) #2
  switch i3 0, label %bb25 [
    i3 0, label %bb30
    i3 1, label %bb44
    i3 2, label %bb40
    i3 3, label %bb34
    i3 -4, label %bb38
  ]

bb30:                                             ; preds = %bb27
  br i1 %2, label %bb32, label %bb44

bb31:                                             ; preds = %bb44
  br i1 %1, label %bb33, label %bb45

bb32:                                             ; preds = %bb30
  switch i16 %4, label %bb36 [
    i16 3, label %bb44
    i16 4, label %bb42
  ]

bb33:                                             ; preds = %bb31
  switch i16 %3, label %bb37 [
    i16 3, label %bb45
    i16 4, label %bb43
  ]

bb34:                                             ; preds = %bb40, %bb27
  br i1 false, label %bb36, label %bb38

bb35:                                             ; preds = %bb44, %bb41
  br i1 false, label %bb37, label %bb39

bb36:                                             ; preds = %bb34, %bb32
  br label %bb44

bb37:                                             ; preds = %bb35, %bb33
  br label %bb45

bb38:                                             ; preds = %bb34, %bb27
  br label %bb44

bb39:                                             ; preds = %bb44, %bb35
  br label %bb45

bb40:                                             ; preds = %bb27
  br label %bb34

bb41:                                             ; preds = %bb44
  br label %bb35

bb42:                                             ; preds = %bb32
  br label %bb44

bb43:                                             ; preds = %bb33
  br label %bb45

bb44:                                             ; preds = %bb42, %bb38, %bb36, %bb32, %bb30, %bb27
  %.sink.0lane = phi i3 [ 1, %bb42 ], [ -4, %bb36 ], [ 1, %bb32 ], [ 0, %bb30 ], [ 0, %bb38 ], [ 0, %bb27 ]
  %i_read3.r0.eof.reg2mem.1.ph.0lane = phi i1 [ %i_read3.r0.eof.reg2mem.0.reg2mem.0, %bb42 ], [ false, %bb36 ], [ false, %bb32 ], [ false, %bb30 ], [ false, %bb38 ], [ false, %bb27 ]
  switch i3 %.sink.0lane, label %bb25 [
    i3 0, label %bb31
    i3 1, label %bb45
    i3 2, label %bb41
    i3 3, label %bb35
    i3 -4, label %bb39
  ]

bb45:                                             ; preds = %bb44, %bb43, %bb39, %bb37, %bb33, %bb31
  %i_read3.r0.eof.reg2mem.1.ph.1lane = phi i1 [ %i_read3.r0.eof.reg2mem.1.ph.0lane, %bb43 ], [ false, %bb37 ], [ false, %bb33 ], [ false, %bb31 ], [ false, %bb39 ], [ false, %bb44 ]
  br label %bb27

bb25:                                             ; preds = %bb44, %bb27
  unreachable
}
"""
        self._test_ll(llvmIr, passKwArgs=dict(
            # RunEarlyCSEPass=False,
            # RunRomExtractPass=False,
            # RunHwtHlsInstCombinePass=False,
            # RunTrivialSimplifyCFGPass=False,
            # RunSimplifyCFGPass=False,
            # RunBitcountMergePass=False,
            )
        )

    def test_multiPhi0(self):
        llvmIr = """\
        define void @test_multiPhi0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  %bb3.ioFsmStBefore.IoFsmSt = alloca i3, align 1
  store i3 0, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  br label %bb27

bb27:                                             ; preds = %bb45, %bb0
  %i_read1.r0.data.reg2mem.2.reg2mem.0 = phi i16 [ %i_read1.r0.data.reg2mem.3.ph.1lane, %bb45 ], [ undef, %bb0 ]
  %i_read3.r0.data.reg2mem.0.reg2mem.0 = phi i16 [ %i_read3.r0.data.reg2mem.1.ph.1lane, %bb45 ], [ undef, %bb0 ]
  %i_read3.r0.eof.reg2mem.0.reg2mem.0 = phi i1 [ %i_read3.r0.eof.reg2mem.1.ph.1lane, %bb45 ], [ undef, %bb0 ]
  %0 = load i3, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %1 = load volatile i38, ptr addrspace(1) %i, align 8
  %i_read1.r0.empty.1lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.37(i38 %1, i7 37) #2
  %i_read1.r0.eof.1lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.36(i38 %1, i7 36) #2
  %2 = call i8 @hwtHls.bitRangeGet.i38.i7.i8.24(i38 %1, i7 24) #2
  %3 = call i8 @hwtHls.bitRangeGet.i38.i7.i8.16(i38 %1, i7 16) #2
  %i_read1.r0.enable.1lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.35(i38 %1, i7 35) #2
  %i_read1.r0.empty.0lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.34(i38 %1, i7 34) #2
  %i_read1.r0.eof.0lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.33(i38 %1, i7 33) #2
  %4 = call i8 @hwtHls.bitRangeGet.i38.i7.i8.8(i38 %1, i7 8) #2
  %5 = call i8 @hwtHls.bitRangeGet.i38.i7.i8.0(i38 %1, i7 0) #2
  %i_read1.r0.enable.0lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.32(i38 %1, i7 32) #2
  %6 = call i16 @hwtHls.bitRangeGet.i38.i7.i16.16(i38 %1, i7 16) #2
  %7 = call i16 @hwtHls.bitRangeGet.i38.i7.i16.0(i38 %1, i7 0) #2
  %8 = xor i1 %i_read1.r0.empty.0lane, true
  %9 = or i1 %i_read1.r0.eof.0lane, %8
  %fewExitSw.sucSel.en..bb4.0lane = icmp eq i16 %i_read1.r0.data.reg2mem.2.reg2mem.0, 3
  %10 = and i1 %i_read1.r0.eof.0lane, %i_read1.r0.empty.0lane
  %11 = or i1 %i_read3.r0.eof.reg2mem.0.reg2mem.0, %10
  %12 = and i1 %11, %i_read1.r0.empty.0lane
  %"(i_read3).0lane" = call i25 @hwtHls.bitConcat.i16.i8.i1(i16 %i_read3.r0.data.reg2mem.0.reg2mem.0, i8 %5, i1 %12) #2
  %i_read_data4.0lane = call i24 @hwtHls.bitRangeGet.i25.i6.i24.0(i25 %"(i_read3).0lane", i6 0) #2
  %13 = xor i1 %11, true
  %spec.select.0lane = call i4 @hwtHls.bitConcat.i3.i1(i3 0, i1 %13) #2
  %14 = icmp eq i4 %spec.select.0lane, 0
  %15 = or i1 %i_read3.r0.eof.reg2mem.0.reg2mem.0, %i_read1.r0.eof.0lane
  %"(i_read11).0lane" = call i33 @hwtHls.bitConcat.i16.i16.i1(i16 %i_read3.r0.data.reg2mem.0.reg2mem.0, i16 %7, i1 %15) #2
  %16 = call i24 @hwtHls.bitRangeGet.i33.i7.i24.0(i33 %"(i_read11).0lane", i7 0) #2
  %17 = call i3 @hwtHls.bitConcat.i1.i2(i1 %fewExitSw.sucSel.en..bb4.0lane, i2 1) #2
  switch i3 %0, label %bb25 [
    i3 0, label %bb30
    i3 1, label %bb44
    i3 2, label %bb40
    i3 3, label %bb34
    i3 -4, label %bb38
  ]

bb30:                                             ; preds = %bb27
  br i1 %i_read1.r0.enable.0lane, label %bb32, label %bb44

bb31:                                             ; preds = %bb44
  br i1 %i_read1.r0.enable.1lane, label %bb33, label %bb45

bb32:                                             ; preds = %bb30
  switch i16 %7, label %bb36 [
    i16 3, label %bb44
    i16 4, label %bb42
  ]

bb33:                                             ; preds = %bb31
  switch i16 %6, label %bb37 [
    i16 3, label %bb45
    i16 4, label %bb43
  ]

bb34:                                             ; preds = %bb40, %bb27
  %iDataOffset.1.0lane = phi i1 [ true, %bb40 ], [ %14, %bb27 ]
  %18 = phi i24 [ %16, %bb40 ], [ %i_read_data4.0lane, %bb27 ]
  %19 = phi i8 [ %4, %bb40 ], [ 0, %bb27 ]
  %20 = call i32 @hwtHls.bitConcat.i24.i8(i24 %18, i8 %19) #2
  br i1 %iDataOffset.1.0lane, label %bb36, label %bb38

bb35:                                             ; preds = %bb41, %bb44
  %iDataOffset.1.1lane = phi i1 [ true, %bb41 ], [ %35, %bb44 ]
  %21 = phi i24 [ %37, %bb41 ], [ %i_read_data4.1lane, %bb44 ]
  %22 = phi i8 [ %2, %bb41 ], [ 0, %bb44 ]
  %23 = call i32 @hwtHls.bitConcat.i24.i8(i24 %21, i8 %22) #2
  br i1 %iDataOffset.1.1lane, label %bb37, label %bb39

bb36:                                             ; preds = %bb32, %bb34
  %storeLaneVld0.2.0lane = phi i1 [ false, %bb32 ], [ true, %bb34 ]
  %storeLaneData0.2.0lane = phi i32 [ poison, %bb32 ], [ %20, %bb34 ]
  %i_read1.r0.data.reg2mem.1.0lane = phi i16 [ %7, %bb32 ], [ %i_read1.r0.data.reg2mem.2.reg2mem.0, %bb34 ]
  br label %bb44

bb37:                                             ; preds = %bb33, %bb35
  %storeLaneVld0.2.1lane = phi i1 [ false, %bb33 ], [ true, %bb35 ]
  %storeLaneData0.2.1lane = phi i32 [ poison, %bb33 ], [ %23, %bb35 ]
  %i_read1.r0.data.reg2mem.1.1lane = phi i16 [ %6, %bb33 ], [ %i_read1.r0.data.reg2mem.3.ph.0lane, %bb35 ]
  br label %bb45

bb38:                                             ; preds = %bb34, %bb27
  %storeLaneVld0.0.0lane = phi i1 [ true, %bb34 ], [ false, %bb27 ]
  %storeLaneData0.0.0lane = phi i32 [ %20, %bb34 ], [ poison, %bb27 ]
  %iDataOffset.0.0.0lane = phi i1 [ false, %bb34 ], [ true, %bb27 ]
  %"(i_read5).0lane" = call i9 @hwtHls.bitConcat.i8.i1(i8 %5, i1 %10) #2
  %"(i_read5)21.0lane" = call i9 @hwtHls.bitConcat.i8.i1(i8 %4, i1 %i_read1.r0.eof.0lane) #2
  %"(i_read5).mux.0lane" = select i1 %iDataOffset.0.0.0lane, i9 %"(i_read5).0lane", i9 %"(i_read5)21.0lane"
  %i_read_data7.0lane = call i8 @hwtHls.bitRangeGet.i9.i5.i8.0(i9 %"(i_read5).mux.0lane", i5 0) #2
  %24 = zext i8 %i_read_data7.0lane to i32
  br label %bb44

bb39:                                             ; preds = %bb35, %bb44
  %storeLaneVld0.0.1lane = phi i1 [ true, %bb35 ], [ false, %bb44 ]
  %storeLaneData0.0.1lane = phi i32 [ %23, %bb35 ], [ poison, %bb44 ]
  %iDataOffset.0.0.1lane = phi i1 [ false, %bb35 ], [ true, %bb44 ]
  %"(i_read5).1lane" = call i9 @hwtHls.bitConcat.i8.i1(i8 %3, i1 %31) #2
  %"(i_read5)21.1lane" = call i9 @hwtHls.bitConcat.i8.i1(i8 %2, i1 %i_read1.r0.eof.1lane) #2
  %"(i_read5).mux.1lane" = select i1 %iDataOffset.0.0.1lane, i9 %"(i_read5).1lane", i9 %"(i_read5)21.1lane"
  %i_read_data7.1lane = call i8 @hwtHls.bitRangeGet.i9.i5.i8.0(i9 %"(i_read5).mux.1lane", i5 0) #2
  %25 = zext i8 %i_read_data7.1lane to i32
  br label %bb45

bb40:                                             ; preds = %bb27
  br label %bb34

bb41:                                             ; preds = %bb44
  br label %bb35

bb42:                                             ; preds = %bb32
  br label %bb44

bb43:                                             ; preds = %bb33
  br label %bb45

bb44:                                             ; preds = %bb42, %bb36, %bb32, %bb30, %bb38, %bb27
  %.sink.0lane = phi i3 [ 1, %bb42 ], [ -4, %bb36 ], [ 1, %bb32 ], [ 0, %bb30 ], [ 0, %bb38 ], [ %17, %bb27 ]
  %storeLaneVld1.1.ph.0lane = phi i1 [ false, %bb42 ], [ false, %bb36 ], [ false, %bb32 ], [ false, %bb30 ], [ true, %bb38 ], [ false, %bb27 ]
  %storeLaneData1.1.ph.0lane = phi i32 [ poison, %bb42 ], [ poison, %bb36 ], [ poison, %bb32 ], [ poison, %bb30 ], [ %24, %bb38 ], [ poison, %bb27 ]
  %storeLaneVld0.3.ph.0lane = phi i1 [ false, %bb42 ], [ %storeLaneVld0.2.0lane, %bb36 ], [ false, %bb32 ], [ false, %bb30 ], [ %storeLaneVld0.0.0lane, %bb38 ], [ false, %bb27 ]
  %storeLaneData0.3.ph.0lane = phi i32 [ poison, %bb42 ], [ %storeLaneData0.2.0lane, %bb36 ], [ poison, %bb32 ], [ poison, %bb30 ], [ %storeLaneData0.0.0lane, %bb38 ], [ poison, %bb27 ]
  %i_read3.r0.eof.reg2mem.1.ph.0lane = phi i1 [ %i_read3.r0.eof.reg2mem.0.reg2mem.0, %bb42 ], [ %i_read3.r0.eof.reg2mem.0.reg2mem.0, %bb36 ], [ %i_read3.r0.eof.reg2mem.0.reg2mem.0, %bb32 ], [ %i_read3.r0.eof.reg2mem.0.reg2mem.0, %bb30 ], [ %i_read3.r0.eof.reg2mem.0.reg2mem.0, %bb38 ], [ %i_read1.r0.eof.0lane, %bb27 ]
  %i_read3.r0.data.reg2mem.1.ph.0lane = phi i16 [ %i_read3.r0.data.reg2mem.0.reg2mem.0, %bb42 ], [ %i_read3.r0.data.reg2mem.0.reg2mem.0, %bb36 ], [ %i_read3.r0.data.reg2mem.0.reg2mem.0, %bb32 ], [ %i_read3.r0.data.reg2mem.0.reg2mem.0, %bb30 ], [ %i_read3.r0.data.reg2mem.0.reg2mem.0, %bb38 ], [ %7, %bb27 ]
  %i_read1.r0.data.reg2mem.3.ph.0lane = phi i16 [ %7, %bb42 ], [ %i_read1.r0.data.reg2mem.1.0lane, %bb36 ], [ %7, %bb32 ], [ %7, %bb30 ], [ %i_read1.r0.data.reg2mem.2.reg2mem.0, %bb38 ], [ %i_read1.r0.data.reg2mem.2.reg2mem.0, %bb27 ]
  store i3 %.sink.0lane, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %26 = call i66 @hwtHls.bitConcat.i32.i32.i1.i1(i32 %storeLaneData0.3.ph.0lane, i32 %storeLaneData1.1.ph.0lane, i1 %storeLaneVld0.3.ph.0lane, i1 %storeLaneVld1.1.ph.0lane) #2
  %27 = call i64 @hwtHls.bitRangeGet.i66.i8.i64.0(i66 %26, i8 0) #2
  %28 = call i2 @hwtHls.bitRangeGet.i66.i8.i2.64(i66 %26, i8 64) #2
  %29 = xor i1 %i_read1.r0.empty.1lane, true
  %30 = or i1 %i_read1.r0.eof.1lane, %29
  %fewExitSw.sucSel.en..bb4.1lane = icmp eq i16 %i_read1.r0.data.reg2mem.3.ph.0lane, 3
  %31 = and i1 %i_read1.r0.eof.1lane, %i_read1.r0.empty.1lane
  %32 = or i1 %i_read3.r0.eof.reg2mem.1.ph.0lane, %31
  %33 = and i1 %32, %i_read1.r0.empty.1lane
  %"(i_read3).1lane" = call i25 @hwtHls.bitConcat.i16.i8.i1(i16 %i_read3.r0.data.reg2mem.1.ph.0lane, i8 %3, i1 %33) #2
  %i_read_data4.1lane = call i24 @hwtHls.bitRangeGet.i25.i6.i24.0(i25 %"(i_read3).1lane", i6 0) #2
  %34 = xor i1 %32, true
  %spec.select.1lane = call i4 @hwtHls.bitConcat.i3.i1(i3 0, i1 %34) #2
  %35 = icmp eq i4 %spec.select.1lane, 0
  %36 = or i1 %i_read3.r0.eof.reg2mem.1.ph.0lane, %i_read1.r0.eof.1lane
  %"(i_read11).1lane" = call i33 @hwtHls.bitConcat.i16.i16.i1(i16 %i_read3.r0.data.reg2mem.1.ph.0lane, i16 %6, i1 %36) #2
  %37 = call i24 @hwtHls.bitRangeGet.i33.i7.i24.0(i33 %"(i_read11).1lane", i7 0) #2
  %38 = call i3 @hwtHls.bitConcat.i1.i2(i1 %fewExitSw.sucSel.en..bb4.1lane, i2 1) #2
  switch i3 %.sink.0lane, label %bb25 [
    i3 0, label %bb31
    i3 1, label %bb45
    i3 2, label %bb41
    i3 3, label %bb35
    i3 -4, label %bb39
  ]

bb45:                                             ; preds = %bb43, %bb37, %bb33, %bb31, %bb39, %bb44
  %.sink.1lane = phi i3 [ 1, %bb43 ], [ -4, %bb37 ], [ 1, %bb33 ], [ 0, %bb31 ], [ 0, %bb39 ], [ %38, %bb44 ]
  %storeLaneVld1.1.ph.1lane = phi i1 [ false, %bb43 ], [ false, %bb37 ], [ false, %bb33 ], [ false, %bb31 ], [ true, %bb39 ], [ false, %bb44 ]
  %storeLaneData1.1.ph.1lane = phi i32 [ poison, %bb43 ], [ poison, %bb37 ], [ poison, %bb33 ], [ poison, %bb31 ], [ %25, %bb39 ], [ poison, %bb44 ]
  %storeLaneVld0.3.ph.1lane = phi i1 [ false, %bb43 ], [ %storeLaneVld0.2.1lane, %bb37 ], [ false, %bb33 ], [ false, %bb31 ], [ %storeLaneVld0.0.1lane, %bb39 ], [ false, %bb44 ]
  %storeLaneData0.3.ph.1lane = phi i32 [ poison, %bb43 ], [ %storeLaneData0.2.1lane, %bb37 ], [ poison, %bb33 ], [ poison, %bb31 ], [ %storeLaneData0.0.1lane, %bb39 ], [ poison, %bb44 ]
  %i_read3.r0.eof.reg2mem.1.ph.1lane = phi i1 [ %i_read3.r0.eof.reg2mem.1.ph.0lane, %bb43 ], [ %i_read3.r0.eof.reg2mem.1.ph.0lane, %bb37 ], [ %i_read3.r0.eof.reg2mem.1.ph.0lane, %bb33 ], [ %i_read3.r0.eof.reg2mem.1.ph.0lane, %bb31 ], [ %i_read3.r0.eof.reg2mem.1.ph.0lane, %bb39 ], [ %i_read1.r0.eof.1lane, %bb44 ]
  %i_read3.r0.data.reg2mem.1.ph.1lane = phi i16 [ %i_read3.r0.data.reg2mem.1.ph.0lane, %bb43 ], [ %i_read3.r0.data.reg2mem.1.ph.0lane, %bb37 ], [ %i_read3.r0.data.reg2mem.1.ph.0lane, %bb33 ], [ %i_read3.r0.data.reg2mem.1.ph.0lane, %bb31 ], [ %i_read3.r0.data.reg2mem.1.ph.0lane, %bb39 ], [ %6, %bb44 ]
  %i_read1.r0.data.reg2mem.3.ph.1lane = phi i16 [ %6, %bb43 ], [ %i_read1.r0.data.reg2mem.1.1lane, %bb37 ], [ %6, %bb33 ], [ %6, %bb31 ], [ %i_read1.r0.data.reg2mem.3.ph.0lane, %bb39 ], [ %i_read1.r0.data.reg2mem.3.ph.0lane, %bb44 ]
  store i3 %.sink.1lane, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %39 = call i66 @hwtHls.bitConcat.i32.i32.i1.i1(i32 %storeLaneData0.3.ph.1lane, i32 %storeLaneData1.1.ph.1lane, i1 %storeLaneVld0.3.ph.1lane, i1 %storeLaneVld1.1.ph.1lane) #2
  %40 = call i64 @hwtHls.bitRangeGet.i66.i8.i64.0(i66 %39, i8 0) #2
  %41 = call i2 @hwtHls.bitRangeGet.i66.i8.i2.64(i66 %39, i8 64) #2
  %42 = call i132 @hwtHls.bitConcat.i64.i64.i2.i2(i64 %27, i64 %40, i2 %28, i2 %41) #2
  store volatile i132 %42, ptr addrspace(2) %o, align 32
  br label %bb27

bb25:                                             ; preds = %bb27, %bb44
  unreachable
}
"""

        # llvm = llmIrStripInstrucionsUnrelatedToCrash(llvmIr, lambda llvm: self._runTestOpt(llvm))
        # print(str(llvm.main))
        self._test_ll(llvmIr, passKwArgs=dict(
           RunEarlyCSEPass=False,
           RunRomExtractPass=False,
           RunHwtHlsInstCombinePass=False,
           RunTrivialSimplifyCFGPass=False,
           RunSimplifyCFGPass=False,
           RunBitcountMergePass=False,
           )
        )

    def test_multiPhi4(self):
        llvmIr = """\
        define void @test_multiPhi4(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  %bb3.ioFsmStBefore.IoFsmSt = alloca i3, align 1
  br label %bb27

bb27:                                             ; preds = %bb45, %bb0
  %i_read1.r0.data.reg2mem.2.reg2mem.0 = phi i16 [ %i_read1.r0.data.reg2mem.3.ph.1lane, %bb45 ], [ undef, %bb0 ]
  %0 = load i3, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %1 = load volatile i38, ptr addrspace(1) %i, align 8
  %2 = trunc i38 %1 to i1
  %3 = trunc i38 %1 to i16
  %4 = trunc i16 %i_read1.r0.data.reg2mem.2.reg2mem.0 to i3
  switch i3 %0, label %bb25 [
    i3 0, label %bb30
    i3 1, label %bb44
    i3 2, label %bb40
    i3 3, label %bb34
    i3 -4, label %bb38
  ]

bb30:                                             ; preds = %bb27
  br i1 false, label %bb32, label %bb44

bb31:                                             ; preds = %bb44
  br i1 %2, label %bb33, label %bb45

bb32:                                             ; preds = %bb30
  switch i16 0, label %bb36 [
    i16 3, label %bb44
    i16 4, label %bb42
  ]

bb33:                                             ; preds = %bb31
  switch i16 %3, label %bb37 [
    i16 3, label %bb45
    i16 4, label %bb43
  ]

bb34:                                             ; preds = %bb40, %bb27
  br i1 false, label %bb36, label %bb38

bb35:                                             ; preds = %bb44, %bb41
  br i1 false, label %bb37, label %bb39

bb36:                                             ; preds = %bb34, %bb32
  br label %bb44

bb37:                                             ; preds = %bb35, %bb33
  %i_read1.r0.data.reg2mem.1.1lane = phi i16 [ %3, %bb33 ], [ 0, %bb35 ]
  br label %bb45

bb38:                                             ; preds = %bb34, %bb27
  br label %bb44

bb39:                                             ; preds = %bb44, %bb35
  br label %bb45

bb40:                                             ; preds = %bb27
  br label %bb34

bb41:                                             ; preds = %bb44
  br label %bb35

bb42:                                             ; preds = %bb32
  br label %bb44

bb43:                                             ; preds = %bb33
  br label %bb45

bb44:                                             ; preds = %bb42, %bb38, %bb36, %bb32, %bb30, %bb27
  %.sink.0lane = phi i3 [ 1, %bb42 ], [ -4, %bb36 ], [ 1, %bb32 ], [ 0, %bb30 ], [ 0, %bb38 ], [ %4, %bb27 ]
  store i3 %.sink.0lane, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  switch i3 0, label %bb25 [
    i3 0, label %bb31
    i3 1, label %bb45
    i3 2, label %bb41
    i3 3, label %bb35
    i3 -4, label %bb39
  ]

bb45:                                             ; preds = %bb44, %bb43, %bb39, %bb37, %bb33, %bb31
  %i_read1.r0.data.reg2mem.3.ph.1lane = phi i16 [ 0, %bb43 ], [ %i_read1.r0.data.reg2mem.1.1lane, %bb37 ], [ 0, %bb33 ], [ 0, %bb31 ], [ 0, %bb39 ], [ 0, %bb44 ]
  br label %bb27

bb25:                                             ; preds = %bb44, %bb27
  unreachable
}
"""
        # llvm = llmIrStripInstrucionsUnrelatedToCrash(llvmIr, lambda llvm: self._runTestOpt(llvm))
        # print(str(llvm.main))
        self._test_ll(llvmIr, passKwArgs=dict(
            RunEarlyCSEPass=False,
            RunRomExtractPass=False,
            RunHwtHlsInstCombinePass=False,
            RunTrivialSimplifyCFGPass=False,
            RunSimplifyCFGPass=False,
            RunBitcountMergePass=False,
            )
        )

    def test_multiPhi5(self):
        llvmIr = """\
define void @test_multiPhi5(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  %bb3.ioFsmStBefore.IoFsmSt = alloca i3, align 1
  br label %bb27

bb27:                                             ; preds = %bb45, %bb0
  %i_read1.r0.data.reg2mem.2.reg2mem.0 = phi i16 [ %i_read1.r0.data.reg2mem.3.ph.1lane, %bb45 ], [ undef, %bb0 ]
  %0 = load i3, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %1 = load volatile i38, ptr addrspace(1) %i, align 8
  %2 = trunc i38 %1 to i1
  %3 = trunc i38 %1 to i16
  %4 = trunc i16 %i_read1.r0.data.reg2mem.2.reg2mem.0 to i3
  %5 = trunc i3 %0 to i1
  %.sink.0lane = select i1 %5, i3 %4, i3 0
  store i3 %.sink.0lane, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  br label %bb44

bb33:                                             ; preds = %bb44
  switch i16 %3, label %bb37 [
    i16 3, label %bb45
    i16 4, label %bb45
  ]

bb37:                                             ; preds = %bb33
  br label %bb45

bb44:                                             ; preds = %bb27
  br i1 %2, label %bb33, label %bb45

bb45:                                             ; preds = %bb44, %bb37, %bb33, %bb33
  %i_read1.r0.data.reg2mem.3.ph.1lane = phi i16 [ 0, %bb33 ], [ %3, %bb37 ], [ 0, %bb33 ], [ 0, %bb44 ]
  br label %bb27
}
"""
        # llvm = llmIrStripInstrucionsUnrelatedToCrash(llvmIr, lambda llvm: self._runTestOpt(llvm))
        # print(str(llvm.main))
        self._test_ll(llvmIr, passKwArgs=dict(
            RunEarlyCSEPass=False,
            RunRomExtractPass=False,
            RunHwtHlsInstCombinePass=False,
            RunTrivialSimplifyCFGPass=False,
            RunSimplifyCFGPass=False,
            RunBitcountMergePass=False,
            )
        )

    def test_nonBB0DominatedExit0(self):
        llvmIr = """\
        define void @test_nonBB0DominatedExit0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.entry:
          br label %bb.loop0.head

        bb.loop0.head: ; e0
          %e0 = load volatile i1, ptr addrspace(1) %i, align 4
          %c0 = load volatile i2, ptr addrspace(1) %i, align 4
          %c1 = load volatile i1, ptr addrspace(1) %i, align 4
          br i1 %c1, label %bb.sw, label %bb.loop1.head

        bb.sw:  ;bb0                       ; preds = %bb.loop0.head
          switch i2 %c0, label %bb.swUnreachable [
            i2 0, label %bb.swJump0
            i2 1, label %bb.swJump1
            i2 -2, label %bb.swJump2
          ]
        
        bb.swJump1:  ; *                             ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump2:  ; *                           ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump0:  ; *                        ; preds = %bb.sw, %bb.swJump2, %bb.swJump1
          br label %bb.loop1.head
        
        bb.loop1.head:   ; e1                                 ; preds = %bb.loop0.head, %bb.swJump0, %bb.loop1.head
          %e1 = load volatile i1, ptr addrspace(1) %i, align 4
          br i1 %e1, label %bb.loop0.head, label %bb.loop1.head
        
        bb.swUnreachable:  ; *                       ; preds = %bb.sw
          unreachable
        }
        """
        self._test_ll(llvmIr)

    def test_nonBB0DominatedExit0_phiInE1(self):
        llvmIr = """\
        define void @test_nonBB0DominatedExit0_phiInE1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.entry:
          br label %bb.loop0.head

        bb.loop0.head: ; e0
          %e0 = load volatile i1, ptr addrspace(1) %i, align 4
          %c0 = load volatile i2, ptr addrspace(1) %i, align 4
          %c1 = load volatile i1, ptr addrspace(1) %i, align 4
          %v0 = load volatile i2, ptr addrspace(1) %i, align 4
          br i1 %c1, label %bb.sw, label %bb.loop1.head

        bb.sw:  ;bb0                       ; preds = %bb.loop0.head
          switch i2 %c0, label %bb.swUnreachable [
            i2 0, label %bb.swJump0
            i2 1, label %bb.swJump1
            i2 -2, label %bb.swJump2
          ]
        
        bb.swJump1:  ; *                             ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump2:  ; *                           ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump0:  ; *                        ; preds = %bb.sw, %bb.swJump2, %bb.swJump1
          br label %bb.loop1.head
        
        bb.loop1.head:   ; e1                                 ; preds = %bb.loop0.head, %bb.swJump0, %bb.loop1.head
          %phiE1 =  phi i2 [ %v0, %bb.loop0.head ], [ 1, %bb.swJump0 ], [ 2, %bb.loop1.head ]
          store volatile i2 %phiE1, ptr addrspace(2) %o, align 1
          %e1 = load volatile i1, ptr addrspace(1) %i, align 4
          br i1 %e1, label %bb.loop0.head, label %bb.loop1.head
        
        bb.swUnreachable:  ; *                       ; preds = %bb.sw
          unreachable
        }
        """
        self._test_ll(llvmIr)

    def test_nonBB0DominatedExit0_phiInE1UsingE0Val(self):
        llvmIr = """\
        define void @test_nonBB0DominatedExit0_phiInE1UsingE0Val(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.entry:
          br label %bb.loop0.head

        bb.loop0.head: ; e0
          %e0 = load volatile i1, ptr addrspace(1) %i, align 4
          %c0 = load volatile i2, ptr addrspace(1) %i, align 4
          %c1 = load volatile i1, ptr addrspace(1) %i, align 4
          %v0 = load volatile i2, ptr addrspace(1) %i, align 4
          br i1 %c1, label %bb.sw, label %bb.loop1.head

        bb.sw:  ;bb0                       ; preds = %bb.loop0.head
          switch i2 %c0, label %bb.swUnreachable [
            i2 0, label %bb.swJump0
            i2 1, label %bb.swJump1
            i2 -2, label %bb.swJump2
          ]
        
        bb.swJump1:  ; *                             ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump2:  ; *                           ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump0:  ; *                        ; preds = %bb.sw, %bb.swJump2, %bb.swJump1
          br label %bb.loop1.head
        
        bb.loop1.head:   ; e1                                 ; preds = %bb.loop0.head, %bb.swJump0, %bb.loop1.head
          %phiE1 =  phi i2 [ %v0, %bb.loop0.head ], [ 1, %bb.swJump0 ], [ 2, %bb.loop1.head ]
          store volatile i2 %phiE1, ptr addrspace(2) %o, align 1
          %e1 = load volatile i1, ptr addrspace(1) %i, align 4
          br i1 %e1, label %bb.loop0.head, label %bb.loop1.head
        
        bb.swUnreachable:  ; *                       ; preds = %bb.sw
          unreachable
        }
        """
        self._test_ll(llvmIr)

    def test_nonBB0DominatedExit0_phiInE1UsingE0Phi(self):
        llvmIr = """\
        define void @test_nonBB0DominatedExit0_phiInE1UsingE0Phi(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.entry:
          br label %bb.loop0.head

        bb.loop0.head: ; e0
          %phiE0 =  phi i2 [ 0, %bb.entry ], [ 1, %bb.swJump1 ], [ 2, %bb.swJump2 ], [ 3, %bb.loop1.head ]
          %e0 = load volatile i1, ptr addrspace(1) %i, align 4
          %c0 = load volatile i2, ptr addrspace(1) %i, align 4
          %c1 = load volatile i1, ptr addrspace(1) %i, align 4
          br i1 %c1, label %bb.sw, label %bb.loop1.head

        bb.sw:  ;bb0                       ; preds = %bb.loop0.head
          switch i2 %c0, label %bb.swUnreachable [
            i2 0, label %bb.swJump0
            i2 1, label %bb.swJump1
            i2 -2, label %bb.swJump2
          ]
        
        bb.swJump1:  ; *                             ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump2:  ; *                           ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump0:  ; *                        ; preds = %bb.sw, %bb.swJump2, %bb.swJump1
          br label %bb.loop1.head
        
        bb.loop1.head:   ; e1                                 ; preds = %bb.loop0.head, %bb.swJump0, %bb.loop1.head
          %phiE1 =  phi i2 [ %phiE0, %bb.loop0.head ], [ 1, %bb.swJump0 ], [ 2, %bb.loop1.head ]
          store volatile i2 %phiE1, ptr addrspace(2) %o, align 1
          %e1 = load volatile i1, ptr addrspace(1) %i, align 4
          br i1 %e1, label %bb.loop0.head, label %bb.loop1.head
        
        bb.swUnreachable:  ; *                       ; preds = %bb.sw
          unreachable
        }
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_TC)
    # suite = unittest.TestSuite([HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_TC('test_2exits_and_header_and_exit01phis')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
