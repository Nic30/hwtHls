define void @test_tryReducePopcnt_constBits(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %v0 = load volatile i2, ptr addrspace(1) %dataIn, align 1
  %0 = call i2 @llvm.ctpop.i2(i2 %v0)
  %1 = zext i2 %0 to i5
  %res = add i5 %1, 3
  store volatile i5 %res, ptr addrspace(2) %dataOut, align 2
  ret void
}
