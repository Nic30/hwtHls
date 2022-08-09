define void @mainThread(i32* %i, i32 addrspace(1)* %o) {
mainThread:
  %i0 = load volatile i32, i32* %i, align 4
  %"5" = add i32 %i0, 1
  %"6" = xor i32 %"5", -1
  store volatile i32 %"6", i32 addrspace(1)* %o, align 4
  ret void
}
