define void @mainThread(i32 addrspace(1)* %o) {
mainThread:
  store volatile i32 32, i32 addrspace(1)* %o, align 4
  ret void
}
