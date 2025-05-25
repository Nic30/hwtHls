define void @test_whileSize(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
entry:
  br label %mainLoop

mainLoop:                                         ; preds = %read, %entry
  %isChildLoop.whileSize = phi i1 [ false, %entry ], [ %isChildLoopInLatch.whileSize, %read ]
  %size.0 = phi i8 [ 0, %entry ], [ %size.1.inLatch, %read ]
  br i1 %isChildLoop.whileSize, label %whileSize, label %mainLoop.split

mainLoop.split:                                   ; preds = %mainLoop
  %size.0.ne0 = icmp ne i8 %size.0, 0
  br i1 %size.0.ne0, label %preheader, label %read.oldLatch

preheader:                                        ; preds = %mainLoop.split
  br label %whileSize

whileSize:                                        ; preds = %mainLoop, %preheader
  %size.1 = phi i8 [ %size.0, %preheader ], [ %size.0, %mainLoop ]
  store volatile i8 %size.1, ptr addrspace(2) %dataOut, align 1
  %size.1.sub1 = sub i8 %size.1, 1
  %"5" = icmp ne i8 %size.1.sub1, 0
  br i1 %"5", label %read, label %read.loopexit

read.loopexit:                                    ; preds = %whileSize
  br label %read.oldLatch

read.oldLatch:                                    ; preds = %mainLoop.split, %read.loopexit
  %size.new = load volatile i8, ptr addrspace(1) %dataIn, align 1
  br label %read

read:                                             ; preds = %whileSize, %read.oldLatch
  %size.1.inLatch = phi i8 [ %size.1.sub1, %whileSize ], [ %size.new, %read.oldLatch ]
  %isChildLoopInLatch.whileSize = phi i1 [ true, %whileSize ], [ false, %read.oldLatch ]
  br label %mainLoop
}
