#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC

class LoopFlattenUsingIfPass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return llvm._testLoopFlattenUsingIfPass()

    def test_notingToReduce(self):
        llvmIr0 = """
        define void @test_notingToReduce() {
          ret void
        }
        """
        self._test_ll(llvmIr0)

    def test_whileWhile(self):
        # v = 0
        # while (*c) {
        #   v += 1;
        #   while (*c)
        #     v += 16;
        #   *o = v;
        # }
        llvmIr0 = """
        define void @test_whileWhile(ptr addrspace(1) %c, ptr addrspace(2) %o) {
          entry:
            br label %bb.wh
          
          bb.wh:
            %v0 = phi i8 [0, %entry], [%v2, %bb.fn1]
            %c0 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c0, label %bb.wh.body, label %bb.wh.exit
          bb.wh.body:
            br label %bb.fn0
          bb.fn0:
            %v1 = add i8 %v0, 1
            br label %bb.wh.wh 
          bb.wh.wh:
            %v2 = phi i8 [%v1, %bb.fn0], [%v3, %bb.wh.wh.body]
            %c1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c1, label %bb.wh.wh.body, label %bb.fn1
          bb.wh.wh.body:
            %v3 = add i8 %v2, 16
            br label %bb.wh.wh, !llvm.loop !0
          bb.fn1:
            store volatile i8 %v2, ptr addrspace(2) %o, align 1
            br label %bb.wh
          
          bb.wh.exit:
            ret void
        }
        
        !0 = distinct !{!0, !1}
        !1 = !{!"hwthls.loop.flattenusingif.enable", i32 1}
        """
        self._test_ll(llvmIr0)

    def test_whileWhile2xNested(self):
        # v = 0
        # while (*c) {
        #   v += 1;
        #   while (*c)
        #     v += 16;
        #     while (*c)
        #       v += 32;
        #     *o = v; 
        #   *o = v;
        # }
        llvmIr0 = """
        define void @test_whileWhile2xNested(ptr addrspace(1) %c, ptr addrspace(2) %o) {
          entry:
            br label %bb.wh

          bb.wh:
            %v0 = phi i8 [0, %entry], [%v2, %bb.fn1]
            %c0 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c0, label %bb.wh.body, label %bb.wh.exit
          bb.wh.body:
            br label %bb.fn0
          bb.fn0:
            %v1 = add i8 %v0, 1
            br label %bb.wh1 
          bb.wh1:
            %v2 = phi i8 [%v1, %bb.fn0], [%v2.2, %bb.wh1.body.end]
            %c1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c1, label %bb.wh1.body, label %bb.fn1
          bb.wh1.body:
            %v3 = add i8 %v2, 16
            br label %bb.wh2
            
            bb.wh2:
               %v2.2 = phi i8 [%v3, %bb.wh1.body], [%v3.2, %bb.wh2.body]
               %c1.2 = load volatile i1, ptr addrspace(1) %c, align 1
               br i1 %c1.2, label %bb.wh2.body, label %bb.wh1.body.end
            bb.wh2.body:
               %v3.2 = add i8 %v2, 16
               br label %bb.wh2, !llvm.loop !0
          
          bb.wh1.body.end:
            store volatile i8 %v2.2, ptr addrspace(2) %o, align 1
            br label %bb.wh1, !llvm.loop !0
        
          bb.fn1:
            store volatile i8 %v2, ptr addrspace(2) %o, align 1
            br label %bb.wh
          
          bb.wh.exit:
            ret void
        }
        
        !0 = distinct !{!0, !1}
        !1 = !{!"hwthls.loop.flattenusingif.enable", i32 1}
        """
        self._test_ll(llvmIr0)

    def test_whileGuardedWhile(self):
        # v = 0
        # while (*c) {
        #   v += 1;
        #   if (*c) {
        #      while (*c)
        #        v += 16;
        #   }
        #   *o = v;
        # }
        llvmIr0 = """
        define void @test_whileGuardedWhile(ptr addrspace(1) %c, ptr addrspace(2) %o, ptr addrspace(3) %i) {
          entry:
            br label %bb.wh
          
          bb.wh:
            %v0 = phi i8 [0, %entry], [%v4, %bb.fn1]
            %c0 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c0, label %bb.wh.body, label %bb.wh.exit
          bb.wh.body:
            br label %bb.fn0
          bb.fn0:
            %v1 = add i8 %v0, 1
            %beginTmp = load volatile i8, ptr addrspace(3) %i, align 1
            br label %bb.wh.if
          bb.wh.if:
            %cIf = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %cIf, label %bb.wh.wh, label %bb.fn1
          bb.wh.wh:
            %v2 = phi i8 [%v1, %bb.wh.if], [%v3, %bb.wh.wh.body]
            %c1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c1, label %bb.wh.wh.body, label %bb.fn1
          bb.wh.wh.body:
            %v3 = add i8 %v2, 16
            br label %bb.wh.wh, !llvm.loop !0
          bb.fn1:
            %v4 = phi i8 [%v1, %bb.wh.if], [%v2, %bb.wh.wh]
            store volatile i8 %v4, ptr addrspace(2) %o, align 1
            store volatile i8 %beginTmp, ptr addrspace(2) %o, align 1
            br label %bb.wh
          
          bb.wh.exit:
            ret void
        }
        
        !0 = distinct !{!0, !1}
        !1 = !{!"hwthls.loop.flattenusingif.enable", i32 1}
        """
        self._test_ll(llvmIr0)

    def test_whileGuardedWhile2xLinear(self):
        # v = 0
        # while (*c) {
        #   v += 1;
        #   if (*c) {
        #      while (*c)
        #        v += 16;
        #   }
        #   if (*c) {
        #      while (*c)
        #        v += 16;
        #   }
        #   *o = v;
        # }
        llvmIr0 = """
        define void @test_whileGuardedWhile2xLinear(ptr addrspace(1) %c, ptr addrspace(2) %o, ptr addrspace(3) %i) {
          entry:
            br label %bb.wh
          
          bb.wh:
            %v0 = phi i8 [0, %entry], [%v4, %bb.fn1]
            %c0 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c0, label %bb.wh.body, label %bb.wh.exit
          bb.wh.body:
            br label %bb.fn0
          bb.fn0:
            %v1 = add i8 %v0, 1
            %beginTmp = load volatile i8, ptr addrspace(3) %i, align 1
            br label %bb.wh.if
          
          bb.wh.if:
            %cIf = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %cIf, label %bb.wh.wh, label %bb.wh1.if
          bb.wh.wh:
            %v2 = phi i8 [%v1, %bb.wh.if], [%v3, %bb.wh.wh.body]
            %c1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c1, label %bb.wh.wh.body, label %bb.wh1.if
          bb.wh.wh.body:
            %v3 = add i8 %v2, 16
            br label %bb.wh.wh, !llvm.loop !0
            
          bb.wh1.if:
            %v1.1 = phi i8 [%v1, %bb.wh.if], [%v2, %bb.wh.wh]
            %cIf.1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %cIf.1, label %bb.wh1.wh, label %bb.fn1
          bb.wh1.wh:
            %v2.1 = phi i8 [%v1.1, %bb.wh1.if], [%v3.1, %bb.wh1.wh.body]
            %c1.1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c1.1, label %bb.wh1.wh.body, label %bb.fn1
          bb.wh1.wh.body:
            %v3.1 = add i8 %v2.1, 16
            br label %bb.wh1.wh, !llvm.loop !0
            
          bb.fn1:
            %v4 = phi i8 [%v1.1, %bb.wh1.if], [%v2.1, %bb.wh1.wh]
            store volatile i8 %v4, ptr addrspace(2) %o, align 1
            store volatile i8 %beginTmp, ptr addrspace(2) %o, align 1
            br label %bb.wh
          
          bb.wh.exit:
            ret void
        }

        !0 = distinct !{!0, !1}
        !1 = !{!"hwthls.loop.flattenusingif.enable", i32 1}
        """
        self._test_ll(llvmIr0)

    def test_whileGuardedWhile2xLinear_firstNestedLoopFlattened(self):
        # :note: test_whileGuardedWhile2xLinear with first nested loop flattened
        llvmIr0 = """\
        define void @test_whileGuardedWhile2xLinear_firstNestedLoopFlattened(ptr addrspace(1) %c, ptr addrspace(2) %o, ptr addrspace(3) %i) {
        entry:
          br label %bb.wh
        
        bb.wh:                                            ; preds = %bb.fn1, %entry
          %beginTmp2.0 = phi i8 [ undef, %entry ], [ %beginTmp2.3, %bb.fn1 ]
          %isChildLoop.bb.wh.wh = phi i1 [ false, %entry ], [ %isChildLoopInLatch.bb.wh.wh, %bb.fn1 ]
          %v0 = phi i8 [ 0, %entry ], [ %v2.inLatch, %bb.fn1 ]
          br i1 %isChildLoop.bb.wh.wh, label %bb.wh.wh, label %bb.wh.split
        
        bb.wh.split:                                      ; preds = %bb.wh
          %c0 = load volatile i1, ptr addrspace(1) %c, align 1
          br i1 %c0, label %bb.wh.body, label %bb.wh.exit
        
        bb.wh.body:                                       ; preds = %bb.wh.split
          br label %bb.fn0
        
        bb.fn0:                                           ; preds = %bb.wh.body
          %v1 = add i8 %v0, 1
          %beginTmp = load volatile i8, ptr addrspace(3) %i, align 1
          br label %bb.wh.if
        
        bb.wh.if:                                         ; preds = %bb.fn0
          %cIf = load volatile i1, ptr addrspace(1) %c, align 1
          br i1 %cIf, label %bb.wh.wh.preheader, label %bb.wh1.if
        
        bb.wh.wh.preheader:                               ; preds = %bb.wh.if
          br label %bb.wh.wh
        
        bb.wh.wh:                                         ; preds = %bb.wh, %bb.wh.wh.preheader
          %beginTmp2.1 = phi i8 [ %beginTmp2.0, %bb.wh ], [ %beginTmp, %bb.wh.wh.preheader ]
          %v2 = phi i8 [ %v1, %bb.wh.wh.preheader ], [ %v0, %bb.wh ]
          %c1 = load volatile i1, ptr addrspace(1) %c, align 1
          br i1 %c1, label %bb.wh.wh.body, label %bb.wh1.if.loopexit
        
        bb.wh.wh.body:                                    ; preds = %bb.wh.wh
          %v3 = add i8 %v2, 16
          br label %bb.fn1
        
        bb.wh1.if.loopexit:                               ; preds = %bb.wh.wh
          %v2.lcssa = phi i8 [ %v2, %bb.wh.wh ]
          br label %bb.wh1.if
        
        bb.wh1.if:                                        ; preds = %bb.wh1.if.loopexit, %bb.wh.if
          %beginTmp2.2 = phi i8 [ %beginTmp2.1, %bb.wh1.if.loopexit ], [ %beginTmp, %bb.wh.if ]
          %v1.1 = phi i8 [ %v1, %bb.wh.if ], [ %v2.lcssa, %bb.wh1.if.loopexit ]
          %cIf.1 = load volatile i1, ptr addrspace(1) %c, align 1
          br i1 %cIf.1, label %bb.wh1.wh.preheader, label %bb.fn1.oldLatch
        
        bb.wh1.wh.preheader:                              ; preds = %bb.wh1.if
          br label %bb.wh1.wh
        
        bb.wh1.wh:                                        ; preds = %bb.wh1.wh.preheader, %bb.wh1.wh.body
          %v2.1 = phi i8 [ %v3.1, %bb.wh1.wh.body ], [ %v1.1, %bb.wh1.wh.preheader ]
          %c1.1 = load volatile i1, ptr addrspace(1) %c, align 1
          br i1 %c1.1, label %bb.wh1.wh.body, label %bb.fn1.loopexit
        
        bb.wh1.wh.body:                                   ; preds = %bb.wh1.wh
          %v3.1 = add i8 %v2.1, 16
          br label %bb.wh1.wh, !llvm.loop !0
        
        bb.fn1.loopexit:                                  ; preds = %bb.wh1.wh
          %v2.1.lcssa = phi i8 [ %v2.1, %bb.wh1.wh ]
          br label %bb.fn1.oldLatch
        
        bb.fn1.oldLatch:                                  ; preds = %bb.wh1.if, %bb.fn1.loopexit
          %v4 = phi i8 [ %v1.1, %bb.wh1.if ], [ %v2.1.lcssa, %bb.fn1.loopexit ]
          store volatile i8 %v4, ptr addrspace(2) %o, align 1
          store volatile i8 %beginTmp2.2, ptr addrspace(2) %o, align 1
          br label %bb.fn1
        
        bb.fn1:                                           ; preds = %bb.wh.wh.body, %bb.fn1.oldLatch
          %beginTmp2.3 = phi i8 [ %beginTmp2.1, %bb.wh.wh.body ], [ %beginTmp2.2, %bb.fn1.oldLatch ]
          %v2.inLatch = phi i8 [ %v3, %bb.wh.wh.body ], [ %v4, %bb.fn1.oldLatch ]
          %isChildLoopInLatch.bb.wh.wh = phi i1 [ true, %bb.wh.wh.body ], [ false, %bb.fn1.oldLatch ]
          br label %bb.wh
        
        bb.wh.exit:                                       ; preds = %bb.wh.split
          ret void
        }
        
        !0 = distinct !{!0, !1}
        !1 = !{!"hwthls.loop.flattenusingif.enable", i32 1}
        """
        
        self._test_ll(llvmIr0)

    def test_whileGuardedWhile2xGuadNested(self):
        # v = 0
        # while (*c) {
        #   v += 1;
        #   if (*c) {
        #      while (*c)
        #        v += 16;
        #   
        #      if (*c) {
        #         while (*c)
        #           v += 16;
        #      }
        #   }
        #   *o = v;
        # }
        llvmIr0 = """
        define void @test_whileGuardedWhile2xGuadNested(ptr addrspace(1) %c, ptr addrspace(2) %o, ptr addrspace(3) %i) {
          entry:
            br label %bb.wh
          
          bb.wh:
            %v0 = phi i8 [0, %entry], [%v4, %bb.fn1]
            %c0 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c0, label %bb.wh.body, label %bb.wh.exit
          bb.wh.body:
            br label %bb.fn0
          bb.fn0:
            %v1 = add i8 %v0, 1
            %beginTmp = load volatile i8, ptr addrspace(3) %i, align 1
            br label %bb.wh.if
          
          bb.wh.if:
            %cIf = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %cIf, label %bb.wh.wh, label %bb.fn1
          bb.wh.wh:
            %v2 = phi i8 [%v1, %bb.wh.if], [%v3, %bb.wh.wh.body]
            %c1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c1, label %bb.wh.wh.body, label %bb.wh1.if
          bb.wh.wh.body:
            %v3 = add i8 %v2, 16
            br label %bb.wh.wh, !llvm.loop !0
            
          bb.wh1.if:
            %v1.1 = phi i8 [%v2, %bb.wh.wh]
            %cIf.1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %cIf.1, label %bb.wh1.wh, label %bb.fn1
          bb.wh1.wh:
            %v2.1 = phi i8 [%v1.1, %bb.wh1.if], [%v3.1, %bb.wh1.wh.body]
            %c1.1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c1.1, label %bb.wh1.wh.body, label %bb.fn1
          bb.wh1.wh.body:
            %v3.1 = add i8 %v2.1, 16
            br label %bb.wh1.wh, !llvm.loop !0
            
          bb.fn1:
            %v4 = phi i8 [%v1, %bb.wh.if], [%v1.1, %bb.wh1.if], [%v2.1, %bb.wh1.wh]
            store volatile i8 %v4, ptr addrspace(2) %o, align 1
            store volatile i8 %beginTmp, ptr addrspace(2) %o, align 1
            br label %bb.wh
          
          bb.wh.exit:
            ret void
        }

        !0 = distinct !{!0, !1}
        !1 = !{!"hwthls.loop.flattenusingif.enable", i32 1}
        """
        self._test_ll(llvmIr0)

    def test_whileDowhile(self):
        # while (parentCond()) {
        #     fn0();
        #     do {
        #         childBody();
        #     } while (childCond());
        #     fn1();
        # }
        # 
        
        llvmIr0 = """
        define void @test_whileDowhile(ptr addrspace(1) %c, ptr addrspace(2) %o) {
          entry:
            br label %bb.wh
          
          bb.wh:
            %v0 = phi i8 [0, %entry], [%v2, %bb.fn1]
            %c0 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c0, label %bb.wh.body, label %bb.wh.exit
          bb.wh.body:
            br label %bb.fn0
          bb.fn0:
            %v1 = add i8 %v0, 1
            br label %bb.wh.wh 
          bb.wh.wh:
            %v2 = phi i8 [%v1, %bb.fn0], [%v3, %bb.wh.wh.body]
            br label %bb.wh.wh.body
          bb.wh.wh.body:
            %v3 = add i8 %v2, 16
            %c1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c1, label %bb.wh.wh, label %bb.fn1, !llvm.loop !0
            
          bb.fn1:
            store volatile i8 %v2, ptr addrspace(2) %o, align 1
            br label %bb.wh
          
          bb.wh.exit:
            ret void
        }

        !0 = distinct !{!0, !1}
        !1 = !{!"hwthls.loop.flattenusingif.enable", i32 1}
        """
        self._test_ll(llvmIr0)
       

    def test_dowhileWhile(self):
        # do {
        #     fn0();
        #     while (*c)
        #         childBody();
        #     fn1();
        # } while (parentCond());
        
        llvmIr0 = """
        define void @test_dowhileWhile(ptr addrspace(1) %c, ptr addrspace(2) %o) {
          entry:
            br label %bb.wh

          bb.wh:
            %v0 = phi i8 [0, %entry], [%v2, %bb.fn1]
            br label %bb.fn0
          bb.fn0:
            %v1 = add i8 %v0, 1
            br label %bb.wh.wh 
          bb.wh.wh:
            %v2 = phi i8 [%v1, %bb.fn0], [%v3, %bb.wh.wh.body]
            %c1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c1, label %bb.wh.wh.body, label %bb.fn1
          bb.wh.wh.body:
            %v3 = add i8 %v2, 16
            br label %bb.wh.wh, !llvm.loop !0
          bb.fn1:
            store volatile i8 %v2, ptr addrspace(2) %o, align 1
            %c0 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c0, label %bb.wh, label %bb.wh.exit
          
          bb.wh.exit:
            ret void
        }

        !0 = distinct !{!0, !1}
        !1 = !{!"hwthls.loop.flattenusingif.enable", i32 1}
        """
        self._test_ll(llvmIr0)
    
    
    def test_dowhileDowhile(self):
        # do {
        #     fn0();
        #     do {
        #         childBody();
        #     } while (childCond());
        #     fn1();
        # } while (parentCond());

        llvmIr0 = """
        define void @test_dowhileDowhile(ptr addrspace(1) %c, ptr addrspace(2) %o) {
          entry:
            br label %bb.wh

          bb.wh:
            %v0 = phi i8 [0, %entry], [%v2, %bb.fn1]
            br label %bb.fn0
          bb.fn0:
            %v1 = add i8 %v0, 1
            br label %bb.wh.wh 
          bb.wh.wh:
            %v2 = phi i8 [%v1, %bb.fn0], [%v3, %bb.wh.wh.body]
            br label %bb.wh.wh.body
          bb.wh.wh.body:
            %v3 = add i8 %v2, 16
            %c1 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c1, label %bb.wh.wh, label %bb.fn1, !llvm.loop !0
          bb.fn1:
            store volatile i8 %v2, ptr addrspace(2) %o, align 1
            %c0 = load volatile i1, ptr addrspace(1) %c, align 1
            br i1 %c0, label %bb.wh, label %bb.wh.exit
          
          bb.wh.exit:
            ret void
        }

        !0 = distinct !{!0, !1}
        !1 = !{!"hwthls.loop.flattenusingif.enable", i32 1}
        """
        self._test_ll(llvmIr0)
    
    
    def test_whileSize(self):
        # size = 0
        # while True:
        #     # mainLoop
        #     while size != 0:
        #         # hileSize
        #         *size = self.dataOut
        #         size = size - 1
        #     
        #     # read
        #     size = *dataIn
        # 
        llvmIr0 = """
        define void @test_whileSize(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        entry:
          br label %mainLoop
        
        mainLoop:
          %size.0 = phi i8 [ 0, %entry ], [ %size.new, %read ]
          %size.0.ne0 = icmp ne i8 %size.0, 0
          br i1 %size.0.ne0, label %preheader, label %read
        
        preheader:
          br label %whileSize
        
        whileSize:
          %size.1 = phi i8 [ %size.1.sub1, %whileSize ], [ %size.0, %preheader ]
          store volatile i8 %size.1, ptr addrspace(2) %dataOut, align 1
          %size.1.sub1 = sub i8 %size.1, 1
          %"5" = icmp ne i8 %size.1.sub1, 0
          br i1 %"5", label %whileSize, label %read.loopexit, !llvm.loop !0
        
        read.loopexit:
          br label %read
        
        read:
          %size.new = load volatile i8, ptr addrspace(1) %dataIn, align 1
          br label %mainLoop
        }

        !0 = distinct !{!0, !1}
        !1 = !{!"hwthls.loop.flattenusingif.enable", i32 1}
        """
        self._test_ll(llvmIr0)
    
    

if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([LoopFlattenUsingIfPass_TC('test_dowhileDowhile')])
    suite = testLoader.loadTestsFromTestCase(LoopFlattenUsingIfPass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
