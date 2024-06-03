#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_SwitchToSelect.h>

#include <algorithm>
#include <map>
#include <set>

#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Local.h>

#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFGUtils.h>

#define DEBUG_TYPE "simplifycfg2"
using namespace llvm;

namespace hwtHls {

struct PhiWithFewUnieqValues {
	PHINode &phi;
	Value *v0;
	size_t v0UseCnt;
	bool v0IsFromSwitchDefault;
	Value *v1;
	size_t v1UseCnt;
	bool v1IsFromSwitchDefault;
	PhiWithFewUnieqValues(PHINode &phi) :
			phi(phi), v0(nullptr), v0UseCnt(0), v0IsFromSwitchDefault(false), v1(
					nullptr), v1UseCnt(0), v1IsFromSwitchDefault(false) {
	}
	PhiWithFewUnieqValues(const PhiWithFewUnieqValues &other) = default;
	/*
	 * :returns: false if the phi has few unique input values else false
	 * */
	bool add_incoming_value(Value *v, bool isFromSwitchDefault) {
		if (v == v0) {
			v0UseCnt++;
			v0IsFromSwitchDefault |= isFromSwitchDefault;
		} else if (v == v1) {
			v1UseCnt++;
			v1IsFromSwitchDefault |= isFromSwitchDefault;
		} else if (!v0) {
			v0 = v;
			v0UseCnt = 1;
			v0IsFromSwitchDefault = isFromSwitchDefault;
		} else if (!v1) {
			v1 = v;
			v1UseCnt = 1;
			v1IsFromSwitchDefault = isFromSwitchDefault;
		} else {
			return false;
		}
		return true;
	}
	/*
	 * Sort v0, v1 so v0 has the most uses
	 * */
	void normalize() {
		if (v0UseCnt < v1UseCnt) {
			std::swap(v0, v1);
			std::swap(v0UseCnt, v1UseCnt);
			std::swap(v0IsFromSwitchDefault, v1IsFromSwitchDefault);
		}
	}
};

Value * buildSelectForSwitchWith2UniqValues(PHINode & PHI,
		const SmallVector<std::pair<BasicBlock*, Value*> >& Conditions,
		IRBuilder<> & Builder,
		Value * v0,
		Value * v1) {
	assert(v1);
	assert(v0);
	Value* v0Cond = nullptr;
	for (auto &Cond : Conditions) {
		auto _V = PHI.getIncomingValueForBlock(Cond.first);
		if (_V == v0) {
			if (!v0Cond) {
				v0Cond = Cond.second;
			} else {
				v0Cond = Builder.CreateOr(v0Cond, Cond.second);
			}
		}
	}
	assert(v0Cond);

	return Builder.CreateSelect(v0Cond, v0, v1);
}

Value* buildRomLoadFromPHI(SwitchInst *SI, Value *Cond, BasicBlock *BBTop,
		BasicBlock *BBBottom, PHINode &PHI, IRBuilder<> &Builder) {
	SmallVector<Constant*> romData;
	for (size_t i = 0; i < (1ull << Cond->getType()->getIntegerBitWidth());
			++i) {
		romData.push_back(nullptr);
	}
	// fill in values from cases
	for (auto C : SI->cases()) {
		size_t i = C.getCaseValue()->getZExtValue();
		assert(i < romData.size());
		auto phiPred = C.getCaseSuccessor();
		if (phiPred == BBBottom)
			phiPred = BBTop;
		auto _caseVal = dyn_cast<Constant>(
				PHI.getIncomingValueForBlock(phiPred));
		assert(_caseVal);
		romData[i] = _caseVal;
	}
	// fill in value from default on places which were not filled previously
	auto phiPred = SI->getDefaultDest();
	if (phiPred == BBBottom)
		phiPred = BBTop;
	auto *defVal = dyn_cast<Constant>(PHI.getIncomingValueForBlock(phiPred));
	for (auto &romD : romData) {
		if (romD == nullptr)
			romD = defVal;
	}

	auto romGep = CreateGlobalDataWithGEP(Builder, *BBTop->getModule(), Cond,
			romData, "switch.phirom", "switch.phirom.index", "switch.phi.gep");

	return Builder.CreateLoad(PHI.getType(), romGep, true, "switch.phirom.val");
}


void rewritePHIsAsSelectOrRomLoad(size_t MaxRomAddrWidth, llvm::SwitchInst *SI,
		BasicBlock *BBBottom, BasicBlock *BBTop, IRBuilder<> &Builder) {
	// rewrite PHIs in BBBottom as selects
	// insert at the end of BBTop because we merge BBTop to BBBottom
	// construct conditions first then selects for every PHI separately
	// so all select for some PHI are uninterrupted sequence of selects
	Value *Cond = SI->getCondition();
	auto *DefDst = SI->getDefaultDest();
	SmallVector<std::pair<BasicBlock*, Value*> > Conditions;
	std::set<PHINode*> phisForRomExtraction;
	size_t CondWidth = Cond->getType()->getIntegerBitWidth();
	if (CondWidth <= MaxRomAddrWidth
			&& SI->getNumCases() >= (1llu << CondWidth) / 2) {
		// if PHI has more than 2 operands and SI cases are covering value domain
		// are covering value domain of SI condition sufficiently.
		// It is beneficial to use load from ROM instead of tree of selects
		for (PHINode &PHI : BBBottom->phis()) {
			bool allValuesAreConst = true;
			for (Use &V : PHI.incoming_values()) {
				if (!isa<Constant>(V.get())) {
					allValuesAreConst = false;
					break;
				}
			}
			if (allValuesAreConst) {
				phisForRomExtraction.insert(&PHI);
			}
		}
	}

	auto getPhiPredForBB = [&](BasicBlock * BB) {
		return BB == BBBottom ? BBTop : BB;
	};
	std::map<PHINode*, PhiWithFewUnieqValues> phisWithFewUniqValues;
	size_t phiCnt = 0;
	for (PHINode &PHI : BBBottom->phis()) {
		++phiCnt;
		PhiWithFewUnieqValues phiMeta(PHI);
		bool hasJustPhiUniqInputs = true;
		auto *BBDefaultPredInPHI = getPhiPredForBB(DefDst);
		for (auto BB : PHI.blocks()) {
			auto *V = PHI.getIncomingValueForBlock(&*BB);
			if (!phiMeta.add_incoming_value(V, &*BB == BBDefaultPredInPHI)) {
				hasJustPhiUniqInputs = false;
				break;
			}
		}
		if (hasJustPhiUniqInputs) {
			phiMeta.normalize();
			if (!phiMeta.v1 || phiMeta.v1UseCnt == 1) {
				// if it has only a single value of v1 is used only once and rest is v0
				phisWithFewUniqValues.insert(std::make_pair(&PHI, phiMeta));
			}
		}
	}

	bool allPhisCanBeRom = phisForRomExtraction.size() == phiCnt;
	if (!allPhisCanBeRom) {
		if (DefDst) {
			Conditions.push_back( { getPhiPredForBB(DefDst), nullptr });
		}
		for (auto C : SI->cases()) {
			auto *Succ = C.getCaseSuccessor();
			Conditions.push_back(
					{ getPhiPredForBB(Succ), Builder.CreateICmpEQ(Cond,
							C.getCaseValue()) });
		}
	}
	for (PHINode &PHI : make_early_inc_range(BBBottom->phis())) {
		// there can be more conditions because the SwitchInst may jump to same block multiple times
		Value *V = nullptr;
		bool extractAsRom = phisForRomExtraction.find(&PHI)
				!= phisForRomExtraction.end();
		if (extractAsRom) {
			V = buildRomLoadFromPHI(SI, Cond, BBTop, BBBottom, PHI, Builder);
		} else {
			assert(Conditions.size() >= PHI.getNumIncomingValues());
			auto hasFewValues = phisWithFewUniqValues.find(&PHI);
			if (hasFewValues != phisWithFewUniqValues.end()) {
				auto& fewValues = hasFewValues->second;
				assert(fewValues.v0);
				assert(fewValues.v0UseCnt);
				assert(fewValues.v0IsFromSwitchDefault != fewValues.v1IsFromSwitchDefault && "Only one can be switch default");
				if (!fewValues.v1) {
					// most simple case: there is just one unique incoming value in phi
					V = fewValues.v0;
				} else if (fewValues.v1IsFromSwitchDefault) {
					// the value with least uses comes from SwitchInst default block,
					// we check if we can reduce it with just simple eq cmp or if we have
					// to compare all switch cases because switch cases are to sparse
					if (SI->getNumCases() == (1llu << CondWidth) - 1) { // - 1 because of default bb
						SmallVector<size_t> casesSorted;
						casesSorted.reserve(SI->case_end() - SI->case_begin());
						for (auto C : SI->cases()) {
							size_t i = C.getCaseValue()->getZExtValue();
							casesSorted.push_back(i);
						}
						std::sort(casesSorted.begin(), casesSorted.end());
						size_t CondCaseForDefDst = 0;
						for (auto c: casesSorted) {
							if (CondCaseForDefDst == c)
								++CondCaseForDefDst;
							else
								break; // we found first empty slot in value sequence
						}
						auto c = Builder.CreateICmpEQ(Cond, Builder.getIntN(Cond->getType()->getIntegerBitWidth(), CondCaseForDefDst ));
						V = Builder.CreateSelect(c, fewValues.v1, fewValues.v0);
					} else {
						// the cases in switch are too sparse, we have to create cmp for every case to resolve condition
						// for default branch
						V = buildSelectForSwitchWith2UniqValues(PHI, Conditions, Builder, fewValues.v0, fewValues.v1);
					}

				} else {
					// construct condition for the value with least uses
					V = buildSelectForSwitchWith2UniqValues(PHI, Conditions, Builder, fewValues.v1, fewValues.v0);
				}
			} else {
				for (auto &Cond : Conditions) {
					auto _V = PHI.getIncomingValueForBlock(Cond.first);
					if (V == nullptr) {
						V = _V;
					} else {
						assert(
								Cond.second
										&& "nullptr is used only for default value");
						if (_V != V)
							V = Builder.CreateSelect(Cond.second, _V, V);
					}
				}
			}
		}
		assert(V);
		if (!V->hasName() && PHI.hasName())
			V->setName(PHI.getName());

		PHI.replaceAllUsesWith(V);
		PHI.eraseFromParent();
	}
}

bool trySwitchToSelectOrRomLoad(llvm::SwitchInst *SI, IRBuilder<> &Builder,
		DomTreeUpdater &DTU, size_t MaxRomAddrWidth) {
	// if every successor has only PHIs (and terminator) or there is one which post dominates others and begins with phis
	// this SwitchInst does not have true effect on control flow and it only drives PHIs which are selecting values
	// To simplify CFG it is beneficial to rewrite this pattern. Remove all tmp blocks and keep only parent of SI with
	// updated terminator.
	// find simple diamond CFG pattern
	BasicBlock *BBTop = SI->getParent();
	BasicBlock *BBBottom = nullptr;
	SetVector<BasicBlock*> BBTopSuccessors = SetVector<BasicBlock*>(
			successors(BBTop).begin(), successors(BBTop).end());
	for (BasicBlock *Succ : BBTopSuccessors) {
		if (Succ->hasAddressTaken()) {
			return false;
		}
		if (Succ->getUniquePredecessor() == BBTop) {
			auto _SucSuc = Succ->getUniqueSuccessor();
			if (_SucSuc == nullptr)
				return false; // there must be unconditional jump to bottom block
			else if (BBBottom == nullptr) {
				BBBottom = _SucSuc;
				continue;
			} else if (BBBottom == _SucSuc) {
				continue;
			} else {
				return false; // successor is not BBBottom -> this is not recognized pattern
			}
		}
		bool allSucPredecessorsAreDominatedByBB = true;
		for (auto *SuccPred : predecessors(Succ)) {
			if (SuccPred != BBTop && BBTopSuccessors.count(SuccPred) == 0) {
				return false;
			} else if (BBBottom != nullptr && BBBottom != Succ) {
				return false; // this should not happen as there can be only one BBBottom
			}
		}
		if (allSucPredecessorsAreDominatedByBB) {
			BBBottom = Succ;
			continue;
		}
		return false;
	}
	assert(
			BBBottom
					&& "If there were successors there must be BBBottom or this function would already return");

	// check that every successor has compatible instructions
	for (BasicBlock *Succ : BBTopSuccessors) {
		if (Succ != BBBottom) {
			auto *Ter = Succ->getTerminator();
			// block must contain only br to BBBottom
			if (&*Succ->begin() != Ter) {
				return false;
			}
			auto *Br = dyn_cast<BranchInst>(Ter);
			if (!Br || Br->isConditional())
				return false;
		}
	}
	rewritePHIsAsSelectOrRomLoad(MaxRomAddrWidth, SI, BBBottom, BBTop, Builder);
	SI->eraseFromParent();
	for (BasicBlock *Succ : BBTopSuccessors) {
		if (Succ != BBBottom) {
			assert(Succ->hasNPredecessors(0));
		}
		DTU.applyUpdates( { { DominatorTree::Delete, BBTop, Succ } });
	}

	Builder.SetInsertPoint(BBTop, BBTop->end());
	Builder.CreateBr(BBBottom);
	DTU.applyUpdates( { { DominatorTree::Insert, BBTop, BBBottom } });
	for (BasicBlock *Succ : BBTopSuccessors) {
		if (Succ != BBBottom) {
			assert(Succ->hasNPredecessors(0));
			assert(Succ->use_empty());
			DeleteDeadBlock(Succ, &DTU); // :attention: can not directly erase because of iterator in caller
		}
	}
	if (BBTop != BBBottom) {
		MergeBlockIntoPredecessor(BBBottom, &DTU);
	}

	// :attention: DTU.flush() can not be applied there because it would break parent iteration if next block gets removed
	return true;
}

}
