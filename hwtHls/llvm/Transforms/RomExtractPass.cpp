#include <hwtHls/llvm/Transforms/RomExtractPass.h>

#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/Analysis/GlobalsModRef.h>
#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/IRBuilder.h>

#include <algorithm>
#include <set>

#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/targets/bitMathUtils.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>

using namespace llvm;

namespace hwtHls {

struct IndexCmpMatchInfo {
	Value *index;
	uint64_t val;
};

std::optional<IndexCmpMatchInfo> matchIndexCmp(const Value *V) {
	using namespace llvm::PatternMatch;
	uint64_t cmpVal;
	Value *index;
	CmpPredicate pred;
	if (match(V, m_ICmp(pred, m_Value(index), m_ConstantInt(cmpVal)))
			&& pred == ICmpInst::Predicate::ICMP_EQ) {
		return IndexCmpMatchInfo {index, cmpVal};
	}

	return {};
}

bool collectSelectTree(std::set<SelectInst*> &analyzed, Value &V,
		Value *index, std::unordered_map<uint64_t, Constant*> &values, size_t& collectedValues, Constant*& defaultValue) {
	if (auto SI = dyn_cast<SelectInst>(&V)) {
		auto _indexMatch = matchIndexCmp(SI->getCondition());
		if (!_indexMatch.has_value()) {
			return false;
		}
		auto indexMatch = _indexMatch.value();
		if (indexMatch.index != index)
			return false; // index does not match index of currently searched ROM
		if (analyzed.contains(SI))
			return true; // some other branch of the SelectInst tree has already filled this value in

		analyzed.insert(SI);
		auto TValAsConst = dyn_cast<Constant>(SI->getTrueValue());
		if (!TValAsConst) {
			return false; // value is not constant -> this can not be rewritten as a ROM
						  // not in format select indexCmp, constant, v
		}
		auto curVal = values.find(indexMatch.val);
		if (curVal != values.end() && curVal->second != TValAsConst) {
			// value was known to be something else, cancel search
			return false;
		}
		values[indexMatch.val] = TValAsConst;
		collectedValues++;

		if (collectSelectTree(analyzed, *SI->getFalseValue(), index, values, collectedValues, defaultValue))
			return true;

	} else if (auto C = dyn_cast<Constant>(&V)) {
		if (defaultValue == C) {
			return true;
		} else if (defaultValue == nullptr) {
			defaultValue = C;
			collectedValues++;
			return true;
		}
	}

	return false;
}

llvm::PreservedAnalyses RomExtractPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	TargetLibraryInfo *TLI = &AM.getResult<TargetLibraryAnalysis>(F);
	DceWorklist DCE(TLI);
	bool Changed = false;
	std::set<SelectInst*> analyzed;
	for (auto &&BB : F) {
		for (auto &I : make_early_inc_range(BB)) {
			if (auto *SI = dyn_cast<SelectInst>(&I)) {
				if (analyzed.contains(SI))
					continue; // already rewritten or known to be unextractable
				auto indexMatch = matchIndexCmp(SI->getCondition());
				if (indexMatch.has_value()) {
					Value * romIndex = indexMatch.value().index;
					size_t indexWidth = romIndex->getType()->getIntegerBitWidth();
					size_t romSize = 1 << indexWidth;
					if (romIndex->getType()->getIntegerBitWidth() == 1)
						continue; // to simple for extraction
					size_t collectedValues = 0;
					Constant *defaultValue = nullptr;
					SelectInst * TopSI = SI;
					bool parentShouldBeAnalyzedFirst = false;
					for (;TopSI->hasOneUser();) {
						User* SiUser = *TopSI->user_begin();
						if (auto SiUserAsSI = dyn_cast<SelectInst>(SiUser)) {
							auto UserIndexMatch = matchIndexCmp(SI->getCondition());
							if (!analyzed.contains(SiUserAsSI) &&
								UserIndexMatch.has_value() &&
								UserIndexMatch.value().index == romIndex) {
								// if the select has cmp on same index and it was not analyzed yet
								//TopSI = SiUserAsSI;
								parentShouldBeAnalyzedFirst = true;
								break;
							}
						}
						break;
					}
					if (parentShouldBeAnalyzedFirst) {
						continue;
					}
					std::unordered_map<uint64_t, Constant*> romDataDict;
					if (!collectSelectTree(analyzed, *TopSI, romIndex, romDataDict, collectedValues, defaultValue))
						continue;
					if (collectedValues < romSize)
						continue; // not enough values to extract as a ROM
											
					if (collectedValues == romSize) {
					} else {
						// +1 is the case where default value is not used because all cases are covered
						assert(collectedValues == romSize + 1);
					}

					SmallVector<Constant *, 64> romData;
					romData.resize(romSize);
					for (uint64_t i = 0; i < romSize; ++i) {
						auto curVal = romDataDict.find(i);
						if (curVal == romDataDict.end()) {
							romData[i] = defaultValue;
						} else {
							romData[i] = curVal->second;
						}
					}

					IRBuilder<> builder(TopSI);
					Value *newGep = CreateGlobalDataWithGEP(builder,
							*F.getParent(), romIndex, romData,
							"select.rom.table", "select.rom.index.zext",
							"select.rom.index");
					Value *newLoad = builder.CreateLoad(romData[0]->getType(),
							newGep, true, "select.table.val" + TopSI->getName());
					TopSI->replaceAllUsesWith(newLoad);

					DCE.insert(*TopSI);

					Changed = true;
				}
			}
		}
	}

	Changed |= DCE.runToCompletion();
	if (Changed) {
		// Mark all the analyses that instcombine updates as preserved.
		PreservedAnalyses PA;
		PA.preserveSet<CFGAnalyses>();
		PA.preserve<AAManager>();
		PA.preserve<BasicAA>();
		PA.preserve<GlobalsAA>();
		return PA;
	} else {
		return PreservedAnalyses::all();
	}
}

}
