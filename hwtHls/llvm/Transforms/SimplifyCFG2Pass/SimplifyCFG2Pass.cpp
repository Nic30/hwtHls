/*
 * This whole file is mostly original SimplifyCFG with just patch for switch instr merge checks.
 * This is required in order to successfully translate large SwitchInst to load from constant array
 * */
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass.h>

#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/MDBuilder.h>
#include <llvm/Support/Debug.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/DomTreeUpdater.h>

#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_normalizeLookupTableIndex.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_aggresiveStoreSink.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_rewriteMaskPatternsFromCFGToData.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_SwitchSuccessorHoistCode.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_SwitchToSelect.h>

#include <map>
#define DEBUG_TYPE "simplifycfg2"

using namespace llvm;
namespace hwtHls {

template<typename T>
cl::opt<T>& getLlvmOption(llvm::StringRef name) {
	llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
	auto opt = Map.find(name);
	assert(opt != Map.end());
	return *dynamic_cast<cl::opt<T>*>(opt->second);
}

// [copied] copied from llvm because of SimplifyCFG private Options which can not be accessed through inheritance
// Command-line settings override compile-time settings.
static void applyCommandLineOverridesToOptions(SimplifyCFGOptions &Options) {
	auto &UserBonusInstThreshold = getLlvmOption<unsigned>(
			"bonus-inst-threshold");
	auto &UserForwardSwitchCond = getLlvmOption<bool>("forward-switch-cond");
	auto &UserSwitchRangeToICmp = getLlvmOption<bool>("switch-range-to-icmp");
	auto &UserSwitchToLookup = getLlvmOption<bool>("switch-to-lookup");
	auto &UserKeepLoops = getLlvmOption<bool>("keep-loops");
	auto &UserHoistCommonInsts = getLlvmOption<bool>("hoist-common-insts");
	auto &UserSinkCommonInsts = getLlvmOption<bool>("sink-common-insts");
	if (UserBonusInstThreshold.getNumOccurrences())
		Options.BonusInstThreshold = UserBonusInstThreshold;
	if (UserForwardSwitchCond.getNumOccurrences())
		Options.ForwardSwitchCondToPhi = UserForwardSwitchCond;
	if (UserSwitchRangeToICmp.getNumOccurrences())
		Options.ConvertSwitchRangeToICmp = UserSwitchRangeToICmp;
	if (UserSwitchToLookup.getNumOccurrences())
		Options.ConvertSwitchToLookupTable = UserSwitchToLookup;
	if (UserKeepLoops.getNumOccurrences())
		Options.NeedCanonicalLoop = UserKeepLoops;
	if (UserHoistCommonInsts.getNumOccurrences())
		Options.HoistCommonInsts = UserHoistCommonInsts;
	if (UserSinkCommonInsts.getNumOccurrences())
		Options.SinkCommonInsts = UserSinkCommonInsts;
}

SimplifyCFG2Pass::SimplifyCFG2Pass() :
		SimplifyCFGPass() {
	applyCommandLineOverridesToOptions(Options);
}

SimplifyCFG2Pass::SimplifyCFG2Pass(const SimplifyCFGOptions &Opts) :
		SimplifyCFGPass(Opts), Options(Opts) {
	applyCommandLineOverridesToOptions(Options);
}

/// This class implements a stable ordering of constant
/// integers that does not depend on their address.  This is important for
/// applications that sort ConstantInt's to ensure uniqueness.
struct ConstantIntOrdering {
	bool operator()(const ConstantInt *LHS, const ConstantInt *RHS) const {
		return LHS->getValue().ult(RHS->getValue());
	}
};

/// ValueEqualityComparisonCase - Represents a case of a switch.
struct ValueEqualityComparisonCase {
	ConstantInt *Value;
	BasicBlock *Dest;

	ValueEqualityComparisonCase(ConstantInt *Value, BasicBlock *Dest) :
			Value(Value), Dest(Dest) {
	}

	bool operator<(ValueEqualityComparisonCase RHS) const {
		// Comparing pointers is ok as we only rely on the order for uniquing.
		return Value < RHS.Value;
	}

	bool operator==(BasicBlock *RHSDest) const {
		return Dest == RHSDest;
	}
};

// original SimplifyCFGOpt with simplifySwitch/FoldValueComparisonIntoPredecessors patched
class SimplifyCFGOpt2 {
	DomTreeUpdater *DTU;
	const DataLayout &DL;
	const TargetTransformInfo &TTI;
	const SimplifyCFGOptions &Options;
	unsigned LlvmHoistCommonSkipLimit;

	bool Resimplify;

	Value* isValueEqualityComparison(Instruction *TI,
			bool checkParentPredecessors);
	BasicBlock* GetValueEqualityComparisonCases(Instruction *TI,
			std::vector<ValueEqualityComparisonCase> &Cases);
	bool FoldValueComparisonIntoPredecessors(Instruction *TI,
			IRBuilder<> &Builder);
	bool PerformValueComparisonIntoPredecessorFolding(Instruction *TI,
			Value *&CV, Instruction *PTI, IRBuilder<> &Builder);
	bool simplifySwitch(SwitchInst *SI, IRBuilder<> &Builder);

public:
	SimplifyCFGOpt2(DomTreeUpdater *DTU, const DataLayout &DL,
			const TargetTransformInfo &TTI, const SimplifyCFGOptions &Opts,
			unsigned LlvmHoistCommonSkipLimit) :
			DTU(DTU), DL(DL), TTI(TTI), Options(Opts), LlvmHoistCommonSkipLimit(
					LlvmHoistCommonSkipLimit), Resimplify(false) {
		assert(
				(!DTU || !DTU->hasPostDomTree())
						&& "SimplifyCFG is not yet capable of maintaining validity of a "
								"PostDomTree, so don't ask for it.");
	}
	bool simplifyOnce(BasicBlock *BB);
	// Helper to set Resimplify and return change indication.
	bool requestResimplify() {
		Resimplify = true;
		return true;
	}
	bool run(BasicBlock *BB) {
		bool Changed = false;

		// Repeated simplify BB as long as resimplification is requested.
		do {
			Resimplify = false;

			// Perform one round of simplifcation. Resimplify flag will be set if
			// another iteration is requested.
			Changed |= simplifyOnce(BB);
		} while (Resimplify);

		return Changed;
	}
};

/// Extract ConstantInt from value, looking through IntToPtr
/// and PointerNullValue. Return NULL if value is not a constant int.
static ConstantInt* GetConstantInt(Value *V, const DataLayout &DL) {
	// Normal constant int.
	ConstantInt *CI = dyn_cast<ConstantInt>(V);
	if (CI || !isa<Constant>(V) || !V->getType()->isPointerTy())
		return CI;

	// This is some kind of pointer constant. Turn it into a pointer-sized
	// ConstantInt if possible.
	IntegerType *PtrTy = cast<IntegerType>(DL.getIntPtrType(V->getType()));

	// Null pointer means 0, see SelectionDAGBuilder::getValue(const Value*).
	if (isa<ConstantPointerNull>(V))
		return ConstantInt::get(PtrTy, 0);

	// IntToPtr const int.
	if (ConstantExpr *CE = dyn_cast<ConstantExpr>(V))
		if (CE->getOpcode() == Instruction::IntToPtr)
			if (ConstantInt *CI = dyn_cast<ConstantInt>(CE->getOperand(0))) {
				// The constant is very likely to have the right type already.
				if (CI->getType() == PtrTy)
					return CI;
				else
					return cast<ConstantInt>(
							ConstantExpr::getIntegerCast(CI, PtrTy, /*isSigned=*/
							false));
			}
	return nullptr;
}

static inline bool HasBranchWeights(const Instruction *I) {
	MDNode *ProfMD = I->getMetadata(LLVMContext::MD_prof);
	if (ProfMD && ProfMD->getOperand(0))
		if (MDString *MDS = dyn_cast<MDString>(ProfMD->getOperand(0)))
			return MDS->getString().equals("branch_weights");

	return false;
}

/// Get Weights of a given terminator, the default weight is at the front
/// of the vector. If TI is a conditional eq, we need to swap the branch-weight
/// metadata.
static void GetBranchWeights(Instruction *TI,
		SmallVectorImpl<uint64_t> &Weights) {
	MDNode *MD = TI->getMetadata(LLVMContext::MD_prof);
	assert(MD);
	for (unsigned i = 1, e = MD->getNumOperands(); i < e; ++i) {
		ConstantInt *CI = mdconst::extract<ConstantInt>(MD->getOperand(i));
		Weights.push_back(CI->getValue().getZExtValue());
	}

	// If TI is a conditional eq, the default case is the false case,
	// and the corresponding branch-weight data is at index 2. We swap the
	// default weight to be the first entry.
	if (BranchInst *BI = dyn_cast<BranchInst>(TI)) {
		assert(Weights.size() == 2);
		ICmpInst *ICI = cast<ICmpInst>(BI->getCondition());
		if (ICI->getPredicate() == ICmpInst::ICMP_EQ)
			std::swap(Weights.front(), Weights.back());
	}
}

/// Update PHI nodes in Succ to indicate that there will now be entries in it
/// from the 'NewPred' block. The values that will be flowing into the PHI nodes
/// will be the same as those coming in from ExistPred, an existing predecessor
/// of Succ.
static void AddPredecessorToBlock(BasicBlock *Succ, BasicBlock *NewPred,
		BasicBlock *ExistPred, MemorySSAUpdater *MSSAU = nullptr) {
	for (PHINode &PN : Succ->phis())
		PN.addIncoming(PN.getIncomingValueForBlock(ExistPred), NewPred);
	if (MSSAU)
		if (auto *MPhi = MSSAU->getMemorySSA()->getMemoryAccess(Succ))
			MPhi->addIncoming(MPhi->getIncomingValueForBlock(ExistPred),
					NewPred);
}

/// Keep halving the weights until all can fit in uint32_t.
static void FitWeights(MutableArrayRef<uint64_t> Weights) {
	uint64_t Max = *std::max_element(Weights.begin(), Weights.end());
	if (Max > UINT_MAX) {
		unsigned Offset = 32 - countLeadingZeros(Max);
		for (uint64_t &I : Weights)
			I >>= Offset;
	}
}
// Set branch weights on SwitchInst. This sets the metadata if there is at
// least one non-zero weight.
static void setBranchWeights(SwitchInst *SI, ArrayRef<uint32_t> Weights) {
	// Check that there is at least one non-zero weight. Otherwise, pass
	// nullptr to setMetadata which will erase the existing metadata.
	MDNode *N = nullptr;
	if (llvm::any_of(Weights, [](uint32_t W) {
		return W != 0;
	})
		)
		N = MDBuilder(SI->getParent()->getContext()).createBranchWeights(
				Weights);
	SI->setMetadata(LLVMContext::MD_prof, N);
}

static void EraseTerminatorAndDCECond(Instruction *TI, MemorySSAUpdater *MSSAU =
		nullptr) {
	Instruction *Cond = nullptr;
	if (SwitchInst *SI = dyn_cast<SwitchInst>(TI)) {
		Cond = dyn_cast<Instruction>(SI->getCondition());
	} else if (BranchInst *BI = dyn_cast<BranchInst>(TI)) {
		if (BI->isConditional())
			Cond = dyn_cast<Instruction>(BI->getCondition());
	} else if (IndirectBrInst *IBI = dyn_cast<IndirectBrInst>(TI)) {
		Cond = dyn_cast<Instruction>(IBI->getAddress());
	}

	TI->eraseFromParent();
	if (Cond)
		RecursivelyDeleteTriviallyDeadInstructions(Cond, nullptr, MSSAU);
}

static bool passingValueIsAlwaysUndefined(Value *V, Instruction *I,
		bool PtrValueMayBeModified = false);
/// Check if passing a value to an instruction will cause undefined behavior.
static bool passingValueIsAlwaysUndefined(Value *V, Instruction *I,
		bool PtrValueMayBeModified) {
	Constant *C = dyn_cast<Constant>(V);
	if (!C)
		return false;

	if (I->use_empty())
		return false;

	if (C->isNullValue() || isa<UndefValue>(C)) {
		// Only look at the first use, avoid hurting compile time with long uselists
		auto *Use = cast<Instruction>(*I->user_begin());
		// Bail out if Use is not in the same BB as I or Use == I or Use comes
		// before I in the block. The latter two can be the case if Use is a PHI
		// node.
		if (Use->getParent() != I->getParent() || Use == I
				|| Use->comesBefore(I))
			return false;

		// Now make sure that there are no instructions in between that can alter
		// control flow (eg. calls)
		auto InstrRange = make_range(std::next(I->getIterator()),
				Use->getIterator());
		if (any_of(InstrRange, [](Instruction &I) {
			return !isGuaranteedToTransferExecutionToSuccessor(&I);
		})
			)
			return false;

		// Look through GEPs. A load from a GEP derived from NULL is still undefined
		if (GetElementPtrInst *GEP = dyn_cast<GetElementPtrInst>(Use))
			if (GEP->getPointerOperand() == I) {
				if (!GEP->isInBounds() || !GEP->hasAllZeroIndices())
					PtrValueMayBeModified = true;
				return passingValueIsAlwaysUndefined(V, GEP,
						PtrValueMayBeModified);
			}

		// Look through bitcasts.
		if (BitCastInst *BC = dyn_cast<BitCastInst>(Use))
			return passingValueIsAlwaysUndefined(V, BC, PtrValueMayBeModified);

		// Load from null is undefined.
		if (LoadInst *LI = dyn_cast<LoadInst>(Use))
			if (!LI->isVolatile())
				return !NullPointerIsDefined(LI->getFunction(),
						LI->getPointerAddressSpace());

		// Store to null is undefined.
		if (StoreInst *SI = dyn_cast<StoreInst>(Use))
			if (!SI->isVolatile())
				return (!NullPointerIsDefined(SI->getFunction(),
						SI->getPointerAddressSpace()))
						&& SI->getPointerOperand() == I;

		if (auto *CB = dyn_cast<CallBase>(Use)) {
			if (C->isNullValue() && NullPointerIsDefined(CB->getFunction()))
				return false;
			// A call to null is undefined.
			if (CB->getCalledOperand() == I)
				return true;

			if (C->isNullValue()) {
				for (const llvm::Use &Arg : CB->args())
					if (Arg == I) {
						unsigned ArgIdx = CB->getArgOperandNo(&Arg);
						if (CB->isPassingUndefUB(ArgIdx)
								&& CB->paramHasAttr(ArgIdx,
										Attribute::NonNull)) {
							// Passing null to a nonnnull+noundef argument is undefined.
							return !PtrValueMayBeModified;
						}
					}
			} else if (isa<UndefValue>(C)) {
				// Passing undef to a noundef argument is undefined.
				for (const llvm::Use &Arg : CB->args())
					if (Arg == I) {
						unsigned ArgIdx = CB->getArgOperandNo(&Arg);
						if (CB->isPassingUndefUB(ArgIdx)) {
							// Passing undef to a noundef argument is undefined.
							return true;
						}
					}
			}
		}
	}
	return false;
}

/// If BB has an incoming value that will always trigger undefined behavior
/// (eg. null pointer dereference), remove the branch leading here.
static bool removeUndefIntroducingPredecessor(BasicBlock *BB,
		DomTreeUpdater *DTU) {
	for (PHINode &PHI : BB->phis())
		for (unsigned i = 0, e = PHI.getNumIncomingValues(); i != e; ++i)
			if (passingValueIsAlwaysUndefined(PHI.getIncomingValue(i), &PHI)) {
				BasicBlock *Predecessor = PHI.getIncomingBlock(i);
				Instruction *T = Predecessor->getTerminator();
				IRBuilder<> Builder(T);
				if (BranchInst *BI = dyn_cast<BranchInst>(T)) {
					BB->removePredecessor(Predecessor);
					// Turn uncoditional branches into unreachables and remove the dead
					// destination from conditional branches.
					if (BI->isUnconditional())
						Builder.CreateUnreachable();
					else {
						// Preserve guarding condition in assume, because it might not be
						// inferrable from any dominating condition.
						Value *Cond = BI->getCondition();
						if (BI->getSuccessor(0) == BB)
							Builder.CreateAssumption(Builder.CreateNot(Cond));
						else
							Builder.CreateAssumption(Cond);
						Builder.CreateBr(
								BI->getSuccessor(0) == BB ?
										BI->getSuccessor(1) :
										BI->getSuccessor(0));
					}
					BI->eraseFromParent();
					if (DTU)
						DTU->applyUpdates( { { DominatorTree::Delete,
								Predecessor, BB } });
					return true;
				} else if (SwitchInst *SI = dyn_cast<SwitchInst>(T)) {
					// Redirect all branches leading to UB into
					// a newly created unreachable block.
					BasicBlock *Unreachable = BasicBlock::Create(
							Predecessor->getContext(), "unreachable",
							BB->getParent(), BB);
					Builder.SetInsertPoint(Unreachable);
					// The new block contains only one instruction: Unreachable
					Builder.CreateUnreachable();
					for (auto &Case : SI->cases())
						if (Case.getCaseSuccessor() == BB) {
							BB->removePredecessor(Predecessor);
							Case.setSuccessor(Unreachable);
						}
					if (SI->getDefaultDest() == BB) {
						BB->removePredecessor(Predecessor);
						SI->setDefaultDest(Unreachable);
					}

					if (DTU)
						DTU->applyUpdates( { { DominatorTree::Insert,
								Predecessor, Unreachable }, {
								DominatorTree::Delete, Predecessor, BB } });
					return true;
				}
			}

	return false;
}

bool SimplifyCFGOpt2::PerformValueComparisonIntoPredecessorFolding(
		Instruction *TI, Value *&CV, Instruction *PTI, IRBuilder<> &Builder) {
	BasicBlock *BB = TI->getParent();
	BasicBlock *Pred = PTI->getParent();

	SmallVector<DominatorTree::UpdateType, 32> Updates;

	// Figure out which 'cases' to copy from SI to PSI.
	std::vector<ValueEqualityComparisonCase> BBCases;
	BasicBlock *BBDefault = GetValueEqualityComparisonCases(TI, BBCases);

	std::vector<ValueEqualityComparisonCase> PredCases;
	BasicBlock *PredDefault = GetValueEqualityComparisonCases(PTI, PredCases);

	// Based on whether the default edge from PTI goes to BB or not, fill in
	// PredCases and PredDefault with the new switch cases we would like to
	// build.
	SmallMapVector<BasicBlock*, int, 8> NewSuccessors;

	// Update the branch weight metadata along the way
	SmallVector<uint64_t, 8> Weights;
	bool PredHasWeights = HasBranchWeights(PTI);
	bool SuccHasWeights = HasBranchWeights(TI);

	if (PredHasWeights) {
		GetBranchWeights(PTI, Weights);
		// branch-weight metadata is inconsistent here.
		if (Weights.size() != 1 + PredCases.size())
			PredHasWeights = SuccHasWeights = false;
	} else if (SuccHasWeights)
		// If there are no predecessor weights but there are successor weights,
		// populate Weights with 1, which will later be scaled to the sum of
		// successor's weights
		Weights.assign(1 + PredCases.size(), 1);

	SmallVector<uint64_t, 8> SuccWeights;
	if (SuccHasWeights) {
		GetBranchWeights(TI, SuccWeights);
		// branch-weight metadata is inconsistent here.
		if (SuccWeights.size() != 1 + BBCases.size())
			PredHasWeights = SuccHasWeights = false;
	} else if (PredHasWeights)
		SuccWeights.assign(1 + BBCases.size(), 1);

	if (PredDefault == BB) {
		// If this is the default destination from PTI, only the edges in TI
		// that don't occur in PTI, or that branch to BB will be activated.
		std::set<ConstantInt*, ConstantIntOrdering> PTIHandled;
		for (unsigned i = 0, e = PredCases.size(); i != e; ++i)
			if (PredCases[i].Dest != BB)
				PTIHandled.insert(PredCases[i].Value);
			else {
				// The default destination is BB, we don't need explicit targets.
				std::swap(PredCases[i], PredCases.back());

				if (PredHasWeights || SuccHasWeights) {
					// Increase weight for the default case.
					Weights[0] += Weights[i + 1];
					std::swap(Weights[i + 1], Weights.back());
					Weights.pop_back();
				}

				PredCases.pop_back();
				--i;
				--e;
			}

		// Reconstruct the new switch statement we will be building.
		if (PredDefault != BBDefault) {
			PredDefault->removePredecessor(Pred);
			if (DTU && PredDefault != BB)
				Updates.push_back(
						{ DominatorTree::Delete, Pred, PredDefault });
			PredDefault = BBDefault;
			++NewSuccessors[BBDefault];
		}

		unsigned CasesFromPred = Weights.size();
		uint64_t ValidTotalSuccWeight = 0;
		for (unsigned i = 0, e = BBCases.size(); i != e; ++i)
			if (!PTIHandled.count(BBCases[i].Value)
					&& BBCases[i].Dest != BBDefault) {
				PredCases.push_back(BBCases[i]);
				++NewSuccessors[BBCases[i].Dest];
				if (SuccHasWeights || PredHasWeights) {
					// The default weight is at index 0, so weight for the ith case
					// should be at index i+1. Scale the cases from successor by
					// PredDefaultWeight (Weights[0]).
					Weights.push_back(Weights[0] * SuccWeights[i + 1]);
					ValidTotalSuccWeight += SuccWeights[i + 1];
				}
			}

		if (SuccHasWeights || PredHasWeights) {
			ValidTotalSuccWeight += SuccWeights[0];
			// Scale the cases from predecessor by ValidTotalSuccWeight.
			for (unsigned i = 1; i < CasesFromPred; ++i)
				Weights[i] *= ValidTotalSuccWeight;
			// Scale the default weight by SuccDefaultWeight (SuccWeights[0]).
			Weights[0] *= SuccWeights[0];
		}
	} else {
		// If this is not the default destination from PSI, only the edges
		// in SI that occur in PSI with a destination of BB will be
		// activated.
		std::set<ConstantInt*, ConstantIntOrdering> PTIHandled;
		std::map<ConstantInt*, uint64_t> WeightsForHandled;
		for (unsigned i = 0, e = PredCases.size(); i != e; ++i)
			if (PredCases[i].Dest == BB) {
				PTIHandled.insert(PredCases[i].Value);

				if (PredHasWeights || SuccHasWeights) {
					WeightsForHandled[PredCases[i].Value] = Weights[i + 1];
					std::swap(Weights[i + 1], Weights.back());
					Weights.pop_back();
				}

				std::swap(PredCases[i], PredCases.back());
				PredCases.pop_back();
				--i;
				--e;
			}

		// Okay, now we know which constants were sent to BB from the
		// predecessor.  Figure out where they will all go now.
		for (unsigned i = 0, e = BBCases.size(); i != e; ++i)
			if (PTIHandled.count(BBCases[i].Value)) {
				// If this is one we are capable of getting...
				if (PredHasWeights || SuccHasWeights)
					Weights.push_back(WeightsForHandled[BBCases[i].Value]);
				PredCases.push_back(BBCases[i]);
				++NewSuccessors[BBCases[i].Dest];
				PTIHandled.erase(BBCases[i].Value); // This constant is taken care of
			}

		// If there are any constants vectored to BB that TI doesn't handle,
		// they must go to the default destination of TI.
		for (ConstantInt *I : PTIHandled) {
			if (PredHasWeights || SuccHasWeights)
				Weights.push_back(WeightsForHandled[I]);
			PredCases.push_back(ValueEqualityComparisonCase(I, BBDefault));
			++NewSuccessors[BBDefault];
		}
	}

	// Okay, at this point, we know which new successor Pred will get.  Make
	// sure we update the number of entries in the PHI nodes for these
	// successors.
	SmallPtrSet<BasicBlock*, 2> SuccsOfPred;
	if (DTU) {
		SuccsOfPred = { succ_begin(Pred), succ_end(Pred) };
		Updates.reserve(Updates.size() + NewSuccessors.size());
	}
	for (const std::pair<BasicBlock*, int /*Num*/> &NewSuccessor : NewSuccessors) {
		for (auto I : seq(0, NewSuccessor.second)) {
			(void) I;
			AddPredecessorToBlock(NewSuccessor.first, Pred, BB);
		}
		if (DTU && !SuccsOfPred.contains(NewSuccessor.first))
			Updates.push_back(
					{ DominatorTree::Insert, Pred, NewSuccessor.first });
	}

	Builder.SetInsertPoint(PTI);
	// Convert pointer to int before we switch.
	if (CV->getType()->isPointerTy()) {
		CV = Builder.CreatePtrToInt(CV, DL.getIntPtrType(CV->getType()),
				"magicptr");
	}

	// Now that the successors are updated, create the new Switch instruction.
	SwitchInst *NewSI = Builder.CreateSwitch(CV, PredDefault, PredCases.size());
	NewSI->setDebugLoc(PTI->getDebugLoc());
	for (ValueEqualityComparisonCase &V : PredCases)
		NewSI->addCase(V.Value, V.Dest);

	if (PredHasWeights || SuccHasWeights) {
		// Halve the weights if any of them cannot fit in an uint32_t
		FitWeights(Weights);

		SmallVector<uint32_t, 8> MDWeights(Weights.begin(), Weights.end());

		setBranchWeights(NewSI, MDWeights);
	}

	EraseTerminatorAndDCECond(PTI);

	// Okay, last check.  If BB is still a successor of PSI, then we must
	// have an infinite loop case.  If so, add an infinitely looping block
	// to handle the case to preserve the behavior of the code.
	BasicBlock *InfLoopBlock = nullptr;
	for (unsigned i = 0, e = NewSI->getNumSuccessors(); i != e; ++i)
		if (NewSI->getSuccessor(i) == BB) {
			if (!InfLoopBlock) {
				// Insert it at the end of the function, because it's either code,
				// or it won't matter if it's hot. :)
				InfLoopBlock = BasicBlock::Create(BB->getContext(), "infloop",
						BB->getParent());
				BranchInst::Create(InfLoopBlock, InfLoopBlock);
				if (DTU)
					Updates.push_back( { DominatorTree::Insert, InfLoopBlock,
							InfLoopBlock });
			}
			NewSI->setSuccessor(i, InfLoopBlock);
		}

	if (DTU) {
		if (InfLoopBlock)
			Updates.push_back( { DominatorTree::Insert, Pred, InfLoopBlock });

		Updates.push_back( { DominatorTree::Delete, Pred, BB });

		DTU->applyUpdates(Updates);
	}

	//++NumFoldValueComparisonIntoPredecessors;
	return true;
}

/// Given a value comparison instruction,
/// decode all of the 'cases' that it represents and return the 'default' block.
BasicBlock* SimplifyCFGOpt2::GetValueEqualityComparisonCases(Instruction *TI,
		std::vector<ValueEqualityComparisonCase> &Cases) {
	if (SwitchInst *SI = dyn_cast<SwitchInst>(TI)) {
		Cases.reserve(SI->getNumCases());
		for (auto Case : SI->cases())
			Cases.push_back(
					ValueEqualityComparisonCase(Case.getCaseValue(),
							Case.getCaseSuccessor()));
		return SI->getDefaultDest();
	}

	BranchInst *BI = cast<BranchInst>(TI);
	ICmpInst *ICI = cast<ICmpInst>(BI->getCondition());
	BasicBlock *Succ = BI->getSuccessor(
			ICI->getPredicate() == ICmpInst::ICMP_NE);
	Cases.push_back(
			ValueEqualityComparisonCase(GetConstantInt(ICI->getOperand(1), DL),
					Succ));
	return BI->getSuccessor(ICI->getPredicate() == ICmpInst::ICMP_EQ);
}

/// Return true if it is safe to merge these two
/// terminator instructions together.
static bool SafeToMergeTerminators(Instruction *SI1, Instruction *SI2,
		SmallSetVector<BasicBlock*, 4> *FailBlocks = nullptr) {
	if (SI1 == SI2)
		return false; // Can't merge with self!

	// It is not safe to merge these two switch instructions if they have a common
	// successor, and if that successor has a PHI node, and if *that* PHI node has
	// conflicting incoming values from the two switch blocks.
	BasicBlock *SI1BB = SI1->getParent();
	BasicBlock *SI2BB = SI2->getParent();

	SmallPtrSet<BasicBlock*, 16> SI1Succs(succ_begin(SI1BB), succ_end(SI1BB));
	bool Fail = false;
	for (BasicBlock *Succ : successors(SI2BB))
		if (SI1Succs.count(Succ))
			for (BasicBlock::iterator BBI = Succ->begin(); isa<PHINode>(BBI);
					++BBI) {
				PHINode *PN = cast<PHINode>(BBI);
				if (PN->getIncomingValueForBlock(SI1BB)
						!= PN->getIncomingValueForBlock(SI2BB)) {
					if (FailBlocks)
						FailBlocks->insert(Succ);
					Fail = true;
				}
			}

	return !Fail;
}

/// Return true if the specified terminator checks
/// to see if a value is equal to constant integer value.
Value* SimplifyCFGOpt2::isValueEqualityComparison(Instruction *TI,
		bool checkParentPredecessors) {
	Value *CV = nullptr;
	if (SwitchInst *SI = dyn_cast<SwitchInst>(TI)) {
		// Do not permit merging of large switch instructions into their
		// predecessors unless there is only one predecessor.
		if (!checkParentPredecessors
				|| !SI->getParent()->hasNPredecessorsOrMore(
						128 / SI->getNumSuccessors()))
			CV = SI->getCondition();
	} else if (BranchInst *BI = dyn_cast<BranchInst>(TI))
		if (BI->isConditional() && BI->getCondition()->hasOneUse())
			if (ICmpInst *ICI = dyn_cast<ICmpInst>(BI->getCondition())) {
				if (ICI->isEquality() && GetConstantInt(ICI->getOperand(1), DL))
					CV = ICI->getOperand(0);
			}

	// Unwrap any lossless ptrtoint cast.
	if (CV) {
		if (PtrToIntInst *PTII = dyn_cast<PtrToIntInst>(CV)) {
			Value *Ptr = PTII->getPointerOperand();
			if (PTII->getType() == DL.getIntPtrType(Ptr->getType()))
				CV = Ptr;
		}
	}
	return CV;
}

/// The specified terminator is a value equality comparison instruction
/// (either a switch or a branch on "X == c").
/// See if any of the predecessors of the terminator block are value comparisons
/// on the same value.  If so, and if safe to do so, fold them together.
bool SimplifyCFGOpt2::FoldValueComparisonIntoPredecessors(Instruction *TI,
		IRBuilder<> &Builder) {
	BasicBlock *BB = TI->getParent();
	Value *CV = isValueEqualityComparison(TI, false); // CondVal
	assert(CV && "Not a comparison?");

	bool Changed = false;

	SmallSetVector<BasicBlock*, 16> Preds(pred_begin(BB), pred_end(BB));
	while (!Preds.empty()) {
		BasicBlock *Pred = Preds.pop_back_val();
		Instruction *PTI = Pred->getTerminator();

		// Don't try to fold into itself.
		if (Pred == BB)
			continue;

		// See if the predecessor is a comparison with the same value.
		Value *PCV = isValueEqualityComparison(PTI, false); // PredCondVal
		if (PCV != CV)
			continue;

		SmallSetVector<BasicBlock*, 4> FailBlocks;
		if (!SafeToMergeTerminators(TI, PTI, &FailBlocks)) {
			for (auto *Succ : FailBlocks) {
				if (!SplitBlockPredecessors(Succ, TI->getParent(),
						".fold.split", DTU))
					return false;
			}
		}

		PerformValueComparisonIntoPredecessorFolding(TI, CV, PTI, Builder);
		Changed = true;
	}
	return Changed;
}

bool SimplifyCFGOpt2::simplifySwitch(SwitchInst *SI, IRBuilder<> &Builder) {
	BasicBlock *BB = SI->getParent();

	if (isValueEqualityComparison(SI, false)) {
		// If the block only contains the switch, see if we can fold the block
		// away into any preds.
		if (SI == &*BB->instructionsWithoutDebug(false).begin())
			if (FoldValueComparisonIntoPredecessors(SI, Builder))
				return requestResimplify();
	}
	bool everySucDominated = true;
	auto BBSuccessors = successors(BB);
	for (BasicBlock *Succ : BBSuccessors) {
		if (Succ->hasAddressTaken()) {
			everySucDominated = false;
			break;
		}
		if (Succ->getUniquePredecessor() == BB)
			continue;
		bool allSucPredecessorsAreDominatedByBB = true;
		for (auto *SuccPred : predecessors(Succ)) {
			if (SuccPred != BB
					&& std::find(BBSuccessors.begin(), BBSuccessors.end(),
							SuccPred) == BBSuccessors.end()) {
				allSucPredecessorsAreDominatedByBB = false;
				break;
			}
		}
		if (allSucPredecessorsAreDominatedByBB)
			continue;
		everySucDominated = false;
		break;
	}
	if (Options.HoistCommonInsts) {
		if (everySucDominated
				&& HoistFromSwitchSuccessors(SI, TTI,
						LlvmHoistCommonSkipLimit)) {
			return requestResimplify();
		}
	}
	if (everySucDominated && trySwitchToSelect(SI, Builder, *DTU))
		return requestResimplify();

	return false;
}

bool SimplifyCFGOpt2::simplifyOnce(BasicBlock *BB) {
	bool Changed = false;

	assert(BB && BB->getParent() && "Block not embedded in function!");
	assert(BB->getTerminator() && "Degenerate basic block encountered!");

	// Remove basic blocks that have no predecessors (except the entry block)...
	// or that just have themself as a predecessor.  These are unreachable.
	if ((pred_empty(BB) && BB != &BB->getParent()->getEntryBlock())
			|| BB->getSinglePredecessor() == BB) {
		LLVM_DEBUG(dbgs() << "Removing BB: \n" << *BB);
		DeleteDeadBlock(BB, DTU);
		return true;
	}

	// Check to see if we can constant propagate this terminator instruction
	// away...
	Changed |= ConstantFoldTerminator(BB, /*DeleteDeadConditions=*/true,
	/*TLI=*/nullptr, DTU);

	// Check for and eliminate duplicate PHI nodes in this block.
	Changed |= EliminateDuplicatePHINodes(BB);

	// Check for and remove branches that will always cause undefined behavior.
	if (removeUndefIntroducingPredecessor(BB, DTU))
		return requestResimplify();

	// Merge basic blocks into their predecessor if there is only one distinct
	// pred, and if there is only one distinct successor of the predecessor, and
	// if there are no PHI nodes.
	if (MergeBlockIntoPredecessor(BB, DTU))
		return true;

	IRBuilder<> Builder(BB);

	Instruction *Terminator = BB->getTerminator();
	Builder.SetInsertPoint(Terminator);
	switch (Terminator->getOpcode()) {
	case Instruction::Switch:
		Changed |= simplifySwitch(cast<SwitchInst>(Terminator), Builder);
		break;
	}
	return Changed;
}

// run SimplifyCFGPass::run, SimplifyCFGOpt2 and SimplifyCFGPass2_normalizeLookupTableIndex
llvm::PreservedAnalyses SimplifyCFG2Pass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	size_t itCntr = 0;
	Options.AC = &AM.getResult<AssumptionAnalysis>(F);
	DominatorTree *DT = nullptr;
	RequireAndPreserveDomTree = true;
	if (RequireAndPreserveDomTree) {
		DT = &AM.getResult<DominatorTreeAnalysis>(F);
	}
	DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
	auto &TTI = AM.getResult<TargetIRAnalysis>(F);
	auto &DL = F.getParent()->getDataLayout();
	llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
	auto _LlvmHoistCommonSkipLimit = Map.find(
			"simplifycfg-hoist-common-skip-limit");
	assert(_LlvmHoistCommonSkipLimit != Map.end());
	unsigned LlvmHoistCommonSkipLimit =
			dynamic_cast<cl::opt<unsigned>*>(_LlvmHoistCommonSkipLimit->second)->getValue();
	llvm::PreservedAnalyses FirstPA;

	bool changed = false;
	SimplifyCFGOpt2 opt(&DTU, DL, TTI, Options, LlvmHoistCommonSkipLimit);

	for (;;) {
		auto PA = SimplifyCFGPass::run(F, AM);
		if (itCntr == 0)
			FirstPA = PA;

		if (PA.areAllPreserved()) {
			if (itCntr > 0)
				break;
		} else {
			changed = true;
		}
		bool _changed = false;
		for (Function::iterator BBIt = F.begin(); BBIt != F.end();) {
			BasicBlock &BB = *BBIt++;
			assert(
					!DTU.isBBPendingDeletion(&BB)
							&& "Should not end up trying to simplify blocks marked for removal.");
			// Make sure that the advanced iterator does not point at the blocks
			// that are marked for removal, skip over all such blocks.
			while (BBIt != F.end() && DTU.isBBPendingDeletion(&*BBIt))
				++BBIt;
			assert(&BB && BB.getParent() && "Block not embedded in function!");
			_changed |= opt.run(&BB);
			while (BBIt != F.end() && DTU.isBBPendingDeletion(&*BBIt))
				++BBIt;
			DTU.flush(); // (required because otherwise blocks are removed before update is applied)
			_changed |= SimplifyCFG2Pass_normalizeLookupTableIndex(BB);
			_changed |= SimplifyCFG2Pass_rewriteMaskPatternsFromCFGToData(DTU,
					BB);

		}
		_changed = false;
		for (Function::iterator BBIt = F.begin(); BBIt != F.end();) {
			//auto _PA = PreservedAnalyses::all();
			////_PA.abandon<DominatorTreeAnalysis>();
			//AM.invalidate(F, _PA);
			//DT = &AM.getResult<DominatorTreeAnalysis>(F);
			//auto _DTU = DomTreeUpdater(DT, DomTreeUpdater::UpdateStrategy::Lazy);
			if (SimplifyCFG2Pass_aggresiveStoreSink(DTU, *BBIt)) {
				_changed = true;
				// continue rewriting this block while it is updated
			} else {
				BBIt++;
			}
		}
		changed |= _changed;
		if (!_changed)
			break;

		itCntr++;
		assert(itCntr < 1000 && "SimplifyCFGPass2 did not converge");
	}

	if (changed) {
		PreservedAnalyses PA;
		if (RequireAndPreserveDomTree)
			PA.preserve<DominatorTreeAnalysis>();
		return PA;
	}
	return FirstPA;
}

}
