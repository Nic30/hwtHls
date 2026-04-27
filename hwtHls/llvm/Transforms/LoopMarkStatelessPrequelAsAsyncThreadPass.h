#pragma once

#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/LoopAnalysisManager.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/PassManager.h>
#include <unordered_set>

namespace llvm {
class LPMUpdater;
class Loop;
}

namespace hwtHls {

/**
 *  Extract stateless prequel from selected loop into a separated thread.
 *  The stateless prequel is a part of the code which does not depend on the
 *  loop state or on any other form of state. Simplified this means that the
 *  extracted code does not depend on header PHIs and memory which has
 *  write and read or io if not all its instruction can be extracted.
 *
 *  :see: :class:`LoopMarkStatelessSequelAsAsyncThread`
 *  :note: :class:`ThreadExtractIoFsmPass` extract also the parent loop state
 *          private to IO while :class:`LoopMarkStatelessPrequelAsAsyncThreadPass` keeps
 *          it in original place
 *
 *  .. code-block::cpp
 *
 *       void main() {
 *           for (int i = 0; i < 10; ++i) {
 *               auto x = fn0();
 *               if (x == 0 && i == 0)
 *                  fn1();
 *           }
 *       }
 *       // to
 *       void main() {
 *           for (int i = 0; i < 10; ++i) {
 *               @hwtHls.thread.split.begin.t1(), !hwtHls.thread.section !1;
 *               auto x = fn0();
 *               auto o = x == 0;
 *               @hwtHls.thread.split.end.t1(), !hwtHls.thread.section !1;
 *               if (o && i == 0)
 *                  fn1();
 *           }
 *       }
 *       // :note: ThreadSplitSectionMetadata
 *       //         std::string name;
 *       //         bool aggregateInputs;
 *       //         bool beginMayBeAsync;
 *       //         bool aggregateOutputs;
 *       //         bool endMayBeAsync;
 *       //         size_t inputBufferCapacity;
 *       //         size_t outputBufferCapacity;
 *       !1 = distinct !{!"slprequel", i1 true, i1 true, i1 true, i1 false,
 *	                      i64 0, i64 0}
 *
 *       // then later after ThreadExtractPass
 *       void main.slprequel(o) {
 *	         while(1) {
 *               auto x = fn0();
 *               *o = x == 0;
 *           }
 *       }
 *       void main(o) {
 *           for (int i = 0; i < 10; ++i) {
 *               if (*o && i == 0)
 *                  fn1();
 *           }
 *       }
 *
 */
class LoopMarkPassPrototype {
public:
	const bool applyOnAll;
	LoopMarkPassPrototype(bool applyOnAll): applyOnAll(applyOnAll) {
	}
	virtual bool processLoop(llvm::LoopInfo &LI, llvm::Loop &L,
							 llvm::DomTreeUpdater &DTU,
							 llvm::MemorySSAUpdater *MSSAU) = 0;
	llvm::PreservedAnalyses run(llvm::Loop &L, llvm::LoopAnalysisManager &AM,
								llvm::LoopStandardAnalysisResults &AR,
								llvm::LPMUpdater &U);
	llvm::PreservedAnalyses run(llvm::Module &M,
								llvm::ModuleAnalysisManager &AM);
	/*
	 * :param isSelectedFn: predicate specifying if instruction is in selected
	 *        region
	 * :param IOcompatibility:  key is Argument* or AllocaInst*, the
	 *     value is true if all LoadInst/StoreInst accessing this pointer
	 *     (or its GEP) are in selected region
	 */
	static void checkIoIsPrivateToSelectedRegion(
		llvm::LoopInfo &LI, llvm::Loop &L, llvm::BasicBlock &BB0,
		std::function<bool(llvm::Instruction &)> isSelectedFn,
		llvm::DenseMap<llvm::Value *, bool> &IOcompatibility);
	static void
	findIncopatibleIoInstr(llvm::LoopInfo &LI, llvm::Loop &L,
						   std::unordered_set<llvm::Instruction *> compatible,
						   std::unordered_set<llvm::Instruction *> incompatible,
						   llvm::DenseMap<llvm::Value *, bool> IOcompatibility);
	static void walkAllUserGepLoadStoreInstructions(
		llvm::Value *io, std::function<void(llvm::Instruction &)> fn);
	static llvm::Value *findIoDef(llvm::Value *io);
	static bool allLoadStoreInstrAreCompatible(
		llvm::Value *io,
		std::function<bool(llvm::Instruction &)> isCompatibleFn);
};

class LoopMarkStatelessPrequelAsAsyncThreadPass
	: public LoopMarkPassPrototype,
	  public llvm::PassInfoMixin<LoopMarkStatelessPrequelAsAsyncThreadPass> {
public:
	LoopMarkStatelessPrequelAsAsyncThreadPass(bool applyOnAll=false): LoopMarkPassPrototype(applyOnAll) {
	}
	static const std::string METADATA_NAME;
	static const std::string METADATA_NAME_followup;
	
	virtual bool processLoop(llvm::LoopInfo &LI, llvm::Loop &L,
							 llvm::DomTreeUpdater &DTU,
							 llvm::MemorySSAUpdater *MSSAU) override;
};

}
