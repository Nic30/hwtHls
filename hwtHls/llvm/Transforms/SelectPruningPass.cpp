#include <hwtHls/llvm/Transforms/SelectPruningPass.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitRewriter.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitPartsUseAnalysis.h>

#include <llvm/ADT/STLExtras.h>

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
	ConstBitPartsAnalysisContextSelectPruning(DceWorklist &DCE,
			ConstBitPartsAnalysisContextSelectPruning *parent = nullptr,
			std::optional<std::function<bool(const llvm::Instruction&)>> analysisHandle =
					{ }) :
			ConstBitPartsAnalysisContext(parent, analysisHandle), DCE(DCE) {
	}

	VarBitConstraint& visitSelectInst(const llvm::SelectInst *_I) override {
		const auto &I = *_I;
		const Value *C = I.getCondition();
		const Value *VT = I.getTrueValue();
		const Value *VF = I.getFalseValue();
		auto knownBits = getKnownBitBoolValue(C);

		if (knownBits.has_value()) {
			// if value is already known we may continue with current bit knowledge
			const Value *_res = knownBits.value() ? VT : VF;
			auto res = visitValue(_res);
			return initConstraintMember(const_cast<SelectInst*>(_I), res);
		} else {
			// select condition value is unknown, each branch has to be pruned with own context

			// :note: ConstBitPartsAnalysisContextSelectPruning can not be shared for T/F paths
			//  because they can come to a different conclusion for the same instruction.
			//  it is also hard to cache the for later use, as the cache key would be actual
			//  path in select tree.
			//  From this reason it is more simple to resolve full value and then discard
			//  bits if parent user recognizes bits as reducible. (parent does not yet know
			//  which bits can be discarded because this function discover bits values)

			auto CBPA_T = createChild();
			CBPA_T->setKnownBitBoolValue(C, 1);
			CBPA_T->visitValue(VT);

			auto CBPA_F = createChild();
			CBPA_F->setKnownBitBoolValue(C, 0);
			CBPA_F->visitValue(VF);
			// merge useMask

			// copy discovered pruned value from T/F branch
			constraints[VT] = std::make_unique<VarBitConstraint>(
					*CBPA_T->constraints[VT]);
			constraints[VF] = std::make_unique<VarBitConstraint>(
					*CBPA_F->constraints[VF]);

			auto &newSelVBC = ConstBitPartsAnalysisContext::visitSelectInst(_I);
			auto selectUseMask = newSelVBC.getTrullyComputedBitMask(_I);
			// now replacement bits are known

			// resolve use mask for all bits
			BitPartsUseAnalysisContext UA_T(*CBPA_T);
			//UA_T.updateUseMask(_I, selectUseMask);
			UA_T.updateUseMask(VT, selectUseMask);

			auto Uses_T = CBPA_T->useMask_backupAndClean();
			useMask_clean(); // because use mask propagation stops if not changed, but F branch may come
			// to same conclusion with a different values and it is required to probe full expression tree
			// and not to break on this false propagation stop

			BitPartsUseAnalysisContext UA_F(*CBPA_F);
			//UA_F.updateUseMask(_I, selectUseMask);
			UA_F.updateUseMask(VF, selectUseMask);

			useMask_accumulate(Uses_T); // return useMask to this, CBPA_T
			CBPA_T->useMaks_mergeOnSameLevel(*CBPA_F);
			CBPA_F->useMaks_mergeOnSameLevel(*CBPA_T);

			auto thisIsTopSelectAndInstrHasOnlyUserWhichIsParentSelect = [_I,
					parent=parent](Instruction &I) {
				// allow to reuse instruction if it is used only by this select and we are rewriting
				// this select without any scoped context
				if (!parent) {
					auto U = I.getSingleUndroppableUse();
					if (U && U->getUser() == _I)
						return true;
				}
				return false;
			};
			BitPartsRewriter rewT(*CBPA_T,
					thisIsTopSelectAndInstrHasOnlyUserWhichIsParentSelect);
			auto newVT = rewT.rewriteIfRequired(const_cast<Value*>(VT));
			//if (newVT == nullptr) // nullptr means replaced by itself
			//	newVT = const_cast<Value*>(VT);
			BitPartsRewriter rewF(*CBPA_F,
					thisIsTopSelectAndInstrHasOnlyUserWhichIsParentSelect);
			auto newVF = rewT.rewriteIfRequired(const_cast<Value*>(VF));
			//if (newVF == nullptr)
			//	newVF = const_cast<Value*>(VF);

			for (const auto& [newV, oldV] : std::array<
					std::pair<Value*, const Value*>, 2>( { { newVT, VT }, {
					newVF, VF } })) {
				if (newV != oldV) {
					if (auto oldI = dyn_cast<Instruction>(
							const_cast<Value*>(oldV))) {
						DCE.insert(*oldI);
					}
				}
			}

			BitPartsUseAnalysisContext UA(*this);
			UA.updateUseMask(_I, selectUseMask);
			BitPartsRewriter rewSel(*this, [_I, parent=parent](Instruction &I) {
				return !parent && _I == &I;
			});
			// add replacements which had to be resolved in advance because CBPA_T/CBPA_F is a separate context
			if (newVT)
				rewSel.addReplacement(const_cast<Value*>(VT), newVT);
			if (newVF)
				rewSel.addReplacement(const_cast<Value*>(VF), newVF);
			auto *SINonConst = const_cast<SelectInst*>(_I);
			auto *newSel = rewSel.rewriteIfRequiredAndExpand(SINonConst);
			if (newSel != _I) {
				if (!parent) {
					// replace only top select value for everyone else, nested selects are always specific to parent select
					SINonConst->replaceAllUsesWith(newSel);
				}
				DCE.insert(*SINonConst);
				newSelVBC.substituteValue(_I, newSel);
			}

			useMask_clean(); // because parent may visit same expressions with a different known values
			return newSelVBC;
		}
	}
	std::unique_ptr<ConstBitPartsAnalysisContextSelectPruning> createChild() {
		auto res = std::make_unique<ConstBitPartsAnalysisContextSelectPruning>(
				DCE, this, this->analysisHandle);
		if (resolvePhiValues)
			res->setShouldResolvePhiValues();
		return res;
	}
	virtual ~ConstBitPartsAnalysisContextSelectPruning() {
	}
};

llvm::PreservedAnalyses SelectPruningPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	TargetLibraryInfo *TLI = &AM.getResult<TargetLibraryAnalysis>(F);
	DceWorklist DCE(TLI, nullptr);
	bool Changed = false;
	for (auto &&BB : F) {
		for (auto &I : make_early_inc_range(BB)) {
			if (auto *SI = dyn_cast<SelectInst>(&I)) {
				ConstBitPartsAnalysisContextSelectPruning selectPruning(DCE,
						nullptr);
				Changed |= !selectPruning.visitSelectInst(SI).isValue(SI);
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