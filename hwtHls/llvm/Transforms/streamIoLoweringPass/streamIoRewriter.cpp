#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoRewriter.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Transforms/Utils/PromoteMemToReg.h>
#include <llvm/Transforms/Utils/CodeMoverUtils.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/IR/Verifier.h>

#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

using namespace llvm;
namespace hwtHls {

StreamIoRewriter::StreamIoRewriter(StreamIoDetector &cfg,
		const StreamChannelProps &streamProps, llvm::DomTreeUpdater *DTU,
		llvm::LoopInfo *LI) :
		cfg(cfg), streamProps(streamProps), DTU(DTU), LI(LI) {
}

std::vector<llvm::BasicBlock*> StreamIoRewriter::_createBranchForEachOffsetVariant(
		llvm::IRBuilder<> &builder,
		const std::vector<size_t> &possibleOffsets) {
	std::vector<llvm::BasicBlock*> offsetBranches;

	if (possibleOffsets.size() > 1) {
		BasicBlock *elseBlock = nullptr;
		// create branch for each offset variant
		llvm::SmallVector<llvm::Value*> offsetCaseCond;
		auto *_curOffsetVar = streamProps.getVarValue(builder,
				streamProps.dataOffsetVar);
		size_t offI = 0;
		for (size_t off : possibleOffsets) {
			bool last = offI == possibleOffsets.size() - 1;
			BasicBlock *offsetVariantBlock;

			Value *offEn = builder.CreateICmpEQ(_curOffsetVar,
					ConstantInt::get(_curOffsetVar->getType(),
							off % streamProps.dataWidth));

			llvm::Instruction *SplitBefore;
			if (elseBlock) {
				SplitBefore = elseBlock->getTerminator();
			} else {
				SplitBefore = &*builder.GetInsertPoint();
			}
			llvm::Instruction *ThenTerm = nullptr;
			llvm::Instruction *ElseTerm = nullptr;
			llvm::SplitBlockAndInsertIfThenElse(offEn, SplitBefore, &ThenTerm,
					&ElseTerm, (llvm::MDNode*) nullptr, DTU);
			offsetVariantBlock = dyn_cast<BasicBlock>(ThenTerm->getParent());
			assert(offsetVariantBlock != nullptr);

			elseBlock = ElseTerm->getParent();
			assert(elseBlock != nullptr);
			builder.SetInsertPoint(elseBlock->getTerminator());
			if (last) {

				builder.CreateUnreachable();
				ElseTerm->eraseFromParent();
			}

			offsetVariantBlock->setName(
					streamProps.ioArg->getName() + "off" + std::to_string(off));
			offsetBranches.push_back(offsetVariantBlock);
			++offI;
		}


	} else {
		auto *curBlock = builder.GetInsertBlock();
		offsetBranches = { curBlock };
	}

	return offsetBranches;
}

void StreamIoRewriter::rewriteAdtAccessToWordAccess(BasicBlock &_curBlock) {
	BasicBlock *curBlock = &_curBlock;
	if (curBlock == &curBlock->getParent()->getEntryBlock()) {
		_rewriteAdtAccessToWordAccessInstruction(nullptr);
	}

	for (auto curBlockPos = curBlock->begin(); curBlockPos != curBlock->end();
			++curBlockPos) {
		if (curBlockPos->getParent() != curBlock) {
			curBlock = curBlockPos->getParent();
		}
		if (auto *CI = dyn_cast<CallInst>(&*curBlockPos)) {
			if (streamProps.ios.count(CI)
					&& cfg.resolvedStms.find(CI) == cfg.resolvedStms.end()) {
				cfg.resolvedStms.insert(CI);
				_rewriteAdtAccessToWordAccessInstruction(CI);
			}
		}
	}

	// :note: curBlock may be a different than the original from arguments, because the block may be split etc.
	for (auto *sucBb : llvm::successors(curBlock)) {
		auto seenPredecessors = cfg.seenPredecessors.find(sucBb);
		bool thisBlockWasSeen = false;
		if (seenPredecessors == cfg.seenPredecessors.end()) {
			cfg.seenPredecessors[sucBb] = { };
			seenPredecessors = cfg.seenPredecessors.find(sucBb);
		} else {
			thisBlockWasSeen = true;
		}
		seenPredecessors->second.insert(curBlock);

		if (!thisBlockWasSeen) {
			rewriteAdtAccessToWordAccess(*sucBb);
		}
	}
}

void finalizeStreamIoLowerig(llvm::Function &F,
		llvm::FunctionAnalysisManager &FAM, DominatorTree &DT,
		const std::vector<StreamChannelProps> &streamProps, bool rmOutputs,
		llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas) {
	assert(!llvm::verifyFunction(F, &errs()));
	for (const StreamChannelProps &s : streamProps) {
		if (rmOutputs != s.isOutput)
			continue;
		for (auto *io : s.ios) {
			assert(!io->hasNUsesOrMore(1));
			io->eraseFromParent();
		}
	}
	auto &AC = FAM.getResult<llvm::AssumptionAnalysis>(F);
	llvm::PromoteMemToReg(GeneratedAllocas, DT, &AC);
}

}
