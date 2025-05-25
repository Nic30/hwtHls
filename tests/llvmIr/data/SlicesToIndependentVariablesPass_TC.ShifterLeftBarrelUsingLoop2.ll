define void @ShifterLeftBarrelUsingLoop2(ptr addrspace(1) %i, ptr addrspace(2) %o, ptr addrspace(3) %sh) {
BB0:
  br label %BB1

BB1:                                              ; preds = %BB1, %BB0
  %vIn = load volatile i2, ptr addrspace(1) %i, align 1
  %0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %vIn, i2 1) #1
  %vIn_b0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %vIn, i2 0) #1
  %shVal = load volatile i1, ptr addrspace(3) %sh, align 1
  %vOut1 = select i1 %shVal, i1 false, i1 %vIn_b0
  %vOut2 = select i1 %shVal, i1 %vIn_b0, i1 %0
  %1 = call i2 @hwtHls.bitConcat.i1.i1(i1 %vOut1, i1 %vOut2) #1
  store volatile i2 %1, ptr addrspace(2) %o, align 1
  br label %BB1
}
