define void @test_HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks_tryHoistFromBB1_0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bbentry:
  br label %bbHead

bbHead:                                           ; preds = %bbLatch, %bbentry
  %c = load volatile i1, ptr addrspace(1) %i, align 4
  %v0 = load volatile i1, ptr addrspace(1) %i, align 4
  %v1 = load volatile i8, ptr addrspace(1) %i, align 4
  call void @llvm.assume(i1 %v0), !hwthls.sideeffect.allowhoist !0
  %v1.1 = add nuw i8 %v1, 3
  %0 = xor i1 %c, true
  %1 = zext i1 %0 to i8
  store volatile i8 %1, ptr addrspace(2) %o, align 4
  br i1 %c, label %bbC0, label %bbLatch

bbC0:                                             ; preds = %bbHead
  store volatile i8 %v1.1, ptr addrspace(2) %o, align 4
  br label %bbLatch

bbLatch:                                          ; preds = %bbC0, %bbHead
  br label %bbHead
}
