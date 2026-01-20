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
		const StreamChannelProps &streamProps, llvm::IRBuilderBase &builder, llvm::DomTreeUpdater *DTU,
		llvm::LoopInfo *LI) :
		cfg(cfg), streamProps(streamProps), Builder(builder), DTU(DTU), LI(LI) {
}

std::vector<llvm::BasicBlock*> StreamIoRewriter::_createBranchForEachOffsetVariant(
		const std::vector<size_t> &possibleOffsets) {
	std::vector<llvm::BasicBlock*> offsetBranches;

	if (possibleOffsets.size() > 1) {
		BasicBlock *elseBlock = nullptr;
		// create branch for each offset variant
		llvm::SmallVector<llvm::Value*> offsetCaseCond;
		auto *_curOffsetVar = streamProps.getVarValue(Builder,
				streamProps.dataOffsetVar);
		size_t offI = 0;
		for (size_t off : possibleOffsets) {
			bool last = offI == possibleOffsets.size() - 1;
			BasicBlock *offsetVariantBlock;

			Value *offEn = Builder.CreateICmpEQ(_curOffsetVar,
					ConstantInt::get(_curOffsetVar->getType(),
							off % streamProps.dataWidth));

			llvm::Instruction *SplitBefore;
			if (elseBlock) {
				SplitBefore = elseBlock->getTerminator();
			} else {
				SplitBefore = &*Builder.GetInsertPoint();
			}
			llvm::Instruction *ThenTerm = nullptr;
			llvm::Instruction *ElseTerm = nullptr;
			llvm::SplitBlockAndInsertIfThenElse(offEn, SplitBefore, &ThenTerm,
					&ElseTerm, (llvm::MDNode*) nullptr, DTU, LI);
			offsetVariantBlock = dyn_cast<BasicBlock>(ThenTerm->getParent());
			assert(offsetVariantBlock != nullptr);

			elseBlock = ElseTerm->getParent();
			assert(elseBlock != nullptr);
			Builder.SetInsertPoint(elseBlock->getTerminator());

			if (last) {
				assert(ElseTerm->getNumSuccessors() == 1);
				auto elseBlockSuc = ElseTerm->getSuccessor(0);
				Builder.CreateUnreachable();
				ElseTerm->eraseFromParent();
				if (DTU) {
					DTU->applyUpdates({{DominatorTree::Delete, elseBlock, elseBlockSuc}});
				}
				Builder.SetInsertPoint(elseBlock->getTerminator());
			}

			offsetVariantBlock->setName(
					streamProps.ioArg->getName() + "off" + std::to_string(off));
			offsetBranches.push_back(offsetVariantBlock);
			++offI;
		}


	} else {
		auto *curBlock = Builder.GetInsertBlock();
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
		if (auto *CI = dyn_cast<CallInst>(&*curBlockPos)) {
			if (streamProps.ios.count(CI)
					&& cfg.resolvedStms.find(CI) == cfg.resolvedStms.end()) {
				cfg.resolvedStms.insert(CI);
				_rewriteAdtAccessToWordAccessInstruction(CI);
				if (curBlockPos->getParent() != curBlock) {
					// in the case that the block was split continue processing on new block begin
					curBlock = curBlockPos->getParent();
				}
			}
		}
	}

	// :note: curBlock may be a different than the original from arguments, because the block may be split etc.
	SmallVector<BasicBlock*> originalSuccessors(llvm::successors(curBlock));
	for (auto *sucBb : originalSuccessors) {
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
	// assert(!llvm::verifyFunction(F, &errs()));
	for (const StreamChannelProps &s : streamProps) {
		if (rmOutputs != s.isOutput)
			continue;
		for (auto *io : s.ios) {
			assert(!io->hasNUsesOrMore(1));
			io->eraseFromParent();
		}
	}
	auto *AC = FAM.getCachedResult<llvm::AssumptionAnalysis>(F);
	for (auto a: GeneratedAllocas) {
		SmallVector<User*> Users(a->users());
		for (auto u: Users) {
			if (auto uci = dyn_cast<CallInst>(u)) {
				if (IsStreamTmpAllocaTmpSetterPlaceholder(uci))
					uci->eraseFromParent();
			}
		}
	}
	llvm::PromoteMemToReg(GeneratedAllocas, DT, AC);
	for (auto &BB : F) {
		// :note: llvm-21 PromoteMemToReg somehow generates phis with reversed
		// order of operands according to block predecessors
		sortPhiOperands(BB);
	}
}

}
