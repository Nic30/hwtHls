#include "llvm/IR/Analysis.h"
#include <hwtHls/llvm/Transforms/FsmStateBinToOneHotPass.h>

#include <bitset>
#include <cstdint>
#include <llvm-21/llvm/Analysis/LazyValueInfo.h>
#include <llvm-21/llvm/IR/Verifier.h>
#include <map>
#include <unordered_map>
#include <unordered_set>
#include <utility>

#include <llvm/ADT/ArrayRef.h>
#include <llvm/ADT/Bitfields.h>
#include <llvm/ADT/PostOrderIterator.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/IR/Constant.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/DataLayout.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/InstrTypes.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/Intrinsics.h>
#include <llvm/IR/PassManager.h>
#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/ValueHandle.h>
#include <llvm/Support/Casting.h>
#include <llvm/Support/ErrorHandling.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_fewExitCluster_cutOffExitBBInClusterSuccessors.h>
#include <hwtHls/llvm/Transforms/LowerSwitchWithIfChain.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

class FsmToOneHotRewritter {
public:
	static constexpr size_t BITWIDTH_LIMIT = 4;
	// :note: the value is a nullptr for states which are not used
	using OneHotEncodedVal = SmallVector<Value *, 1 << BITWIDTH_LIMIT>;
	using OneHotEncodedValMap = std::map<Value *, OneHotEncodedVal>;

private:
	LazyValueInfo *LVI;
	AssumptionCache *AC;
	const DataLayout &DL;
	IRBuilder<> &Builder;
	// int 1b type
	IntegerType *I1Ty;
	// number of bits for binary representation
	uint64_t stateWidth;
	uint64_t maxStateCnt;

public:
	using StateBitmask = std::bitset<1 << BITWIDTH_LIMIT>;
	// bit mask of truly used states
	// :note: if the state is used only in some icmp, but can not happen because
	// the value never appears
	//  in state variable, usedStates still contain the corresponding bit set
	StateBitmask usedStates;
	SetVector<SwitchInst*> memberSwitches;
	// instruction participating in state switching
	SetVector<Instruction *> members;
	// one-hot reencoded value for each original value
	std::map<Value *, OneHotEncodedVal> oneHotMap;

	SetVector<Instruction *> primaryInputs;
	SetVector<Instruction *> primaryOutputUsers;
	//
	std::unordered_map<Instruction *, Value *> newBinValues;

private:
	using RewriteResult = std::pair<decltype(oneHotMap)::iterator, bool>;
	RewriteResult rewriteConstant(Constant &C) {
		auto existing = oneHotMap.find(&C);
		if (existing != oneHotMap.end())
			return {existing, false};

		OneHotEncodedVal newVals;
		if (isa<UndefValue>(&C)) {
			auto v = isa<PoisonValue>(&C) ? PoisonValue::get(I1Ty)
										  : UndefValue::get(I1Ty);
			for (uint64_t stI = 0; stI < maxStateCnt; ++stI) {
				Value *_v = v;
				if (!usedStates[stI]) {
					_v = nullptr;
				}
				newVals.push_back(_v);
			}
		} else if (auto CI = dyn_cast<ConstantInt>(&C)) {
			for (uint64_t stI = 0; stI < maxStateCnt; ++stI) {
				Value *_v = nullptr;
				if (usedStates[stI]) {
					_v = ConstantInt::get(I1Ty,
										  CI->getValue().getZExtValue() == stI);
				}
				newVals.push_back(_v);
			}
		} else {
			llvm_unreachable("FsmToOneHotRewritter: constant of unknown type");
		}
		auto inserted = oneHotMap.emplace(&C, std::move(newVals));
		assert(inserted.second);
		return inserted;
	}

	RewriteResult rewritePhi(PHINode &I) {
		Builder.SetInsertPoint(&I);
		OneHotEncodedVal newPhis;
		for (uint64_t stI = 0; stI < maxStateCnt; ++stI) {
			PHINode *NewPhi = nullptr;
			if (usedStates[stI]) {
				NewPhi =
					Builder.CreatePHI(I1Ty, I.getNumIncomingValues(),
									  I.getName() + ".onehot." + Twine(stI));
			}
			newPhis.push_back(NewPhi);
		}
		auto inserted = oneHotMap.emplace(&I, std::move(newPhis));
		assert(inserted.second);
		return inserted;
	}

	Value *createPredicate(ArrayRef<Value *> OneHot,
						   ArrayRef<uint64_t> SelectedStates, ICmpInst &CmpI) {
		size_t selectedCnt = 0;
		for (auto stI : SelectedStates) {
			assert(usedStates[stI]);
			selectedCnt++;
		}
		if (selectedCnt == 0)
			return Builder.getFalse();

		size_t totalStateCnt = usedStates.count();
		size_t remainingCnt = totalStateCnt - selectedCnt;
		if (remainingCnt == 0)
			return Builder.getTrue();

		SmallVector<Value *, 16> Operands;
		if (selectedCnt <= remainingCnt) {
			for (uint64_t stI : SelectedStates) {
				if (!usedStates[stI])
					continue;
				Operands.push_back(OneHot[stI]);
			}
			return Builder.CreateOr(Operands);
		} else {
			StateBitmask isSelected;
			for (uint64_t stI : SelectedStates) {
				isSelected.set(stI);
			}
			for (uint64_t stI = 0; stI < maxStateCnt; ++stI) {
				if (usedStates[stI] && !isSelected[stI]) {
					Operands.push_back(OneHot[stI]);
				}
			}

			Value *RemainingOr = Builder.CreateOr(Operands);
			return Builder.CreateNot(RemainingOr);
		}
	}

	void appendUnsignedRange(uint64_t First, uint64_t Last,
							 SmallVectorImpl<uint64_t> &selected) {
		for (uint64_t stI = First; stI <= Last; ++stI) {
			if (!usedStates[stI]) {
				continue;
			}
			selected.push_back(stI);
			if (stI == Last)
				break;
		}
	}

	void getUnsignedRange(ICmpInst::Predicate Predicate, uint64_t C,
						  SmallVectorImpl<uint64_t> &selected) {
		switch (Predicate) {
		case ICmpInst::ICMP_ULT:
			if (C != 0)
				appendUnsignedRange(0, C - 1, selected);
			break;

		case ICmpInst::ICMP_ULE:
			appendUnsignedRange(0, C, selected);
			break;

		case ICmpInst::ICMP_UGT:
			if (C + 1 < maxStateCnt)
				appendUnsignedRange(C + 1, maxStateCnt - 1, selected);
			break;

		case ICmpInst::ICMP_UGE:
			if (C < maxStateCnt)
				appendUnsignedRange(C, maxStateCnt - 1, selected);
			break;
		default:
			llvm_unreachable("Not a unsigned predicate");
		}
	}

	void getSignedRange(ICmpInst::Predicate Predicate, int64_t ConstantState,
						SmallVectorImpl<uint64_t> &MatchingStates) {
		for (uint64_t stI = 0; stI < maxStateCnt; ++stI) {
			if (!usedStates[stI])
				continue;
			int64_t SignedState = stI;
			bool Matches = false;

			switch (Predicate) {
			case ICmpInst::ICMP_SLT:
				Matches = SignedState < ConstantState;
				break;
			case ICmpInst::ICMP_SLE:
				Matches = SignedState <= ConstantState;
				break;
			case ICmpInst::ICMP_SGT:
				Matches = SignedState > ConstantState;
				break;
			case ICmpInst::ICMP_SGE:
				Matches = SignedState >= ConstantState;
				break;
			default:
				llvm_unreachable("Not a signed predicate");
			}

			if (Matches)
				MatchingStates.push_back(stI);
		}
	}

	void rewriteICmp(ICmpInst &I) {
		ICmpInst::Predicate Predicate = I.getPredicate();

		// Swap the predicate when the Constant is the left operand.
		Value *Lhs = I.getOperand(0);
		Value *Rhs = I.getOperand(1);

		auto *rhsCI = dyn_cast<ConstantInt>(I.getOperand(1));
		if (!rhsCI) {
			rhsCI = dyn_cast<ConstantInt>(I.getOperand(0));
			if (rhsCI) {
				std::swap(Lhs, Rhs);
				Predicate = ICmpInst::getSwappedPredicate(Predicate);
			}
		}
		Value *LhsAddBase;
		ConstantInt *LhsAddOffset;
		if (match(Lhs,
				  m_Add(m_Value(LhsAddBase), m_ConstantInt(LhsAddOffset)))) {
			llvm_unreachable("[todo]");
		}
		rewriteValue(*Lhs);
		rewriteValue(*Rhs);
		// :note: there because insert may reallocate items in hash table
		auto LhsIt = oneHotMap.find(Lhs);
		assert(LhsIt != oneHotMap.end());
		auto RhsIt = oneHotMap.find(Rhs);
		assert(RhsIt != oneHotMap.end());

		Builder.SetInsertPoint(&I);
		SmallVector<uint64_t, 16> MatchingStates;
		Value *res = nullptr;
		if (rhsCI) {
			uint64_t rhsAsUInt = rhsCI->getValue().getZExtValue();
			int64_t rhsAsInt = rhsCI->getValue().getSExtValue();

			switch (Predicate) {
			case ICmpInst::ICMP_EQ:
				res = LhsIt->second[rhsAsUInt];
				break;

			case ICmpInst::ICMP_NE:
				res = Builder.CreateNot(LhsIt->second[rhsAsUInt]);
				break;

			case ICmpInst::ICMP_ULT:
			case ICmpInst::ICMP_ULE:
			case ICmpInst::ICMP_UGT:
			case ICmpInst::ICMP_UGE:
				getUnsignedRange(Predicate, rhsAsUInt, MatchingStates);
				res = createPredicate(LhsIt->second, MatchingStates, I);
				break;

			case ICmpInst::ICMP_SLT:
			case ICmpInst::ICMP_SLE:
			case ICmpInst::ICMP_SGT:
			case ICmpInst::ICMP_SGE:
				getSignedRange(Predicate, rhsAsInt, MatchingStates);
				res = createPredicate(LhsIt->second, MatchingStates, I);
				break;

			default:
				llvm_unreachable("Unsupported ICMP predicate");
			}
			assert(res);
		} else {
			auto newLhs = materializeBinValue(LhsIt->second);
			auto newRhs = materializeBinValue(RhsIt->second);
			res = Builder.CreateICmp(Predicate, newLhs, newRhs);
		}
		if (!res->hasName() && isa<Instruction>(res) && I.hasName()) {
			res->takeName(&I);
		}
		I.replaceAllUsesWith(res);
	}
	Value *materializeOneHotBitVec(const SmallVector<Value *, 16> &values) {
		SmallVector<Value *, 16> resBits;
		for (auto v : values) {
			if (!v) {
				v = Builder.getInt1(false);
			}
			resBits.push_back(v);
		}

		return hwtHls::CreateBitConcat(&Builder, resBits);
	}
	Value *materializeBinValue(const SmallVector<Value *, 16> &values) {
		auto oneHot = materializeOneHotBitVec(values);
		auto bin = Builder.CreateIntrinsic(Intrinsic::cttz, {oneHot->getType()},
										   {oneHot, /*isZeroPoisonous*/
											Builder.getTrue()});
		return Builder.CreateTrunc(bin, Builder.getIntNTy(stateWidth));
	}

	RewriteResult rewriteSelect(SelectInst &I) {
		rewriteValue(*I.getTrueValue());
		rewriteValue(*I.getFalseValue());
		// :note: there because insert may reallocate items in hash table
		auto TrueIt = oneHotMap.find(I.getTrueValue());
		assert(TrueIt != oneHotMap.end());
		auto FalseIt = oneHotMap.find(I.getFalseValue());
		assert(FalseIt != oneHotMap.end());

		Builder.SetInsertPoint(&I);
		OneHotEncodedVal Replacement;

		for (uint64_t stI = 0; stI < maxStateCnt; ++stI) {
			Value *NewI = nullptr;
			if (usedStates[stI]) {
				auto TV = TrueIt->second[stI];
				auto FV = FalseIt->second[stI];
				NewI =
					Builder.CreateSelect(I.getCondition(), TV, FV,
										 I.getName() + ".onehot." + Twine(stI));
			}
			Replacement.push_back(NewI);
		}

		auto inserted = oneHotMap.emplace(&I, std::move(Replacement));
		assert(inserted.second);
		return inserted;
	}

	void collectStateRelatedConstant(Constant &C,
									 std::unordered_set<Value *> &seen) {
		if (!seen.insert(&C).second) {
			return;
		}
		if (auto CI = dyn_cast<ConstantInt>(&C)) {
			usedStates.set(CI->getZExtValue());
		} else if (isa<PoisonValue>(&C)) {
			// poison notes that this case can not happen
		} else if (isa<UndefValue>(&C)) {
			// undef notes that there can be any value
			usedStates.set();
		}
	}
	void collectStateRelatedValue(Value &V, Instruction *UserForCtxI,
								  std::unordered_set<Value *> &seen) {
		if (auto C = dyn_cast<Constant>(&V)) {
			collectStateRelatedConstant(*C, seen);
		} else if (auto I = dyn_cast<Instruction>(&V)) {
			collectStateHandlingInstructions(*I, UserForCtxI, seen);
		}
	}

public:
	FsmToOneHotRewritter(LazyValueInfo *LVI, AssumptionCache *AC,
						 const DataLayout &DL, IRBuilder<> &Builder,
						 uint64_t stateWidth) :
		LVI(LVI),
		AC(AC),
		DL(DL),
		Builder(Builder),
		I1Ty(Builder.getInt1Ty()),
		stateWidth(stateWidth),
		maxStateCnt(1u << stateWidth) {
			assert(stateWidth > 1);
			usedStates.reset();
		}

	// :param UserForCtxI: an optional user of this instruction for cases
	//      where we need analyze the value of incompatible instruction
	// :return true if all seen instructions were compatible
	void collectStateHandlingInstructions(Instruction &I,
										  Instruction *UserForCtxI,
										  std::unordered_set<Value *> &seen) {
		if (!seen.insert(&I).second) {
			return;
		}
		assert(I.getParent());
		bool shouldFloodDefUse = true;
		// flood user->def
		if (auto phi = dyn_cast<PHINode>(&I)) {
			members.insert(&I);
			for (unsigned i = 0; i < phi->getNumIncomingValues(); ++i) {
				auto v = phi->getIncomingValue(i);
				auto BB = phi->getIncomingBlock(i);
				collectStateRelatedValue(*v, BB->getTerminator(), seen);
			}

		} else if (auto cmp = dyn_cast<ICmpInst>(&I)) {
			members.insert(&I);
			for (auto *O : cmp->operand_values()) {
				collectStateRelatedValue(*O, &I, seen);
			}
			shouldFloodDefUse = false;
		} else if (auto sel = dyn_cast<SelectInst>(&I)) {
			members.insert(&I);
			collectStateRelatedValue(*sel->getTrueValue(), &I, seen);
			collectStateRelatedValue(*sel->getFalseValue(), &I, seen);

		} else if (auto sw = dyn_cast<SwitchInst>(&I)) {
			memberSwitches.insert(sw);
			// collect states from case values, skip unreachable blocks
			if (!usedStates.all()) {
				if (!isa<UnreachableInst>(
						sw->getDefaultDest()->getTerminator())) {
					for (uint64_t stI = 0; stI < maxStateCnt; ++stI)
						usedStates.set(stI);
				}
				for (auto &C : sw->cases()) {
					if (isa<UnreachableInst>(
							C.getCaseSuccessor()->getTerminator())) {
						continue;
					}
					usedStates.set(C.getCaseValue()->getZExtValue());
				}
			}
			//} else if (isa<SExtInst>(&I) || isa<ZExtInst>(&I)) {
			//	if (I.getType()->getIntegerBitWidth() <= stateWidth) {
			//		collectStateRelatedValue(*I.getOperand(0));
			//	} else {
			//		supportedInstr = false;
			//	}
		} else if (match(&I, m_Add(m_Value(), m_ConstantInt()))) {
			// check for add used only as part of range compare
			// %off = add i16 %1, -3
			// %switch = icmp ult i16 %off, 2
			assert(!I.users().empty());
			bool usedOnlyInRangeCmp = true;
			for (auto U : I.users()) {
				auto cmp = dyn_cast<ICmpInst>(U);
				if (!cmp) {
					usedOnlyInRangeCmp = false;
					break;
				}
				if (cmp->getCmpPredicate() != CmpInst::ICMP_ULT) {
					usedOnlyInRangeCmp = false;
					break;
				}
				if (!isa<ConstantInt>(cmp->getOperand(0)) &&
					!isa<ConstantInt>(cmp->getOperand(1))) {
					usedOnlyInRangeCmp = false;
					break;
				}
			}
			if (!usedOnlyInRangeCmp) {
				members.insert(&I);
				if (UserForCtxI) {
					primaryInputs.insert(&I);
				} else {
					primaryOutputUsers.insert(&I);
				}
				return;
			}

		} else {
			if (UserForCtxI) {
				primaryInputs.insert(&I);
				KnownBits kb = computeKnownBits(&I, DL, AC, UserForCtxI);
				const ConstantRange LVIRange = LVI->getConstantRange(
					&I, UserForCtxI, /*UndefAllowed*/ false);
				for (uint64_t stI = 0; stI < maxStateCnt; ++stI) {
					if (usedStates[stI])
						continue;
					APInt stIAsAPInt(stateWidth, stI);
					if (!LVIRange.contains(stIAsAPInt))
						continue;
					bool possibleForKB =
						!kb.unionWith(llvm::KnownBits::makeConstant(stIAsAPInt))
							 .hasConflict();
					if (!possibleForKB) {
						continue;
					}
					usedStates.set(stI);
				}
			} else {
				primaryOutputUsers.insert(&I);
			}
			return;
		}

		if (shouldFloodDefUse) {
			// flood def->user
			for (auto U : I.users()) {
				if (auto UI = dyn_cast<Instruction>(U)) {
					collectStateHandlingInstructions(*UI, nullptr, seen);
				}
			}
		}
	}
	RewriteResult rewriteValue(Value &V) {
		if (auto I = dyn_cast<Instruction>(&V)) {
			return rewriteInstruction(*I);
		} else if (auto C = dyn_cast<Constant>(&V)) {
			return rewriteConstant(*C);
		} else {
			llvm_unreachable("Unsupported Value");
		}
	}
	void rewriteSwitch(SwitchInst &I) {
		SmallPtrSet<BasicBlock *, 8> DeleteList;
		auto C = I.getCondition();
		SmallPtrSet<User*, 32> cUsers;
		cUsers.insert_range(C->users());
		hwtHls::LowerSwitchWithIfChain::ProcessSwitchInst(&I, DeleteList, AC,
														  LVI);

		for (BasicBlock *BB : DeleteList) {
			LVI->eraseBlock(BB);
			llvm::DeleteDeadBlock(BB);
		}
		for (auto u: C->users()) {
			if (cUsers.contains(u))
				continue;
			auto UI = dyn_cast<ICmpInst>(u);
			assert(UI);
			members.insert(UI);
		}
	}
	RewriteResult rewriteInstruction(Instruction &I) {
		auto existing = oneHotMap.find(&I);
		if (existing != oneHotMap.end())
			return {existing, false};

		if (primaryInputs.contains(&I)) {
			Builder.SetInsertPoint(I.getNextNode());
			auto Ty = I.getType();
			OneHotEncodedVal newVal;
			for (uint64_t stI = 0; stI < maxStateCnt; ++stI) {
				Value *stBit = nullptr;
				if (usedStates[stI]) {
					auto stIC = ConstantInt::get(Ty, stI);
					stBit = Builder.CreateICmpEQ(&I, stIC);
				}
				newVal.push_back(stBit);
			}
			auto inserted = oneHotMap.emplace(&I, newVal);
			assert(inserted.second);
			return inserted;
		}
		if (auto phi = dyn_cast<PHINode>(&I)) {
			return rewritePhi(*phi);
		} else if (auto cmp = dyn_cast<ICmpInst>(&I)) {
			rewriteICmp(*cmp);
		} else if (auto sel = dyn_cast<SelectInst>(&I)) {
			return rewriteSelect(*sel);
		} else {
			llvm_unreachable("FsmToOneHotRewritter: Unsupported instruction");
		}
		return {oneHotMap.end(), false};
	}
	void rewritePhiOperands(PHINode &phi) {
		auto &phiReplaces = oneHotMap[&phi];
		for (uint64_t I = 0; I < phi.getNumIncomingValues(); ++I) {
			Value *IncomingValue = phi.getIncomingValue(I);
			BasicBlock *IncomingBlock = phi.getIncomingBlock(I);
			auto newVIt = rewriteValue(*IncomingValue).first;
			assert(newVIt != oneHotMap.end() &&
				   "this could be oneHotMap.end() only for SwitchInst or icmp, "
				   "none of these may be input of state phi");

			for (uint64_t stI = 0; stI < maxStateCnt; ++stI) {
				auto newPhi = phiReplaces[stI];
				if (!newPhi)
					continue;
				dyn_cast<PHINode>(newPhi)->addIncoming(newVIt->second[stI],
													   IncomingBlock);
			}
		}
	}
	void updatePrimaryOutputUser(Instruction &UI) {
		for (auto &Op : UI.operands()) {
			auto OpValI = dyn_cast<Instruction>(Op.get());
			if (!OpValI)
				continue;
			auto ohVal = oneHotMap.find(OpValI);
			if (ohVal != oneHotMap.end()) {
				auto rep = newBinValues.find(OpValI);
				if (rep != newBinValues.end()) {
					Op.set(rep->second);
				} else {
					if (isa<PHINode>(OpValI)) {
						Builder.SetInsertPoint(
							OpValI->getParent()->getFirstInsertionPt());
					} else {
						Builder.SetInsertPoint(OpValI);
					}
					auto newOp = materializeBinValue(ohVal->second);
					newBinValues[OpValI] = newOp;
					Op.set(newOp);
				}
			}
		}
	}
};

PreservedAnalyses FsmStateBinToOneHotPass::run(Function &F,
											   FunctionAnalysisManager &AM) {

	// first detect suitable phis
	//  * used only by phis, select, icmp_le(add(%v, c)), icmp, SwitchInst
	// llvm::ReversePostOrderTraversal<Function *> RPO(&F);
	SetVector<llvm::WeakVH> worklist;
	for (BasicBlock &BB : F) {
		for (PHINode &I : BB.phis()) {
			auto ITy = dyn_cast<IntegerType>(I.getType());
			if (!ITy)
				continue;
			if (ITy->getIntegerBitWidth() <= 1 ||
				 ITy->getIntegerBitWidth() >
					FsmToOneHotRewritter::BITWIDTH_LIMIT) {
				continue;
			}
			worklist.insert(&I);
			// if (PN && isCandidate(*PN)) {
			//	Candidates.push_back(PN);
			//	toRewrite.insert(PN);
			// } else if (any_of(I.operand_values(), [&toRewrite](Value *Op)
			// { 			   auto OpI = dyn_cast<Instruction>(Op);
			// return OpI &&
			// toRewrite.contains(OpI);
			//		   })) {
			//	toRewrite.insert(PN);
			// }
		}
	}
	if (worklist.empty())
		return PreservedAnalyses::all();

	LazyValueInfo *LVI = &AM.getResult<LazyValueAnalysis>(F);
	AssumptionCache *AC = AM.getCachedResult<AssumptionAnalysis>(F);
	bool Changed = false;
	bool ChangedCfg = false;
	IRBuilder<> Builder(F.getContext());
	while (!worklist.empty()) {
		auto V = worklist.pop_back_val();
		if (!V) {
			// the instruction was part of cluster of PHIs and were
			// already rewritten
			continue;
		}
		auto I = dyn_cast<PHINode>(V);
		assert(I);
		FsmToOneHotRewritter fsmReEnc(LVI, AC, F.getDataLayout(), Builder,
									  I->getType()->getIntegerBitWidth());
		{
			std::unordered_set<Value *> seen;
			fsmReEnc.collectStateHandlingInstructions(*I, nullptr, seen);
			if (fsmReEnc.members.size() == 1)
				continue;
		}
		{
			bool isWorthRewritting = !fsmReEnc.memberSwitches.empty();
			if (isWorthRewritting) {
				ChangedCfg = true;
			} else {
				for (auto *mI : fsmReEnc.members) {
					if (isa<ICmpInst>(mI)) {
						isWorthRewritting = true;
						break;
					}
				}
				if (!isWorthRewritting)
					continue;
			}
		}
		for (auto *SI: fsmReEnc.memberSwitches){
			fsmReEnc.rewriteSwitch(*SI);
		}
		for (auto *mI : fsmReEnc.members) {
			fsmReEnc.rewriteInstruction(*mI);
		}
		for (auto *U : fsmReEnc.primaryOutputUsers) {
			fsmReEnc.updatePrimaryOutputUser(*U);
		}
		SmallVector<PHINode*> phis;
		for (auto *mI : fsmReEnc.members) {
			if (auto phi = dyn_cast<PHINode>(mI)) {
				fsmReEnc.rewritePhiOperands(*phi);
				phis.push_back(phi);
			}
		}
		for (auto *mI : fsmReEnc.members) {
			LVI->forgetValue(mI);
			mI->replaceAllUsesWith(UndefValue::get(mI->getType()));
			mI->eraseFromParent();
		}

		Changed = true;
	}
	assert(!verifyFunction(F, &errs()));
	
	if (!Changed) {
		return PreservedAnalyses::all();
	} else {
		PreservedAnalyses PA;
		PA.preserve<LazyValueAnalysis>();
		PA.preserve<AssumptionAnalysis>();
		if (!ChangedCfg)
			PA.preserveSet<CFGAnalyses>();
		return PA;
	}
}

}