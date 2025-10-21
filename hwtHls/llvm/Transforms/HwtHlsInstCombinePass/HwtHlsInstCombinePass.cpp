#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePass.h>

#include <llvm/Support/DebugCounter.h>

#include <llvm/Analysis/InstructionSimplify.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>
#include <llvm/ADT/Statistic.h>

//#undef LLVM_DEBUG
//#define LLVM_DEBUG(x) x

using namespace llvm;

STATISTIC(NumWorklistIterations,
		"Number of instruction combining iterations performed");

namespace hwtHls {

HwtHlsInstCombinePass::HwtHlsInstCombinePass(HwtHlsInstCombinePassOptions Options): Options(Options) {
}

const std::string HwtHlsInstCombinePass::metadataName_mergableFunction_statePlusMaskedData = "hwtHls.mergableFunction.statePlusMaskedData";
const std::string HwtHlsInstCombinePass::metadataName_expr_maskContinuosFromLsb = "hwtHls.expr.maskContinuosFromLsb";

PreservedAnalyses HwtHlsInstCombinePass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	auto &AC = AM.getResult<AssumptionAnalysis>(F);
	// prepare DT, TLI for getBestSimplifyQuery
	AM.getResult<DominatorTreeAnalysis>(F);
	AM.getResult<TargetLibraryAnalysis>(F);
	auto SQ = getBestSimplifyQuery(AM, F);
	InstructionWorklist Worklist;
	bool MadeIRChange = false;
	auto &DL = F.getParent()->getDataLayout();
	/// Builder - This is an IRBuilder that automatically inserts new
	/// instructions into the worklist when they are created.
	IRBuilder<TargetFolder, IRBuilderCallbackInserter> Builder(F.getContext(),
			TargetFolder(DL),
			IRBuilderCallbackInserter([&Worklist, &AC](Instruction *I) {
				Worklist.add(I);
				if (auto *Assume = dyn_cast<AssumeInst>(I)) {
					assert(!isa<ConstantInt>(Assume->getArgOperand(0)));
					AC.registerAssumption(Assume);
				}
			}));

	ReversePostOrderTraversal<BasicBlock*> RPOT(&F.front());
	// Iterate while there is work to do.
	unsigned Iteration = 0;
	for (;;) {
		++Iteration;

		if (Iteration > Options.MaxIterations) {
			LLVM_DEBUG(
					dbgs() << "\n\n[" DEBUG_TYPE_SHORT "] Iteration limit #" << Options.MaxIterations << " on "
					<< F.getName() << " reached; stopping without verifying fixpoint\n");
			break;
		}

		++NumWorklistIterations;
		LLVM_DEBUG(
				dbgs() << "\n\n" DEBUG_TYPE_SHORT " #" << Iteration << " on " << F.getName() << "\n");

		HwtHlsInstCombiner IC(Builder, SQ, Worklist, Options, F);
		bool MadeChangeInThisIteration = IC.prepareWorklist(RPOT);
		MadeChangeInThisIteration |= IC.run();
		if (!MadeChangeInThisIteration)
			break;

		MadeIRChange = true;
		if (Iteration > Options.MaxIterations) {
			report_fatal_error(
					"Instruction Combining did not reach a fixpoint after "
							+ Twine(Options.MaxIterations) + " iterations");
		}
	}

	// Mark all the analyses that instcombine updates as preserved.
	if (MadeIRChange)
		return PreservedAnalyses::all();

	// Mark all the analyses that instcombine updates as preserved.
	PreservedAnalyses PA;
	PA.preserveSet<CFGAnalyses>();
	return PA;
}

}
