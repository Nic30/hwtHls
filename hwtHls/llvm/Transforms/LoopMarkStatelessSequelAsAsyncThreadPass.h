#pragma once

#include <hwtHls/llvm/Transforms/LoopMarkStatelessPrequelAsAsyncThreadPass.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/LoopAnalysisManager.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  Extract stateless sequel from selected loop into a separated thread.
 *  The stateless sequel is a part of the code which does not affect the
 *  loop state or on any other form of state. Simplified this means that the
 *  extracted code does not appear in header PHIs and memory which has read and
 *  write or io if not all its instruction can be extracted.
 *
 *  :see: :class:`LoopMarkStatelessPrequelAsAsyncThreadPass`
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
 *               if (x == 0 && i == 0)
 *                  fn1();
 *               @hwtHls.thread.split.end.t1(), !hwtHls.thread.section !1;
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
 *       !1 = distinct !{!"slsequel", i1 true, i1 false, i1 true, i1 true,
 *	                      i64 0, i64 0}
 *
 *       // then later after ThreadExtractPass
 *       void main.slprequel(o) {
 *           for (int i = 0; i < 10; ++i) {
 *              *o = i;
 *           }
 *       }
 *       void main(o) {
 *           while (1) {
 *               auto i = *o;
 *               auto x = fn0();
 *               if (x == 0 && i == 0)
 *                  fn1();
 *           }
 *       }
 *
 */
class LoopMarkStatelessSequelAsAsyncThreadPass
	: public LoopMarkPassPrototype,
	  public llvm::PassInfoMixin<LoopMarkStatelessSequelAsAsyncThreadPass> {
public:
	static const std::string METADATA_NAME;
	static const std::string METADATA_NAME_followup;
	
	LoopMarkStatelessSequelAsAsyncThreadPass(bool applyOnAll=false): LoopMarkPassPrototype(applyOnAll) {
	}
	bool findCompatibleInstructions(
		llvm::LoopInfo &LI, llvm::Loop &L,
		std::unordered_set<llvm::Instruction *> &incompatible,
		llvm::SetVector<llvm::Instruction *> &compatible);
	virtual bool processLoop(llvm::LoopInfo &LI, llvm::Loop &L,
							 llvm::DomTreeUpdater &DTU,
							 llvm::MemorySSAUpdater *MSSAU) override;
};
}
