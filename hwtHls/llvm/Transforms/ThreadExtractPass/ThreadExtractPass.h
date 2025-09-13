#pragma once

#include <llvm/IR/PassManager.h>
#include <string>
#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractorIoArgUtils.h>

namespace llvm {
class Function;
class LoopInfo;
class DomTreeUpdater;
class AssumptionCache;
}

namespace hwtHls {

struct ThreadSplitSectionMetadata;

/**
 * A pass which extract selected region as a thread-like Function
 *
 * The threads are first extracted as if it was a generic call of the function function with extracted code.
 * Then the call is removed and argument handling is rewritten to thread paradigm.
 * Unlike call, the thread does not pass arguments trough CallInst arguments but trough channels.
 * The channel is represented as pointer. Before extracted sections, the store to this pointer is constructed
 * and the load is constructed in extracted section.
 *
 * The extracted section is wrapped in infinite loop which reads inputs and produces outputs.
 * The original function may be rewritten to add IO argument to function type, because FunctionType is immutable.
 *
 *
 * define void @t0.mainThread(ptr addrspace(1) %dataOut0, ptr addrspace(2) %dataOut1) !hwtHls.io !1 {
 * bb0:
 *   br label %bb.mainLoop
 *
 * bb.mainLoop:                                      ; preds = %bb0, %bb.mainLoop
 *   store volatile i8 0, ptr addrspace(1) %dataOut0, align 1
 *   call void @hwtHls.thread.split.begin.t1(i1 true, i1 true) #1
 *   store volatile i8 1, ptr addrspace(2) %dataOut1, align 1
 *   call void @hwtHls.thread.split.end.t1(i1 true, i1 true) #1
 *   br label %bb.mainLoop
 * }
 *
 * to:
 * define void @t0.mainThread(ptr addrspace(1) %dataOut0) !hwtHls.io !1 {
 * bb0:
 *   br label %bb.mainLoop.threadSplit.begint1
 *
 * bb.mainLoop.threadSplit.begint1:                  ; preds = %bb.mainLoop.threadSplit.end.t1, %bb0
 *   store volatile i8 0, ptr addrspace(1) %dataOut0, align 1
 *   br label %threadSplitCodeRepl
 *
 * threadSplitCodeRepl:                              ; preds = %bb.mainLoop.threadSplit.begint1
 *   br label %bb.mainLoop.threadSplit.end.t1
 *
 * bb.mainLoop.threadSplit.end.t1:                   ; preds = %threadSplitCodeRepl
 *   br label %bb.mainLoop.threadSplit.begint1
 * }
 *
 * define internal void @t0.mainThread.threadSplit(ptr addrspace(1) %dataOut1) !hwtHls.io !1 {
 * newFuncRoot:
 *   br label %bb.mainLoop
 *
 * bb.mainLoop:                                      ; preds = %newFuncRoot
 *   store volatile i8 1, ptr %dataOut1, align 1
 *   br label %bb.mainLoop.threadSplit.end.t1.exitStub
 *
 * bb.mainLoop.threadSplit.end.t1.exitStub:          ; preds = %bb.mainLoop
 *   ret void
 * }
 *
 */
class ThreadExtractPass: public llvm::PassInfoMixin<ThreadExtractPass> {
public:
	llvm::PreservedAnalyses run(llvm::Module &M,
			llvm::ModuleAnalysisManager &AM);

	bool extractSectionAsHwHlsThread(llvm::Function &Func, llvm::LoopInfo &LI,
			llvm::DomTreeUpdater &DTU, llvm::AssumptionCache *AC,
			const ThreadSplitSectionMetadata &cfg,
			const llvm::SmallVector<llvm::BasicBlock*> &Blocks,
			bool extractedIsInLoop,
			llvm::SmallVector<ArgToAddToParentFn> &argsToAddToParentFn);

};

}
