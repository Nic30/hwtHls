#include <hwtHls/llvm/Transforms/SelectPruningPass.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/IR/Instructions.h>

#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitRewriter.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitPartsUseAnalysis.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/utils.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

#define DEBUG_TYPE "hwtfpga-select-pruning"

using namespace llvm;

namespace hwtHls {

class ConstBitPartsAnalysisContextSelectPruning: public ConstBitPartsAnalysisContext {
protected:
	DceWorklist &DCE;

	void useMask_backupAndClean(
			std::vector<std::pair<VarBitConstraint*, APInt>> &backup) {
		for (const auto& [_, vc] : constraints) {
			backup.push_back( { vc.get(), vc->useMask });
			vc->useMask.clearAllBits();
		}
	}
	std::vector<std::pair<VarBitConstraint*, APInt>> useMask_backupAndClean() {
		std::vector<std::pair<VarBitConstraint*, APInt>> backup;
		for (auto *_constraints = this; _constraints != nullptr;
				_constraints =
						reinterpret_cast<ConstBitPartsAnalysisContextSelectPruning*>(_constraints->parent)) {
			_constraints->useMask_backupAndClean(backup);
		}

		return backup;
	}

	static void useMask_accumulate(
			std::vector<std::pair<VarBitConstraint*, APInt>> &toAccumulate) {
		for (const auto& [v, useMask] : toAccumulate) {
			v->useMask |= useMask;
		}
	}

	void useMask_clean() {
		for (BitPartsConstraints *_constraints = this; _constraints;
				_constraints = _constraints->parent) {
			for (const auto& [_, vc] : _constraints->constraints) {
				vc->useMask.clearAllBits();
			}
		}
	}
	void useMaks_mergeOnSameLevel(const BitPartsConstraints &other) {
		for (const auto& [v, constr] : other.constraints) {
			auto thisConstr = constraints.find(v);
			if (thisConstr != constraints.end()) {
				thisConstr->second->useMask |= constr->useMask;
			}
		}
	}
public:
	static bool isCompatibleInstruction(const llvm::Instruction &I) {
		switch (I.getOpcode()) {
		// instruction with cost <= cost of select
		case Instruction::Select:
		case Instruction::And:
		case Instruction::Or:
		case Instruction::Xor:
		case Instruction::ZExt:
		case Instruction::SExt:
		case Instruction::BitCast:
			//case Instruction::ICmp:
			return true;
		case Instruction::Call: {
			auto *CI = dyn_cast<CallInst>(&I);
			return IsBitRangeGet(CI) || IsBitConcat(CI);
		}
		default:
			return false;
		}
	}
	ConstBitPartsAnalysisContextSelectPruning(DceWorklist &DCE,
			ConstBitPartsAnalysisContextSelectPruning *parent = nullptr,
			std::optional<std::function<bool(const llvm::Instruction&)>> analysisPredicate =
					isCompatibleInstruction) :
			ConstBitPartsAnalysisContext(parent, analysisPredicate), DCE(DCE) {
		tryAnalyzeOperandsOfUnsupportedInstructions = false;
	}

	void _initRewriterReplacementCacheWithNotReplacedTerms(
			BitPartsRewriter &rew, llvm::Instruction &I,
			llvm::SmallPtrSetImpl<llvm::Instruction*> &seen) {
		if (seen.contains(&I))
			return;
		if (!analysisPredicate.value()(I)) {
			rew.addReplacement(&I, &I); // will not be replaced => init replacement value to self
			seen.insert(&I);
		} else {
			seen.insert(&I);
			for (auto &O : I.operands()) {
				if (auto OI = dyn_cast<Instruction>(O)) {
					_initRewriterReplacementCacheWithNotReplacedTerms(rew, *OI,
							seen);
				}
			}
		}
	}
	Value* rewriteSelectOperandIfRequired(bool VTIsConst, Value *VT,
			llvm::SelectInst &SI,
			std::unique_ptr<ConstBitPartsAnalysisContextSelectPruning> &CBPA_T) {
		auto thisIsTopSelectAndInstrHasOnlyUserWhichIsParentSelect = [&SI,
				parent=parent](Instruction &I) {
			// allow to reuse instruction if it is used only by this select and we are rewriting
			// this select without any scoped context
			if (!parent) {
				auto U = I.getSingleUndroppableUse();
				if (U && U->getUser() == &SI) {
					return true;
				}
			}
			return false;
		};
		Value *newVT;
		if (VTIsConst) {
			newVT = VT;
		} else {
			BitPartsRewriter rewT(*CBPA_T, &DCE,
					thisIsTopSelectAndInstrHasOnlyUserWhichIsParentSelect);
			llvm::SmallPtrSet<llvm::Instruction*, 32> seenSetForCacheInit;
			_initRewriterReplacementCacheWithNotReplacedTerms(rewT, SI,
					seenSetForCacheInit);
			newVT = rewT.rewriteIfRequired(VT);
		}
		return newVT;
	}
	VarBitConstraint& visitSelectInst(const llvm::SelectInst *_I) override {
		auto &SI = *const_cast<SelectInst*>(_I);
		Value *C = SI.getCondition();
		Value *VT = SI.getTrueValue();
		Value *VF = SI.getFalseValue();
		auto knownBits = getKnownBitBoolValue(C);
		for (auto V : { C, VT, VF }) {
			if (auto VI = dyn_cast<Instruction>(V))
				DCE.insert(*const_cast<Instruction*>(VI));
		}
		if (knownBits.has_value()) {
			// if value is already known we may continue with current bit knowledge
			const Value *_res = knownBits.value() ? VT : VF;
			auto res = visitValue(_res);
			DCE.insert(SI);
			return initConstraintMember(&SI, res);
		} else {
			// select condition value is unknown, each branch has to be pruned with own context

			// :note: ConstBitPartsAnalysisContextSelectPruning can not be shared for T/F paths
			//  because they can come to a different conclusion for the same instruction.
			//  it is also hard to cache the for later use, as the cache key would be actual
			//  path in select tree.
			//  From this reason it is more simple to resolve full value and then discard
			//  bits if parent user recognizes bits as reducible. (parent does not yet know
			//  which bits can be discarded because this function discover bits values)
			std::unique_ptr<ConstBitPartsAnalysisContextSelectPruning> CBPA_T;
			std::unique_ptr<ConstBitPartsAnalysisContextSelectPruning> CBPA_F;
			auto VTIsConst = isa<ConstantInt>(VT);
			auto VFIsConst = isa<ConstantInt>(VF);

			if (!VTIsConst) {
				CBPA_T = createChild();
				CBPA_T->setKnownBitBoolValue(C, 1);
				CBPA_T->visitValue(VT);
			}
			if (!VFIsConst) {
				CBPA_F = createChild();
				CBPA_F->setKnownBitBoolValue(C, 0);
				CBPA_F->visitValue(VF);
			}
			// merge useMask

			// copy discovered pruned value from T/F branch
			//errs() << "CBPA_T\n";
			//CBPA_T->dumpConstraints();
			//errs() << "\n";
			//errs() << "CBPA_F\n";
			//CBPA_T->dumpConstraints();
			//errs() << "\n";
			//
			//errs() << "This CBPA\n";
			//dumpConstraints();
			//errs() << "\n";
			if (VTIsConst) {
				constraints[VT] = std::make_unique<VarBitConstraint>(
						cast<ConstantInt>(VT));
			} else {
				if (auto VTConstr = CBPA_T->findInConstraints(VT))
					constraints[VT] = std::make_unique<VarBitConstraint>(
							*VTConstr);
			}
			if (VFIsConst) {
				constraints[VF] = std::make_unique<VarBitConstraint>(
						cast<ConstantInt>(VF));
			} else {
				if (auto *VFConstr = CBPA_F->findInConstraints(VF))
					constraints[VF] = std::make_unique<VarBitConstraint>(
							*VFConstr);
			}
			auto &newSelVBC = ConstBitPartsAnalysisContext::visitSelectInst(&SI);
			auto selectUseMask = newSelVBC.getTrullyComputedBitMask(&SI);
			// now replacement bits are known

			std::vector<std::pair<VarBitConstraint*, APInt>> Uses_T;
			if (!VTIsConst) {
				// resolve use mask for all bits
				BitPartsUseAnalysisContext UA_T(*CBPA_T);
				//UA_T.updateUseMask(_I, selectUseMask);
				UA_T.updateUseMask(VT, selectUseMask);

				Uses_T = CBPA_T->useMask_backupAndClean();
				useMask_clean(); // because use mask propagation stops if not changed, but F branch may come
				// to same conclusion with a different values and it is required to probe full expression tree
				// and not to break on this false propagation stop
			}
			if (!VFIsConst) {
				BitPartsUseAnalysisContext UA_F(*CBPA_F);
				//UA_F.updateUseMask(_I, selectUseMask);
				UA_F.updateUseMask(VF, selectUseMask);

				useMask_accumulate(Uses_T); // return useMask to this from original state of CBPA_T
			}
			if (!VTIsConst && !VFIsConst) {
				CBPA_T->useMaks_mergeOnSameLevel(*CBPA_F);
				CBPA_F->useMaks_mergeOnSameLevel(*CBPA_T);
			}

			Value *newVT = rewriteSelectOperandIfRequired(VTIsConst, VT, SI,
					CBPA_T);
			//errs() << "newVT " <<  *VT << "\n";
			//if (newVT)
			//	errs() << *newVT << "\n";
			//else
			//	errs() << "null\n";
			Value *newVF = rewriteSelectOperandIfRequired(VFIsConst, VF, SI,
					CBPA_F);

			//errs() << "newVF " <<  *VF << "\n";
			//if (newVF)
			//	errs() << *newVF << "\n";
			//else
			//	errs() << "null\n";

			for (const auto& [newV, oldV] : std::array<
					std::pair<Value*, Value*>, 2>(				//
					{ { newVT, VT }, { newVF, VF } }	//
					)) {
				if (newV != oldV) {
					if (auto oldI = dyn_cast<Instruction>(oldV)) {
						DCE.insert(*oldI);
					}
				}
			}

			BitPartsUseAnalysisContext UA(*this);
			UA.updateUseMask(&SI, selectUseMask);
			BitPartsRewriter rewSel(*this, &DCE,
					[&SI, parent=parent](Instruction &I) {
						return !parent && &SI == &I;
					});
			{
				llvm::SmallPtrSet<llvm::Instruction*, 32> seenSetForCacheInit;
				_initRewriterReplacementCacheWithNotReplacedTerms(rewSel, SI,
						seenSetForCacheInit);
			}
			// add replacements which had to be resolved in advance because CBPA_T/CBPA_F is a separate context
			if (newVT)
				rewSel.addReplacement(const_cast<Value*>(VT), newVT);
			if (newVF)
				rewSel.addReplacement(const_cast<Value*>(VF), newVF);
			//errs() << " rewSel 0 " << *SINonConst << "\n";
			auto *newSel = rewSel.rewriteIfRequiredAndExpand(&SI);
			//errs() << " rewSel 1 " << *newSel << "\n";
			if (newSel != &SI) {
				if (!parent) {
					// replace only top select value for everyone else, nested selects are always specific to parent select
					SI.replaceAllUsesWith(newSel);
				}
				DCE.insert(SI);
				newSelVBC.substituteValue(&SI, newSel);
			}

			useMask_clean(); // because parent may visit same expressions with a different known values
			return newSelVBC;
		}
	}

	std::unique_ptr<ConstBitPartsAnalysisContextSelectPruning> createChild() {
		auto res = std::make_unique<ConstBitPartsAnalysisContextSelectPruning>(
				DCE, this, this->analysisPredicate);
		if (resolvePhiValues)
			res->setShouldResolvePhiValues();
		res->tryAnalyzeOperandsOfUnsupportedInstructions =
				tryAnalyzeOperandsOfUnsupportedInstructions;
		return res;
	}
	virtual ~ConstBitPartsAnalysisContextSelectPruning() {
	}
};

llvm::PreservedAnalyses SelectPruningPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	TargetLibraryInfo *TLI = &AM.getResult<TargetLibraryAnalysis>(F);
	DceWorklist DCE(TLI);
	bool Changed = false;
	for (auto &BB : F) {
		for (auto Iit = BB.begin(); Iit != BB.end(); ++Iit) {
			if (SelectInst *SI = dyn_cast<SelectInst>(&*Iit)) {
				ConstBitPartsAnalysisContextSelectPruning selectPruning(DCE);
				Changed |= !selectPruning.visitSelectInst(SI).isValue(SI);
				Changed |= DCE.runToCompletition(Iit);
			}
		}
	}

	Changed |= DCE.runToCompletition();
	if (Changed) {
		// :note: same as InstructionCombining
		PreservedAnalyses PA;
		PA.preserveSet<CFGAnalyses>();
		return PA;
	} else {
		return PreservedAnalyses::all();
	}
}

}
