define void @test_selectSub0(ptr addrspace(1) %a, ptr addrspace(2) %res) {
  %a_read = load volatile i64, ptr addrspace(1) %a, align 4
  %a_read_msb = call i1 @hwtHls.bitRangeGet.i64.i7.i1.63(i64 %a_read, i7 63) #1
  %1 = sub i64 0, %a_read
  %2 = select i1 %a_read_msb, i64 %1, i64 %a_read
  store volatile i64 %2, ptr addrspace(2) %res, align 1
  ret void
}
