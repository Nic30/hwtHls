#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <llvm/ADT/StringExtras.h>

#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/bitMath.h>

using namespace llvm;

namespace hwtHls {

const std::string BitRangeGetName = "hwtHls.bitRangeGet";

llvm::Value* CreateBitRangeGetConst(llvm::IRBuilder<> *Builder,
		llvm::Value *bitVec, size_t lowBitNo, size_t bitWidth) {
	if (lowBitNo == 0 && bitWidth == bitVec->getType()->getIntegerBitWidth())
		return bitVec;
	size_t indexWidth = log2ceil(bitVec->getType()->getIntegerBitWidth()) + 1;
	return CreateBitRangeGet(Builder, bitVec,
			ConstantInt::get(
					IntegerType::get(Builder->getContext(), indexWidth),
					lowBitNo), bitWidth);
}

llvm::Value* SearchBitRangeGet(Instruction *bitVec, Value *lowBitNo,
		size_t bitWidth) {
	bool isTrunc = false;
	if (auto *lowBitNoC = dyn_cast<ConstantInt>(lowBitNo)) {
		if (lowBitNoC->isZero()) {
			isTrunc = true;
		}
	}
	for (auto suc = BasicBlock::iterator(bitVec);
			suc != bitVec->getParent()->end(); ++suc) {
		if (&*suc == bitVec)
			continue;
		if (isa<PHINode>(suc))
			continue;
		if (auto *Trunc = dyn_cast<TruncInst>(suc)) {
			if (isTrunc && Trunc->getType()->getIntegerBitWidth() == bitWidth)
				return Trunc;
		}
		if (auto *sucI = dyn_cast<CallInst>(suc)) {
			if (IsBitRangeGet(sucI) && sucI->getArgOperand(0) == bitVec) {
				if (sucI->getType()->getIntegerBitWidth() == bitWidth
						&& sucI->getArgOperand(1) == lowBitNo)
					return sucI;
			} else {
				break;
			}
		} else {
			break;
		}
	}
	return nullptr;
}

llvm::Value* CreateBitRangeGet(IRBuilder<> *Builder, Value *bitVec,
		Value *lowBitNo, size_t bitWidth) {
	auto *lowBitNoC = dyn_cast<ConstantInt>(lowBitNo);
	assert(lowBitNoC && "CreateBitRangeGet lowBitNo must be a constant");
	//assert(!lowBitNoC->isNegative());
	assert(
			lowBitNoC->getZExtValue() + bitWidth
					<= bitVec->getType()->getIntegerBitWidth()
					&& "Selected range must be in exiting bits");
	if (isa<UndefValue>(bitVec)) {
		return UndefValue::get(Builder->getIntNTy(bitWidth));
	} else if (auto bitVecCI = dyn_cast<CallInst>(bitVec)) {
		// if this is a slice on slice use slice on original vector instead
		if (IsBitRangeGet(bitVecCI) && lowBitNoC) {
			auto opLowIndex = dyn_cast<ConstantInt>(bitVecCI->getArgOperand(1));
			if (opLowIndex) {
				return CreateBitRangeGetConst(Builder,
						bitVecCI->getArgOperand(0),
						opLowIndex->getZExtValue() + lowBitNoC->getZExtValue(),
						bitWidth);
			}
		}
	} else if (auto Trunc = dyn_cast<TruncInst>(bitVec)) {
		return CreateBitRangeGet(Builder, Trunc->getOperand(0), lowBitNo,
				bitWidth);
	} else if (auto *Cast = dyn_cast<CastInst>(bitVec)) {
		// bitcast, zext, sext
		auto src = Cast->getOperand(0);
		if (src->getType()->getIntegerBitWidth()
				>= lowBitNoC->getZExtValue() + bitWidth) {
			// if selecting bits only in src operand
			return CreateBitRangeGet(Builder, src, lowBitNo, bitWidth);
		}
	}
	if (auto *bitVecInst = dyn_cast<Instruction>(bitVec)) {
		auto existing = SearchBitRangeGet(bitVecInst, lowBitNo, bitWidth);
		if (existing)
			return existing;
	}

	Value *Ops[] = { bitVec, lowBitNo };
	Type *ResT = Builder->getIntNTy(bitWidth);
	Type *Tys[] = { bitVec->getType(), lowBitNo->getType() };
	Type *TysForName[] = { bitVec->getType(), lowBitNo->getType(), ResT };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(BitRangeGetName, TysForName) + "."
							+ std::to_string(lowBitNoC->getZExtValue()), ResT,
					Tys[0], Tys[1]).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	TheFn->addFnAttr(Attribute::Speculatable);

	// resolve
	auto origIP = Builder->saveIP();
	CallInst *CI;
	bool updateIP = false;
	// resolve insertion point
	if (auto *bitVecInst = dyn_cast<Instruction>(bitVec)) {
		if (origIP.getPoint() != origIP.getBlock()->begin()) {
			auto pred = origIP.getPoint()->getPrevNode();
			if (pred == bitVec) {
				// inserting behind sliced vector
				updateIP = true;
			} else if (auto *_pred = dyn_cast<CallInst>(pred)) {
				if (IsBitRangeGet(_pred) && _pred->getArgOperand(0) == bitVec) {
					// insert behind some BitRangeGet on same bitVec
					updateIP = true;
				}
			}
		}
		if (!updateIP) {
			// original insertion point was not after bitVec or after some BitRangeGet on it, we must set insertion point there
			// so we can find it later
			IRBuilder_setInsertPointBehindPhi(*Builder,
					bitVecInst->getNextNode());
		}
	} else {
		updateIP = true;
	}
	CI = Builder->CreateCall(TheFn, Ops);
	if (!updateIP) {
		// restore IP because we changed it to be close to def of bitVec
		Builder->restoreIP(origIP);
	}
	CI->setDoesNotAccessMemory();
	return CI;
}

bool IsBitRangeGetInst(const llvm::Instruction *I) {
	if (isa<TruncInst>(I))
		return true;
	else if (auto C = dyn_cast<CallInst>(I))
		return IsBitRangeGet(C->getCalledFunction());
	return false;
}
bool IsBitRangeGet(const llvm::CallInst *C) {
	return IsBitRangeGet(C->getCalledFunction());
}
bool IsBitRangeGet(const llvm::Function *F) {
	assert(
			F != nullptr
					&& "Function must have definition if input code was valid");
	return F->getName().str().rfind(BitRangeGetName, 0) == 0;
}

const std::string BitConcatName = "hwtHls.bitConcat";
llvm::Value* CreateBitConcat(llvm::IRBuilder<> *Builder,
		llvm::ArrayRef<llvm::Value*> _OpsLowFirst) {
	if (_OpsLowFirst.size() == 1) {
		return _OpsLowFirst[0];
	} else {
		assert(_OpsLowFirst.size() > 0);
	}
	size_t bitWidth = 0;
	std::vector<Type*> ArgTys;
	ArgTys.reserve(_OpsLowFirst.size());
	std::vector<Value*> OpsLowFirst;
	bool lastWasConst = false;
	bool lastWasUndef = false;
	for (auto *o : _OpsLowFirst) {
		if (auto t = dyn_cast<IntegerType>(o->getType())) {
			auto w = t->getBitWidth();
			assert(w > 0 && "Can concatenate only int bit vectors");
			bitWidth += w;
		} else {
			throw std::runtime_error(
					"CreateBitConcat called with non-integer type");
		}
		if (auto *C = dyn_cast<ConstantInt>(o)) {
			if (lastWasConst) {
				// merge constants in operand vector
				auto prev =
						dyn_cast<ConstantInt>(OpsLowFirst.back())->getValue();
				auto cur = C->getValue();
				auto w = prev.getBitWidth() + cur.getBitWidth();
				auto v = cur.zext(w);
				v <<= prev.getBitWidth();
				v |= prev.zext(w);
				OpsLowFirst.pop_back();
				ArgTys.pop_back();
				auto *Ty = IntegerType::get(Builder->getContext(),
						v.getBitWidth());
				OpsLowFirst.push_back(ConstantInt::get(Ty, v));
				ArgTys.push_back(Ty);
				continue;
			}
			lastWasConst = true;
			lastWasUndef = false;
		} else {
			lastWasConst = false;
			if (auto *U = dyn_cast<UndefValue>(o)) {
				if (lastWasUndef) {
					// merge undefs in operand vector
					auto prev = dyn_cast<UndefValue>(OpsLowFirst.back());
					OpsLowFirst.pop_back();
					ArgTys.pop_back();
					auto *Ty = IntegerType::get(Builder->getContext(),
							prev->getType()->getIntegerBitWidth()
									+ U->getType()->getIntegerBitWidth());
					OpsLowFirst.push_back(UndefValue::get(Ty));
					ArgTys.push_back(Ty);
					continue;
				}
				lastWasUndef = true;
			}
		}
		OpsLowFirst.push_back(o);
		ArgTys.push_back(o->getType());
	}
	if (OpsLowFirst.size() == 1) {
		return OpsLowFirst[0];
	} else if (OpsLowFirst.size() == 2) {
		if (auto *o1asC = dyn_cast<ConstantInt>(OpsLowFirst[1])) {
			if (o1asC->isZero()) {
				Type *RetTy = Builder->getIntNTy(bitWidth);
				return Builder->CreateZExt(OpsLowFirst[0], RetTy);
			}
		}
	}

	Type *RetTy = Builder->getIntNTy(bitWidth);
	if (OpsLowFirst.size() > 1) {
		bool isSExt = true;
		for (auto member = OpsLowFirst.begin() + 1; member != OpsLowFirst.end();
				++member) {
			auto v = OffsetWidthValue::fromValue(*member);
			if (!v.isMsbOf(OpsLowFirst.front())) {
				isSExt = false;
				break;
			}
		}
		if (isSExt)
			return Builder->CreateSExt(OpsLowFirst.front(), RetTy);
	}
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();

	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(Intrinsic_getName(BitConcatName, ArgTys),
					FunctionType::get(RetTy, ArgTys, false)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	TheFn->addFnAttr(Attribute::Speculatable);

	CallInst *CI = Builder->CreateCall(TheFn, OpsLowFirst);
	CI->setDoesNotAccessMemory();
	return CI;
}

bool IsBitConcat(const llvm::CallInst *C) {
	return IsBitConcat(C->getCalledFunction());
}

bool IsBitConcatInst(const llvm::Instruction *I) {
	if (auto *C = dyn_cast<CallInst>(I))
		return IsBitConcat(C);
	return false;
}

bool IsBitConcat(const llvm::Function *F) {
	assert(F != nullptr);
	return F->getName().str().rfind(BitConcatName, 0) == 0;
}

}
