; ModuleID = 'test'
source_filename = "test"

define void @test_nothingToExtract(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb.0:
  br label %bb.1

bb.1:                                             ; preds = %bb.1, %bb.0
  %i0 = load volatile i1, ptr addrspace(1) %i, align 1
  store volatile i1 %i0, ptr addrspace(2) %o, align 1
  br label %bb.1
}
