define void @mainThread(i32* %o) {
mainThread:
  store volatile i32 3, i32* %o, align 4
  ret void
}
