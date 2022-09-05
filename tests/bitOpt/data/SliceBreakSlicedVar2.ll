define void @mainThread(i32 addrspace(1)* %o) {
mainThread:
  br label %block0

block0:                                           ; preds = %mainThread
  store volatile i32 32, i32 addrspace(1)* %o, align 4
  ret void
}
