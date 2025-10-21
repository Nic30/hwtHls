#include <hwtHls/llvm/Transforms/BitcountMergePass.h>

#include <llvm/IR/PatternMatch.h>
#include <llvm/ADT/SetVector.h>
#include <map>

#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

#define DEBUG_TYPE "BitcountMergePass"
using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

// based on llvm-18 ControlHeightReduction.cpp/isHoistableInstructionType
// Return true if the given instruction type can be hoisted by CHR.
static bool isHoistableInstructionType(const Instruction *I) {
	if (isa<BinaryOperator>(I) || isa<CastInst>(I) || isa<SelectInst>(I)
			|| isa<GetElementPtrInst>(I) || isa<CmpInst>(I)
			|| isa<InsertElementInst>(I) || isa<ExtractElementInst>(I)
			|| isa<ShuffleVectorInst>(I) || isa<ExtractValueInst>(I)
			|| isa<InsertValueInst>(I))
		return true;
	if (auto CI = dyn_cast<CallInst>(I)) {
		if (auto II = dyn_cast<IntrinsicInst>(CI)) {
			auto ID = II->getIntrinsicID();
			switch (ID) {
			case Intrinsic::cttz:
			case Intrinsic::ctpop:
			case Intrinsic::umax:
			case Intrinsic::umin:
				return true;
			default:
				return  false;
			}
		}
		if (IsBitConcat(CI) || IsBitRangeGet(CI))
			return true;
	}
	return false;
}

// based on llvm-18 ControlHeightReduction.cpp/hoistValue
// Return true if V is already hoisted or was hoisted (along with its operands)
// to the insert point.
static bool hoistValue(Value *V, Instruction *HoistPoint,
		DenseSet<Instruction*> &HoistedSet, bool &changed) {
	if (auto *I = dyn_cast<Instruction>(V)) {
		if (I == HoistPoint)
			// it was just found out that to move some other value HoistPoint must also move, this means that
			// the original value depends on on HoistPoint and thus it is not possible to hoist it
			return false;
		if (HoistedSet.count(I))
			// Already hoisted, return.
			return true;
		if (I->getParent() != HoistPoint->getParent())
			return true; // this means that V is defined before this block
		assert(isHoistableInstructionType(I) && "Unhoistable instruction type");
		if (I->comesBefore(HoistPoint)) {
			// We are already above the hoist point. Stop here. This may be necessary
			// when multiple scopes would independently hoist the same
			// instruction. Since an outer (dominating) scope would hoist it to its
			// entry before an inner (dominated) scope would to its entry, the inner
			// scope may see the instruction already hoisted, in which case it
			// potentially wrong for the inner scope to hoist it and could cause bad
			// IR (non-dominating def), but safe to skip hoisting it instead because
			// it's already in a block that dominates the inner scope.
			HoistedSet.insert(I); // insert so we do not have to check dominance again
			return true;
		}
		assert(
				!isa<PHINode>(I)
						&& "This function should operate in a single block, it should not be required to hoist PHINodes");
		for (Value *Op : I->operands()) {
			if (!hoistValue(Op, HoistPoint, HoistedSet, changed)) {
				return false;
			}
		}
		changed = true;
		I->moveBefore(HoistPoint);
		HoistedSet.insert(I);
		LLVM_DEBUG(dbgs() << "hoistValue " << *I << "\n");
	}
	return true;
}
struct BitcountInstrCache {
	using FirstBitToBitcountMap = std::map<std::pair<size_t, Instruction*>, std::vector<IntrinsicInst*>>;
	// first is lsb
	FirstBitToBitcountMap cttzMap; // cttz(x)
	FirstBitToBitcountMap cttoMap; // cttz(~x)
	// first is msb
	FirstBitToBitcountMap ctlzMap; // ctlz(x)
	FirstBitToBitcountMap ctloMap; // cttz(x)
	// :note: if the instruction is in map it does mean that
	//        the src operand share first bit, but it may be entirely different
	//        vector and additional check is required before merging

	// used to have deterministic rewrite order
	SetVector<std::pair<size_t, Instruction*>> instrOrder;

	FirstBitToBitcountMap& getCacheForInstr(Intrinsic::ID Opc,
			bool srcIsNegated) {
		if (Opc == Intrinsic::cttz) {
			if (srcIsNegated) {
				return cttoMap;
			} else {
				return cttzMap;
			}
		} else {
			assert(Opc == Intrinsic::ctlz);
			if (srcIsNegated) {
				return ctloMap;
			} else {
				return ctlzMap;
			}
		}
	}
	void findBitcounts(Function &F) {
		for (auto &BB : F) {
			for (auto &I : BB) {
				if (auto II = dyn_cast<IntrinsicInst>(&I)) {
					Intrinsic::ID Opc = II->getIntrinsicID();
					switch (Opc) {
					case Intrinsic::cttz:
					case Intrinsic::ctlz: {
						Instruction *src = dyn_cast<Instruction>(
								II->getArgOperand(0));
						if (!src) {
							continue; // this is bitcount on constant
						}
						Value *_unnegatedSrc;
						Instruction *unnegatedSrc;
						if (match(src, m_Not(m_Value(_unnegatedSrc)))) {
							unnegatedSrc = dyn_cast<Instruction>(_unnegatedSrc);
						} else {
							unnegatedSrc = src;
						}

						// search for real first bit of bitcount
						bool searchFromLsb = Opc == Intrinsic::cttz;
						size_t off = 0;
						Instruction *srcBitVec = unnegatedSrc;
						auto srcCI = dyn_cast<CallInst>(unnegatedSrc);
						if (srcCI && IsBitRangeGet(srcCI)) {
							srcBitVec = dyn_cast<Instruction>(
									BitRangeGetSrc(srcCI));
							if (!srcBitVec)
								continue; // this is bitcount of slice on constant
							off = BitRangeGetOffset(srcCI);
						} else if (srcCI && IsBitConcat(srcCI)) {
							size_t firstArgI;
							if (searchFromLsb) {
								firstArgI = 0;
							} else {
								firstArgI = srcCI->arg_size() - 1;
							}
							srcBitVec = dyn_cast<Instruction>(
									srcCI->getArgOperand(firstArgI));
							if (!srcBitVec)
								continue; // lsb/msb in concat is constant
						}
						if (!searchFromLsb) {
							off += srcBitVec->getType()->getIntegerBitWidth()
									- 1;
						}
						std::pair<size_t, Instruction*> bitDescr = { off,
								srcBitVec };

						// resolve in which cache map this instruction will be potentially stored
						bool srcIsNegated = src != unnegatedSrc;
						auto &cacheMap = getCacheForInstr(Opc, srcIsNegated);

						// store found result in cache
						auto cur = cacheMap.find(bitDescr);
						if (cur != cacheMap.end()) {
							cur->second.push_back(II);
						} else {
							instrOrder.insert(bitDescr);
							cacheMap[bitDescr] = std::vector<IntrinsicInst*> {
									II };
						}
						break;
					}
					default:
						break;
					}
				}
			}
		}
	}
};

bool rewriteBitcounts(BitcountInstrCache &bitcountCache,
		IRBuilder<TargetFolder> &Builder, DceWorklist &dce) {
	bool changed = false;
	for (auto bitDescr : bitcountCache.instrOrder) {
		auto _bitcounts = bitcountCache.cttoMap.find(bitDescr);
		bool srcIsNegated = true;
		if (_bitcounts != bitcountCache.cttoMap.end()) {
			auto &bitcounts = _bitcounts->second;
			if (bitcounts.size() <= 1)
				continue;
			// sort, most wide first
			std::sort(bitcounts.begin(), bitcounts.end(),
					[](const IntrinsicInst *v0, const IntrinsicInst *v1) {
						return v0->getArgOperand(0)->getType()->getIntegerBitWidth()
								> v1->getArgOperand(0)->getType()->getIntegerBitWidth();
					});
			// collect instructions operating on exactly same vector and having same is_zero_poisonous flag
			for (auto cttoIIt = bitcounts.begin(); cttoIIt != bitcounts.end();
					++cttoIIt) {
				auto *cttoI = *cttoIIt;
				if (!cttoI)
					continue; // already reduced instr
				// :note: cttoI is the most wide available because vector is sorted
				//   and now we are searching for bitcounts with fewer bits
				auto is_zero_poison = cttoI->getArgOperand(1);
				auto src = cttoI->getArgOperand(0);
				if (srcIsNegated) {
					Instruction *_src;
					if (!match(src, m_Not(m_Instruction(_src)))) {
						llvm_unreachable("It should have been checked in advance that this is negation");
					}
					src = _src;
				}
				ConcatMemberVector srcBits;
				srcBits.push_back_flattened(src);
				// find any instructions which operate on sub bits of this instruction src,
				// so they can be rewritten as umin(cttoI, C) where C is number of bits of src operand
				SmallVector<IntrinsicInst*> compatibleInstr;

				for (auto cttoI2It = cttoIIt + 1;
						cttoI2It != bitcounts.end(); ++cttoI2It) {
					auto *cttoI2 = *cttoI2It;
					if (!cttoI2)
						continue; // already reduced instr
					if (cttoI->getParent() != cttoI2->getParent())
						continue; // this pass is implemented only only for bitcounts in the same block
					if (cttoI2->getArgOperand(1) != is_zero_poison)
						continue;
					auto src2 = cttoI->getArgOperand(0);
					if (srcIsNegated) {
						Instruction *_src;
						if (!match(src2, m_Not(m_Instruction(_src)))) {
							llvm_unreachable("Expect negated term");
						}
						src2 = _src;
					}
					ConcatMemberVector src2Bits;
					src2Bits.push_back_flattened(src2);
					DenseSet<Instruction*> HoistedSet;
					if (src2Bits.isLsbBitsOf(srcBits)
							&& hoistValue(cttoI, cttoI2, HoistedSet, changed)) {
						assert(cttoI->comesBefore(cttoI2) && "cttoI should dominate all instructions to rewrite");
						// hoist of cttoI before cttoI2 was successful, thus we can replace
						// cttoI2 with umin(cttoI, C) later
						compatibleInstr.push_back(cttoI2);
						*cttoI2It = nullptr;
					}
				}
				// rewrite compatible instructions to use cttoI instead
				size_t mainSrcWidth = src->getType()->getIntegerBitWidth();
				Builder.SetInsertPoint(cttoI->getNextNode());
				changed |= compatibleInstr.size();
				for (IntrinsicInst *ItoRewrite : compatibleInstr) {
					assert(cttoI->comesBefore(ItoRewrite) && "cttoI should dominate all instructions to rewrite");
					size_t subSrcWidth =
							ItoRewrite->getArgOperand(0)->getType()->getIntegerBitWidth();
					assert(subSrcWidth <= mainSrcWidth);
					assert(ItoRewrite != cttoI);
					dce.insert(*ItoRewrite);
					if (subSrcWidth == mainSrcWidth) {
						ItoRewrite->replaceAllUsesWith(cttoI);
					} else {
						// [todo] check if umin rhs behaves as expected for any is_zero_poison value
						Value *repl = Builder.CreateBinaryIntrinsic(
								Intrinsic::umin, cttoI,
								Builder.getIntN(mainSrcWidth, subSrcWidth));
						repl = Builder.CreateTrunc(repl, ItoRewrite->getType());
						repl->takeName(ItoRewrite);
						ItoRewrite->replaceAllUsesWith(repl);
					}
				}
			}
		}
	}
	return changed;
}

llvm::PreservedAnalyses BitcountMergePass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {

	auto &TLI = AM.getResult<TargetLibraryAnalysis>(F);
	auto &DL = F.getParent()->getDataLayout();

	BitcountInstrCache bitcountCache;
	bitcountCache.findBitcounts(F);

	// errs() << F << "\n";
	// errs() << "cttzMap:" << bitcountCache.cttzMap.size() << " cttoMap:"
	// 		<< bitcountCache.cttoMap.size() << " ctlzMap:"
	// 		<< bitcountCache.ctlzMap.size() << " ctloMap:"
	// 		<< bitcountCache.ctloMap.size() << "\n";
	/// Builder - This is an IRBuilder that automatically inserts new
	/// instructions into the worklist when they are created.
	IRBuilder<TargetFolder> Builder(F.getContext(), TargetFolder(DL));
	DceWorklist dce(&TLI);
	bool changed = rewriteBitcounts(bitcountCache, Builder, dce);
	changed |= dce.runToCompletition();
	if (changed) {
		// Mark all the analyses that instcombine updates as preserved.
		PreservedAnalyses PA;
		PA.preserveSet<CFGAnalyses>();
		return PA;
	} else {
		return llvm::PreservedAnalyses::all();
	}
}

}
