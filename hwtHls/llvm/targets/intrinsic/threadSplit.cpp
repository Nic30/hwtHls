#include <hwtHls/llvm/targets/intrinsic/threadSplit.h>
#include <llvm/ADT/StringExtras.h>

#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>

#include <llvm/IR/Dominators.h>
#include <llvm/IR/IRBuilder.h>

#include <llvm/Transforms/Utils/CodeExtractor.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/bitMath.h>

using namespace llvm;

namespace hwtHls {

llvm::CallInst* CreateThreadSplit(IRBuilderBase &Builder, std::string name, MDNode* md) {
	Type *ResT = Builder.getVoidTy();
	Module *M = Builder.GetInsertBlock()->getParent()->getParent();
	// :note: this expects hwtHls.thread.section metadata to be set later
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(name, ResT).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder.CreateCall(TheFn);
	CI->setMemoryEffects(MemoryEffects::unknown());
	if (md) {
		CI->setMetadata(ThreadSplitSectionMetadata::METADATA_NAME, md);
	}

	return CI;
}

extern const std::string ThreadSplitBeginName = "hwtHls.thread.split.begin.";
llvm::CallInst* CreateThreadSplitBegin(IRBuilderBase &Builder,
		const std::string &name, MDNode* md) {
	return CreateThreadSplit(Builder, ThreadSplitBeginName + name, md);
}

extern const std::string ThreadSplitEndName = "hwtHls.thread.split.end.";
llvm::CallInst* CreateThreadSplitEnd(IRBuilderBase &Builder,
		const std::string &name, MDNode* md) {
	return CreateThreadSplit(Builder, ThreadSplitEndName + name, md);
}

bool IsThreadSplitBeginInst(const llvm::Instruction *I) {
	if (auto C = dyn_cast<CallInst>(I))
		return IsThreadSplitBegin(C->getCalledFunction());
	return false;
}

bool IsThreadSplitBegin(const llvm::CallInst *C) {
	return IsThreadSplitBegin(C->getCalledFunction());
}

bool IsThreadSplitBegin(const llvm::Function *F) {
	assert(
			F != nullptr
					&& "Function must have definition if input code was valid");
	return F->getName().str().rfind(ThreadSplitBeginName, 0) == 0;
}

bool IsThreadSplitEnd(const llvm::CallInst *C) {
	return IsThreadSplitEnd(C->getCalledFunction());
}

bool IsThreadSplitEnd(const llvm::Function *F) {
	assert(
			F != nullptr
					&& "Function must have definition if input code was valid");
	return F->getName().str().rfind(ThreadSplitEndName, 0) == 0;
}

std::string ThreadSplitBeginGetName(const llvm::Function *F) {
	assert(F->getName().str().rfind(ThreadSplitBeginName, 0) == 0);
	auto FnName = F->getName().str();
	return FnName.substr(ThreadSplitBeginName.length(), FnName.length());
}

std::optional<std::string> getNameOfCalledFunction(const Instruction &I) {
	if (auto *CI = dyn_cast<CallInst>(&I)) {
		return CI->getCalledFunction()->getName().str();
	}
	return {};
}
const std::string ThreadSplitSectionMetadata::METADATA_NAME =
		"hwtHls.thread.section";

llvm::MDNode* ThreadSplitSectionMetadata::toMetadata(
		llvm::LLVMContext &Ctx) const {
	// !0 = distinct !{!"name", i1 0, i1 0, i1 0, i1 0, i64 0, i64 0} // corresponds to members of this sruct
	std::vector<llvm::Metadata*> MDs;
	MDs.push_back(MDString::get(Ctx, name));
	auto *u1 = IntegerType::get(Ctx, 1);
	auto addBoolMd = [u1, &MDs](bool v) {
		MDs.push_back(ValueAsMetadata::get(ConstantInt::get(u1, v)));
	};

	addBoolMd(aggregateInputs);
	addBoolMd(beginMayBeAsync);
	addBoolMd(aggregateOutputs);
	addBoolMd(endMayBeAsync);
	Type *u64 = IntegerType::get(Ctx, 64);
	auto addU64Md = [u64, &MDs](size_t v) {
		MDs.push_back(ValueAsMetadata::get(ConstantInt::get(u64, v)));
	};
	addU64Md(inputBufferCapacity);
	addU64Md(outputBufferCapacity);

	MDNode *mdValTuple = MDNode::getDistinct(Ctx, MDs);
	return mdValTuple;
}

ThreadSplitSectionMetadata ThreadSplitSectionMetadata::fromMetadata(
		llvm::MDNode &MD) {
	MDTuple *mdTuple = dyn_cast<MDTuple>(&MD);
	assert(
			mdTuple && mdTuple->isDistinct()
					&& "expected format for distinct MD");
	assert(mdTuple->getNumOperands() == 7);
	auto getMdInt =
			[&mdTuple](size_t argI) {
				auto v =
						cast<ValueAsMetadata>(mdTuple->getOperand(argI).get())->getValue();
				return dyn_cast<ConstantInt>(v)->getZExtValue();
			};

	ThreadSplitSectionMetadata res;
	res.name = cast<MDString>(mdTuple->getOperand(0).get())->getString();
	res.aggregateInputs = getMdInt(1);
	res.beginMayBeAsync = getMdInt(2);
	res.aggregateOutputs = getMdInt(3);
	res.endMayBeAsync = getMdInt(4);
	res.inputBufferCapacity = getMdInt(5);
	res.outputBufferCapacity = getMdInt(6);

	return res;
}

ThreadSplitSectionMetadata ThreadSplitGetSeparatedSection(DomTreeUpdater &DTU,
		LoopInfo &LI, CallInst &firstThreadSplit,
		SmallVector<BasicBlock*> &Blocks) {
	assert(firstThreadSplit.arg_size() == 0);

	auto SectionName = ThreadSplitBeginGetName(
			firstThreadSplit.getCalledFunction());
	SmallVector<CallInst*> allFrontThreadSplits;

	if (firstThreadSplit.getParent()->begin()
			!= firstThreadSplit.getIterator()) {
		DTU.flush();
		// split block so it starts with ThreadSplit
		auto BBName = firstThreadSplit.getParent()->getName()
				+ ".threadSplit.begin" + SectionName;
		SplitBlock(firstThreadSplit.getParent(), firstThreadSplit.getIterator(),
				&DTU, &LI, /*MSSAU*/nullptr, BBName, /*Before*/true);
	}
	auto sectionMetadata = firstThreadSplit.getMetadata(
			ThreadSplitSectionMetadata::METADATA_NAME);
	assert(
			sectionMetadata
					&& "Each thread split intrinsic should have metadata");
	// :note: for CodeExtractor it is required that BB is dominating all extracted blocks
	// :note: it is required that there is a single exit block from extracted section
	//        because it would be hard to optimize return value encoding
	// :note: if this is in loop the extracted section should have new while true loop
	//        which reads inputs and writes outputs as it would in the original iteration body
	auto *BB = firstThreadSplit.getParent();
	//auto *L = LI.getLoopFor(BB);
	//if (!L) {
	//	throw std::runtime_error("[todo] threadSplit outside of loop");
	//}
	//auto Latch = L->getLoopLatch();
	//if (!Latch) {
	//	throw std::runtime_error(
	//			"[todo] threadSplit in loop without a single latch block");
	//}
	auto EndName = ThreadSplitEndName + SectionName;
	//auto &DT = DTU.getDomTree();
	//assert(DT.dominates(BB, Latch));
	std::set<BasicBlock*> seen;
	SmallVector<BasicBlock*> toSearch = { BB };
	SmallVector<BasicBlock*> ExitingBBs;
	//bool LatchReached = false;
	while (toSearch.size()) {
		auto *_BB = toSearch.back();
		toSearch.pop_back();
		if (seen.contains(_BB))
			continue;
		bool threadSplitFound = false;
		for (auto &I : *_BB) {
			auto fnName = getNameOfCalledFunction(I);
			if (fnName.has_value() && fnName.value() == EndName) {
				assert(
						I.getMetadata(ThreadSplitSectionMetadata::METADATA_NAME)
								== sectionMetadata);
				DTU.flush();
				// split block so it starts with ThreadSplit
				auto BBName = _BB->getName() + ".threadSplit.end."
						+ SectionName;
				SplitBlock(_BB, I.getIterator(), &DTU, &LI, /*MSSAU*/nullptr,
						BBName, /*Before*/false);
				//Blocks.push_back(_BB); // predecessor bb contains selected instructions
				// I is now in block which is not in section
				I.eraseFromParent();
				threadSplitFound = true;
				break;
			}
		}

		Blocks.push_back(_BB);
		if (!threadSplitFound) {
			for (auto *Suc : successors(_BB)) {
				toSearch.push_back(Suc);
			}
		}
	}

	//{
	//	auto* latchTerm = Latch->getTerminator();
	//	DTU.flush();
	//	// split block so it starts with ThreadSplit
	//	auto BBName = Latch->getName() + ".threadSplit.end";
	//	SplitBlock(Latch, latchTerm->getIterator(),
	//			&DTU, &LI, /*MSSAU*/nullptr, BBName, /*Before*/true);
	//	Latch = latchTerm->getParent();
	//}

	//Blocks.push_back(Latch);
	firstThreadSplit.eraseFromParent();

	for (auto *BB : Blocks) {
		for (auto &I : *BB) {
			if (auto CI = dyn_cast<CallInst>(&I)) {
				if (IsThreadSplitBegin(CI)) {
					llvm_unreachable(
							"Section should not contain ThreadSplitBegin because we were extracting inner most section");
				} else if (IsThreadSplitEnd(CI)) {
					llvm_unreachable(
							"Section should not contain ThreadSplitEnd because we were extracting inner most section");
				}
			}
		}
	}
	return ThreadSplitSectionMetadata::fromMetadata(*sectionMetadata);
}

}
