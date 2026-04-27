; ModuleID = 'test'
source_filename = "test"

define void @test_nothingToExtractNoState(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb.0:
  br label %bb.1

bb.1:                                             ; preds = %bb.1, %bb.0
  %v0 = load volatile i8, ptr addrspace(1) %i, align 1
  %v1 = add i8 %v0, 1
  store volatile i8 %v1, ptr addrspace(2) %o, align 1
  br label %bb.1
}
