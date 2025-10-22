  define void @LoopFuseWithPrequelPass_TC.test_1BBLoop(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
  bb0:
    br label %bb.loop0
  
  bb.loop0:                                    ; preds = %bb.loop0, %bb.loop1, %bb0
    %dataIn_read1.r0 = load volatile i65, ptr addrspace(1) %dataIn, align 16
    %dataIn_read_last6.peel = call i1 @hwtHls.bitRangeGet.i65.i8.i1.64(i65 %dataIn_read1.r0, i8 64) #2
    store volatile i65 %dataIn_read1.r0, ptr addrspace(2) %dataOut, align 16
    br i1 %dataIn_read_last6.peel, label %bb.loop0, label %bb.loop1.preheader
  
  bb.loop1.preheader:                ; preds = %bb.loop0
    br label %bb.loop1
  
  bb.loop1:                          ; preds = %bb.loop1.preheader, %bb.loop1
    %dataIn_read4.r0 = load volatile i65, ptr addrspace(1) %dataIn, align 16
    %dataIn_read_last6.1 = call i1 @hwtHls.bitRangeGet.i65.i8.i1.64(i65 %dataIn_read4.r0, i8 64) #2
    store volatile i65 %dataIn_read4.r0, ptr addrspace(2) %dataOut, align 16
    br i1 %dataIn_read_last6.1, label %bb.loop0, label %bb.loop1
  }