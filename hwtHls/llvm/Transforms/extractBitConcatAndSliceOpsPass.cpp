#include <hwtHls/llvm/Transforms/extractBitConcatAndSliceOpsPass.h>

#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/Analysis/GlobalsModRef.h>
#include <llvm/IR/IRBuilder.h>
#include <algorithm>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>


using namespace llvm;

namespace hwtHls {
// [todo] use worklist

// @returns true if replaced and needs to be removed
static bool trySelectInstrToBitConcat(SelectInst *SI) {
	//   %1 = select i1 %0, i3 -1, i3 0  ->  %1 = Concat(%0, %0, %0)
	Value *C = SI->getCondition();
	auto RetTy = dyn_cast<IntegerType>(SI->getType());
	if (RetTy) {
		auto RetWidth = RetTy->getBitWidth();
		IRBuilder<> Builder(SI);

		ConstantInt *S0 = dyn_cast<ConstantInt>(SI->getTrueValue());
		ConstantInt *S1 = dyn_cast<ConstantInt>(SI->getFalseValue());
		if (S0 && S1) {
			APInt S0v = S0->getValue();
			APInt S1v = S1->getValue();
			std::vector<Value*> OpsLowFirst;
			Value *NotC = nullptr;
			Value *lastV = nullptr;
			for (unsigned i = 0; i < RetWidth; ++i) {
				auto b0 = S0v[i];
				auto b1 = S1v[i];
				Value *v;
				if (b0 && b1) {
					v = Builder.getInt1(1);
				} else if (b0) {
					v = C;
				} else if (b1) {
					if (!NotC) {
						NotC = Builder.CreateNot(C);
					}
					v = NotC;
				} else {
					v = Builder.getInt1(0);
				}
				if (lastV) {
					if (ConstantInt *curVarAsInt = dyn_cast<ConstantInt>(v)) {
						if (ConstantInt *lastVarAsInt = dyn_cast<ConstantInt>(
								lastV)) {
							// lastVarAsInt |= curVarAsInt << lastVarAsInt.width
							OpsLowFirst.pop_back();
							// concatenate integer constants
							auto lastW = lastVarAsInt->getType()->getIntegerBitWidth();
							auto curW = curVarAsInt->getType()->getIntegerBitWidth();
							APInt newV = lastVarAsInt->getValue().zext(
									lastW + curW);
							newV |= curVarAsInt->getValue().zext(lastW + curW)
									<< lastW;
							v = Builder.getInt(newV);
						}
					}
				}
				OpsLowFirst.push_back(v);
				lastV = v;

			}
			auto *res = CreateBitConcat(&Builder, OpsLowFirst);
			SI->replaceAllUsesWith(res);
			return true;
		}

	}
	return false;
}

struct OperandOffsetInfo {
	// the final original value from where this record was extracted
	/// was in format @hwtHls.bitConcat(0 on lowZeroCnt bits, val, 0 on highZeroCnt bits)
	unsigned lowZeroBitCnt;
	Value *val;
	unsigned highZeroBitCnt;

	unsigned getBitWidth() {
		return highZeroBitCnt + val->getType()->getIntegerBitWidth() + lowZeroBitCnt;
	}

	void print(raw_ostream &O, bool IsForDebug = false) const {
		O << "{" <<lowZeroBitCnt << ", ";
		if (val) {
			O << *val;
		} else {
			O << "NULL";
		}
		O << ", " << highZeroBitCnt << "}";
	}
};
inline raw_ostream& operator<<(raw_ostream &OS, const OperandOffsetInfo &V) {
	V.print(OS);
	return OS;
}

static OperandOffsetInfo getOperandOffsetAndBaseValue(Value *v) {
	if (auto *c = dyn_cast<ConstantInt>(v)) {
		if (c->isZero()) {
			return {c->getBitWidth(), nullptr, 0};
		} else {
			OperandOffsetInfo res;
			APInt v0 = c->getValue();
			res.highZeroBitCnt = v0.countLeadingZeros();
			res.lowZeroBitCnt = v0.countTrailingZeros();
			auto w = v0.getBitWidth();
			// select the non zero part in the middle to v0
			v0.lshrInPlace(res.lowZeroBitCnt);
			res.val = ConstantInt::get(v->getContext(),
					v0.trunc(w - res.highZeroBitCnt - res.lowZeroBitCnt));
			return res;
		}
	} else if (auto *Call = dyn_cast<CallInst>(v)) {
		if (IsBitConcat(Call)) {
			// find offset from left (high bit)
			// find offset from right (low bit)
			OperandOffsetInfo res = { 0, nullptr, 0 };
			bool found = true;
			for (Use &_op : Call->args()) {
				if (auto *op = dyn_cast<ConstantInt>(_op.get())) {
					if (op->isZero()) {
						if (res.val) {
							res.highZeroBitCnt += op->getBitWidth();
						} else {
							res.lowZeroBitCnt += op->getBitWidth();
						}
					} else {
						// not in correct format there must be at most 1 non zero operand
						// and if it is a constant it should be already concatenated and not in BitConcat function
						found = false;
						break;
					}
				} else {
					// found something which is not constant
					if (res.val) {
						found = false;
						break;
					} else {
						// recursively search offsets and merge them with current state
						auto _res = getOperandOffsetAndBaseValue(_op.get());
						res.highZeroBitCnt += _res.highZeroBitCnt;
						res.val = _res.val;
						res.lowZeroBitCnt = _res.lowZeroBitCnt;
					}
				}
			}

			if (found)
				return res;
		}
	} else if (auto *I = dyn_cast<BinaryOperator>(v)) {
		bool shiftFound = false;
		unsigned off = 0;
		if (I->getOpcode() == Instruction::BinaryOps::LShr) {
			if (ConstantInt *sh = dyn_cast<ConstantInt>(I->getOperand(1))) {
				off = -sh->getSExtValue();
				shiftFound = true;

			}
		} else if (I->getOpcode() == Instruction::BinaryOps::Shl) {
			if (ConstantInt *sh = dyn_cast<ConstantInt>(I->getOperand(1))) {
				off = sh->getSExtValue();
				shiftFound = true;
			}
		}
		if (shiftFound) {
			auto res = getOperandOffsetAndBaseValue(I->getOperand(0));
			if (off > 0) {
				res.lowZeroBitCnt += off;
			} else {
				res.highZeroBitCnt += -off;
			}
			return res;
		}
	} else if (auto *I = dyn_cast<CastInst>(v)) {
		if (I->getOpcode() == Instruction::CastOps::ZExt) {
			auto base = I->getOperand(0);
			return {0, base, I->getType()->getIntegerBitWidth() - base->getType()->getIntegerBitWidth()};
		}
	}
	return {0, v, 0};

}

static bool tryOrToBitConcat(BinaryOperator *BO) {
	// %v0 = call i2 @hwthls.bitConcat(i1 %x0, i1 0) (or %X << 1)
	// %v1 = zext i1 %x1 to i2
	// %v2 = or i2 %v0, %v1 # each bit is 0 in some operand, thus this is concatenation
	// to 
	// %v2 = call i2 @hwthls.bitConcat(i1 %x0, i1 %x1)
	// :note: the zeros are reduced from both sides (lsb/msb) and are allowed in the middle,
	//    
	OperandOffsetInfo lBits = getOperandOffsetAndBaseValue(
			BO->getOperand(1));
	OperandOffsetInfo rBits = getOperandOffsetAndBaseValue(BO->getOperand(0));

	if (rBits.lowZeroBitCnt != lBits.lowZeroBitCnt) {
		if (rBits.lowZeroBitCnt < lBits.lowZeroBitCnt) {
			// swap so upper part is in right
			std::swap(rBits, lBits);
		}
		unsigned lWidth =
				lBits.val ?
						lBits.val->getType()->getIntegerBitWidth() : 0;
		int middlePad = (int) rBits.lowZeroBitCnt
				- int(lBits.lowZeroBitCnt + lWidth); // begin of higher value part - end of lower value part
		if (middlePad >= 0) {
			assert(lBits.lowZeroBitCnt + lWidth + rBits.highZeroBitCnt <= BO->getType()->getIntegerBitWidth());
			// else the left and right overlaps and this is not the concatenation
			IRBuilder<> Builder(BO);

			SmallVector<Value*, 5> OpsLowFirst;
			if (lBits.lowZeroBitCnt)
				OpsLowFirst.push_back(Builder.getIntN(rBits.lowZeroBitCnt, 0));
			if (lBits.val)
				OpsLowFirst.push_back(rBits.val);
			if (middlePad)
				OpsLowFirst.push_back(Builder.getIntN(middlePad, 0));
			if (rBits.val)
				OpsLowFirst.push_back(rBits.val);
			if (rBits.highZeroBitCnt)
				OpsLowFirst.push_back(Builder.getIntN(rBits.highZeroBitCnt, 0));

			auto *res = CreateBitConcat(&Builder, OpsLowFirst);
			auto resI = dyn_cast<Instruction>(res);
			if (resI && !resI->hasName())
				resI->takeName(BO);
			BO->replaceAllUsesWith(res);
			return true;
		}
	}
	return false;
}

static bool tryShlToBitConcat(BinaryOperator *BO) {
	// %0 = zext i4 %i0 to i8
	// %1 = shl nuw i8 %0, 4
	// to
	// %1 = @hwtHls.bitConcat i4 %i0, i4 0
	if (ConstantInt *sh = dyn_cast<ConstantInt>(BO->getOperand(1))) {
		OperandOffsetInfo base = getOperandOffsetAndBaseValue(
				BO->getOperand(0));
		unsigned resW = BO->getType()->getIntegerBitWidth();
		auto off = sh->getSExtValue();

		IRBuilder<> Builder(BO);
		if (off > 0) {
			if (off > base.highZeroBitCnt) {
				// (resTy)(base.val << (base.offset + off))
				unsigned newValWidth = resW - (base.lowZeroBitCnt + off);
				if (!base.val) {
					// all 0
				} else if (auto *C = dyn_cast<ConstantInt>(base.val)) {
					// slice base.val to newValWidth
					APInt v = C->getValue();
					base.val = Builder.getInt(v.trunc(newValWidth));

				} else {
					// slice base.val to newValWidth
					base.val = CreateBitRangeGetConst(&Builder, base.val, 0, newValWidth);
				}
				base.highZeroBitCnt = 0;
				base.lowZeroBitCnt += off;
				off = 0;
			}
			base.highZeroBitCnt -= off;
			base.lowZeroBitCnt += off;
		} else {
			return false; // [todo] need to slice
		}
		// swap so upper part is in o1
		std::vector<Value*> OpsLowFirst;
		unsigned width =
				base.val ? base.val->getType()->getIntegerBitWidth() : 0;
		int highPad = (int) resW - int(width + base.lowZeroBitCnt);
		if (highPad >= 0) {
			if (base.lowZeroBitCnt)
				OpsLowFirst.push_back(Builder.getIntN(base.lowZeroBitCnt, 0));
			if (base.val)
				OpsLowFirst.push_back(base.val);
			if (highPad)
				OpsLowFirst.push_back(Builder.getIntN(highPad, 0));

			auto *res = CreateBitConcat(&Builder, OpsLowFirst);
			BO->replaceAllUsesWith(res);
			auto resI = dyn_cast<Instruction>(res);
			if (resI && !resI->hasName())
				resI->takeName(BO);
			return true;
		}
	}

	return false;
}

PreservedAnalyses ExtractBitConcatAndSliceOpsPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	while (true) {
		std::vector<Instruction*> toRemove;
		for (BasicBlock &BB : F) {
			for (Instruction &I : BB) {

				if (auto *SI = dyn_cast<SelectInst>(&I)) {
					if (trySelectInstrToBitConcat(SI)) {
						toRemove.push_back(&I);
					}
				} else if (auto *BO = dyn_cast<BinaryOperator>(&I)) {
					if (BO->getOpcode() == Instruction::BinaryOps::Or) {
						if (tryOrToBitConcat(BO))
							toRemove.push_back(BO);
					} else if (BO->getOpcode() == Instruction::BinaryOps::Shl) {
						if (tryShlToBitConcat(BO))
							toRemove.push_back(BO);
					}
				}
			}
			for (Instruction *I : toRemove) {
				I->eraseFromParent();
			}
			toRemove.clear();
		}
		if (toRemove.empty()) {
			break;
		}
	}
	// Mark all the analyses that instcombine updates as preserved.
	PreservedAnalyses PA;
	PA.preserveSet<CFGAnalyses>();
	PA.preserve<AAManager>();
	PA.preserve<BasicAA>();
	PA.preserve<GlobalsAA>();
	return PA;
}

}
