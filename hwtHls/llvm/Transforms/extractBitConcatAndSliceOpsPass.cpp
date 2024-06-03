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
	/// was in format Concat(0 on leftOffset bits, val, 0 on offset bits)
	unsigned leftOffset;
	Value *val;
	unsigned offset;

	unsigned getBitWidth() {
		return leftOffset + val->getType()->getIntegerBitWidth() + offset;
	}

	void print(raw_ostream &O, bool IsForDebug = false) const {
		O << "{" << leftOffset << ", ";
		if (val) {
			O << *val;
		} else {
			O << "NULL";
		}
		O << ", " << offset << "}";
	}
};
inline raw_ostream& operator<<(raw_ostream &OS, const OperandOffsetInfo &V) {
	V.print(OS);
	return OS;
}

static OperandOffsetInfo getOperandOffsetAndBaseValue(Value *v) {
	if (auto *c = dyn_cast<ConstantInt>(v)) {
		if (c->isZero()) {
			return {0, nullptr, c->getBitWidth()};
		} else {
			OperandOffsetInfo res;
			APInt v0 = c->getValue();
			res.leftOffset = v0.countLeadingZeros();
			res.offset = v0.countTrailingZeros();
			auto w = v0.getBitWidth();
			// select the non zero part in the middle to v0
			v0.lshrInPlace(res.offset);
			res.val = ConstantInt::get(v->getContext(),
					v0.trunc(w - res.leftOffset - res.offset));
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
							res.offset += op->getBitWidth();
						} else {
							res.leftOffset += op->getBitWidth();
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
						res.leftOffset += _res.leftOffset;
						res.val = _res.val;
						res.offset = _res.offset;
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
				res.offset += off;
			} else {
				res.leftOffset += -off;
			}
			return res;
		}
	} else if (auto *I = dyn_cast<CastInst>(v)) {
		if (I->getOpcode() == Instruction::CastOps::ZExt) {
			auto base = I->getOperand(0);
			return {I->getType()->getIntegerBitWidth() - base->getType()->getIntegerBitWidth(), base, 0};
		}
	}
	return {0, v, 0};

}

static bool tryOrToBitConcat(BinaryOperator *BO) {
	// %hwthls.bitConcat = call i2 @hwthls.bitConcat(i1 X, i1 0) (or X << 1)
	// %1 = zext i1 %0 to i2
	// %2 = or i2 %hwthls.bitConcat, %1
	OperandOffsetInfo highBits = getOperandOffsetAndBaseValue(
			BO->getOperand(1));
	OperandOffsetInfo lowBits = getOperandOffsetAndBaseValue(BO->getOperand(0));

	// swap so upper part is in left
	if (lowBits.offset != highBits.offset) {
		if (lowBits.offset > highBits.offset) {
			std::swap(lowBits, highBits);
		}
		std::vector<Value*> OpsLowFirst;
		unsigned leftWidth =
				highBits.val ?
						highBits.val->getType()->getIntegerBitWidth() : 0;
		unsigned rightWidth =
				lowBits.val ? lowBits.val->getType()->getIntegerBitWidth() : 0;
		unsigned resW = dyn_cast<IntegerType>(BO->getType())->getBitWidth();
		int highPad = (int) resW - int(leftWidth + highBits.offset);
		int middlePad = (int) highBits.offset
				- int(rightWidth + lowBits.offset);
		if (highPad >= 0 && middlePad >= 0) {
			// else the left and right overlaps and this is not the concatenation
			IRBuilder<> Builder(BO);

			if (lowBits.offset)
				OpsLowFirst.push_back(Builder.getIntN(lowBits.offset, 0));
			if (lowBits.val)
				OpsLowFirst.push_back(lowBits.val);
			if (middlePad)
				OpsLowFirst.push_back(Builder.getIntN(middlePad, 0));
			if (highBits.val)
				OpsLowFirst.push_back(highBits.val);
			if (highPad)
				OpsLowFirst.push_back(Builder.getIntN(highPad, 0));

			auto *res = CreateBitConcat(&Builder, OpsLowFirst);
			BO->replaceAllUsesWith(res);
			return true;
		}
	}
	return false;
}

static bool tryTruncToBitRangeGet(CastInst *CI) {
	// resT truncat(x >> C) -> resT hwthls.bitrangeGet1(x, C)
	auto resWidth = CI->getType()->getIntegerBitWidth();
	auto baseInfo = getOperandOffsetAndBaseValue(CI->getOperand(0));
	if (baseInfo.offset == 0 && baseInfo.leftOffset == 0) {
		IRBuilder<> Builder(CI);
		if (!baseInfo.val) {
			// all 0
			auto res = Builder.getIntN(resWidth, 0);
			CI->replaceAllUsesWith(res);
			return true;

		} else {
			llvm::Value *res = nullptr;
			if (auto *BI = dyn_cast<BinaryOperator>(CI->getOperand(0))) {
				if (BI->getOpcode() == Instruction::BinaryOps::Shl) {
					// non const shift
					res = CreateBitRangeGet(&Builder, CI, BI, resWidth);
				}
			}
			if (!res) {
				// just truncatenation (select of lower bits)
				res = CreateBitRangeGetConst(&Builder, CI, 0, resWidth);
			}
			CI->replaceAllUsesWith(res);
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
			if (off > base.leftOffset) {
				// (resTy)(base.val << (base.offset + off))
				unsigned newValWidth = resW - (base.offset + off);
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
				base.leftOffset = 0;
				base.offset += off;
				off = 0;
			}
			base.leftOffset -= off;
			base.offset += off;
		} else {
			return false; // [todo] need to slice
		}
		// swap so upper part is in o1
		std::vector<Value*> OpsLowFirst;
		unsigned width =
				base.val ? base.val->getType()->getIntegerBitWidth() : 0;
		int highPad = (int) resW - int(width + base.offset);
		if (highPad >= 0) {
			if (base.offset)
				OpsLowFirst.push_back(Builder.getIntN(base.offset, 0));
			if (base.val)
				OpsLowFirst.push_back(base.val);
			if (highPad)
				OpsLowFirst.push_back(Builder.getIntN(highPad, 0));

			auto *res = CreateBitConcat(&Builder, OpsLowFirst);
			BO->replaceAllUsesWith(res);
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
				} else if (auto *CI = dyn_cast<CastInst>(&I)) {
					if (CI->getOpcode() == Instruction::CastOps::Trunc) {
						if (tryTruncToBitRangeGet(CI))
							toRemove.push_back(CI);
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
