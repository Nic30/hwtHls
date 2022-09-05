define void @mainThread(i32 addrspace(1)* %i, i32 addrspace(2)* %o) {
mainThread:
  br label %block0

block0:                                           ; preds = %mainThread
  %i0 = load volatile i32, i32 addrspace(1)* %i, align 4
  %"5" = add i32 %i0, 1
  store volatile i32 %"5", i32 addrspace(2)* %o, align 4
  ret void
}
