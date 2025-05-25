define void @mergeConst(ptr addrspace(2) %o) {
  store volatile i8 33, ptr addrspace(2) %o, align 1
  ret void
}
