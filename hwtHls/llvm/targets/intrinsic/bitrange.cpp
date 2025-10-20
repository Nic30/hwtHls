#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <llvm/ADT/StringExtras.h>
#include <llvm/IR/PatternMatch.h>

#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/intrinsic/PatternMatch.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

const std::string BitRangeGetName = "hwtHls.bitRangeGet";

llvm::Value* CreateBitRangeGetConst(llvm::IRBuilderBase *Builder,
		llvm::Value *bitVec, size_t lowBitNo, size_t bitWidth,
		const llvm::Twine &Name) {
	if (lowBitNo == 0 && bitWidth == bitVec->getType()->getIntegerBitWidth())
		return bitVec;
	assert(bitWidth > 0);
	size_t indexWidth = log2ceil(bitVec->getType()->getIntegerBitWidth()) + 1;
	auto _lowBitNo = ConstantInt::get(
			IntegerType::get(Builder->getContext(), indexWidth), lowBitNo);
	return CreateBitRangeGet(Builder, bitVec, _lowBitNo, bitWidth, Name);
}

llvm::Value* CreateBitRangeGetMsb(llvm::IRBuilderBase *Builder,
		llvm::Value *bitVec, const llvm::Twine &Name) {
	return CreateBitRangeGetConst(Builder, bitVec,
			bitVec->getType()->getIntegerBitWidth() - 1, 1, Name);
}

llvm::Value* SearchBitRangeGetConst(Instruction *bitVec, size_t lowBitNo,
		size_t bitWidth) {
	size_t indexWidth = log2ceil(bitVec->getType()->getIntegerBitWidth()) + 1;
	auto _lowBitNo = ConstantInt::get(
			IntegerType::get(bitVec->getContext(), indexWidth), lowBitNo);
	return SearchBitRangeGet(bitVec, _lowBitNo, bitWidth);
}

llvm::Value* SearchBitRangeGet(Instruction *bitVec, Value *lowBitNo,
		size_t bitWidth) {
	assert(bitWidth > 0);
	bool isTrunc = false;
	auto *lowBitNoC = dyn_cast<ConstantInt>(lowBitNo);
	if (lowBitNoC) {
		if (lowBitNoC->isZero()) {
			if (bitWidth == bitVec->getType()->getIntegerBitWidth())
				return bitVec; // bitVec[MSB:0] == bitVec
			isTrunc = true;
		}
	}
	assert(bitWidth < bitVec->getType()->getIntegerBitWidth());

	auto BBEnd = bitVec->getParent()->end();
	if (bitVec->getNextNode()) {
		// search possible slices after this instruction
		bool srcIsPhi = isa<PHINode>(bitVec);
		for (auto suc = bitVec->getNextNode()->getIterator(); suc != BBEnd;
				++suc) {
			assert(&*suc);
			if (isa<PHINode>(suc))
				continue;
			if (auto *Trunc = dyn_cast<TruncInst>(suc)) {
				if (Trunc->getOperand(0) != bitVec) {
					if (srcIsPhi && isa<PHINode>(Trunc->getOperand(0)))
						continue; // slices of PHI may be mixed together,  we need to iterate all of them
					else
						break; // this is the last slice and we did not see any compatible
				}
				if (isTrunc
						&& Trunc->getType()->getIntegerBitWidth() == bitWidth) {
					return Trunc;
				}
			} else if (auto *sucI = dyn_cast<CallInst>(suc)) {
				if (IsBitRangeGet(sucI)) {
					auto sucISrcArg = sucI->getArgOperand(0);
					if (sucISrcArg == bitVec) {
						if (sucI->getType()->getIntegerBitWidth() == bitWidth
								&& sucI->getArgOperand(1) == lowBitNo) {
							return sucI;
						}
					} else if (srcIsPhi && isa<PHINode>(sucISrcArg)) {
						continue; // slices of PHI may be mixed together, we need to iterate all of them
					} else {
						break;
					}
				} else {
					break;
				}
			} else {
				break;
			}
		}
	}
	if (lowBitNoC) {
		// if bitVec is slice or concat try search slice on src operand(s)
		if (auto bitVecCI = dyn_cast<CallInst>(bitVec)) {
			if (IsBitConcat(bitVecCI)) {
				// if this is a slice on concat try extract members of concat
				auto selectOff = lowBitNoC->getZExtValue();
				size_t memberOff = 0;
				for (auto &concMember : bitVecCI->args()) {
					auto memberWidth =
							concMember->getType()->getIntegerBitWidth();
					size_t memberEnd = memberOff + memberWidth;
					size_t selectEnd = selectOff + bitWidth;
					if (memberOff == selectOff && memberWidth == bitWidth) { // exactly selects the member
						auto *existing = concMember.get();
						return existing;
					} else if (selectOff >= memberOff
							&& selectOff < memberEnd) {
						// select starts in this item
						if (selectEnd <= memberEnd) {
							// select also ending in this item
							if (auto srcI = dyn_cast<Instruction>(
									concMember.get())) {
								return SearchBitRangeGetConst(srcI,
										selectOff - memberOff, bitWidth); // selecting only from this member bits
							} else {
								return nullptr; // selected bits are not from instruction
							}
						} else {
							break; // this is selecting multiple members
						}
					}
					memberOff += memberWidth;
					if (memberOff > selectOff) {
						break; // do not search members which starting after selected start
					}
				}
			} else if (IsBitRangeGet(bitVecCI)) {
				if (auto opLowIndex = dyn_cast<ConstantInt>(
						bitVecCI->getArgOperand(1))) {
					if (auto srcI = dyn_cast<Instruction>(
							bitVecCI->getArgOperand(0))) {
						auto newOffset = opLowIndex->getZExtValue()
								+ lowBitNoC->getZExtValue();
						// src operand is also a slice, search slice on src of src
						return SearchBitRangeGetConst(srcI, newOffset, bitWidth);
					}
				}
			}
		}
	}
	return nullptr;
}

llvm::Value* CreateBitRangeGet(llvm::IRBuilderBase *Builder, Value *bitVec,
		Value *lowBitNo, size_t bitWidth, const llvm::Twine &Name) {
	auto *lowBitNoC = dyn_cast<ConstantInt>(lowBitNo);
	assert(lowBitNoC && "CreateBitRangeGet lowBitNo must be a constant");
	//assert(!lowBitNoC->isNegative());
	assert(
			lowBitNoC->getZExtValue() + bitWidth
					<= bitVec->getType()->getIntegerBitWidth()
					&& "Selected range must be in exiting bits");
	if (isa<UndefValue>(bitVec)) {
		auto resTy = Builder->getIntNTy(bitWidth);
		if (isa<PoisonValue>(bitVec))
			return PoisonValue::get(resTy);
		else
			return UndefValue::get(resTy);
	} else if (auto CI = dyn_cast<ConstantInt>(bitVec)) {
		auto resTy = Builder->getIntNTy(bitWidth);
		return ConstantInt::get(resTy,
				CI->getValue().extractBits(bitWidth, lowBitNoC->getZExtValue()));
	} else if (auto bitVecCI = dyn_cast<CallInst>(bitVec)) {
		if (lowBitNoC) {
			if (IsBitRangeGet(bitVecCI)) {
				// if this is a slice on slice use slice on original vector instead
				if (auto opLowIndex = dyn_cast<ConstantInt>(
						bitVecCI->getArgOperand(1))) {
					return CreateBitRangeGetConst(Builder,
							bitVecCI->getArgOperand(0),
							opLowIndex->getZExtValue()
									+ lowBitNoC->getZExtValue(), bitWidth, Name);
				}
			} else if (IsBitConcat(bitVecCI)) {
				// if this is a slice on concat try extract members of concat
				auto selectOff = lowBitNoC->getZExtValue();
				size_t memberOff = 0;
				for (auto &concMember : bitVecCI->args()) {
					auto memberWidth =
							concMember->getType()->getIntegerBitWidth();
					size_t memberEnd = memberOff + memberWidth;
					size_t selectEnd = selectOff + bitWidth;
					if (memberOff == selectOff && memberWidth == bitWidth) { // exactly selects the member
						auto *existing = concMember.get();
						if (!existing->hasName()) {
							existing->setName(Name);
						}
						return existing;
					} else if (selectOff >= memberOff
							&& selectOff < memberEnd) {
						// select starts in this item
						if (selectEnd <= memberEnd) {
							// select also ending in this item
							return CreateBitRangeGetConst(Builder,
									concMember.get(), selectOff - memberOff,
									bitWidth, Name); // selecting only from this member bits
						} else {
							break; // this is selecting multiple members
						}
					}
					memberOff += memberWidth;
					if (memberOff > selectOff) {
						break; // do not search members which starting after selected start
					}
				}
			}
		}
	} else if (auto Trunc = dyn_cast<TruncInst>(bitVec)) {
		return CreateBitRangeGet(Builder, Trunc->getOperand(0), lowBitNo,
				bitWidth, Name);
	} else if (auto *Cast = dyn_cast<CastInst>(bitVec)) {
		// bitcast, zext, sext
		auto src = Cast->getOperand(0);
		if (src->getType()->getIntegerBitWidth()
				>= lowBitNoC->getZExtValue() + bitWidth) {
			// if selecting bits only in src operand
			return CreateBitRangeGet(Builder, src, lowBitNo, bitWidth, Name);
		}
	}
	if (auto *bitVecInst = dyn_cast<Instruction>(bitVec)) {
		auto *existing = SearchBitRangeGet(bitVecInst, lowBitNo, bitWidth);
		if (existing) {
			if (!existing->hasName()) {
				existing->setName(Name);
			}
			return existing;
		}
	}

	Value *Ops[] = { bitVec, lowBitNo };
	for (auto O : Ops) {
		if (auto OAsI = dyn_cast<Instruction>(O)) {
			assert(OAsI->getParent() && "Check that the value is not erased");
			assert(
					OAsI->getParent()->getParent()
							&& "Check that the value is not erased");
		}
	}
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
		auto origIpPoint = origIP.getPoint();
		if (origIpPoint != origIP.getBlock()->begin()) {
			Instruction *pred;
			if (origIpPoint == origIP.getBlock()->end()) {
				pred = &origIP.getBlock()->back();
			} else {
				pred = origIpPoint->getPrevNode();
			}
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

	CI = Builder->CreateCall(TheFn, Ops, Name);
	CI->setDoesNotAccessMemory();

	if (!updateIP) {
		// restore IP because we changed it to be close to def of bitVec
		Builder->restoreIP(origIP);
	}

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
					&& "Function must have definition in parent Module if input code was valid");
	return F->getName().str().rfind(BitRangeGetName, 0) == 0;
}
llvm::Value* BitRangeGetSrc(const llvm::CallInst *C) {
	return C->getArgOperand(0);
}
size_t BitRangeGetOffset(const llvm::CallInst *C) {
	return dyn_cast<ConstantInt>(C->getArgOperand(1))->getZExtValue();
}

llvm::BasicBlock::iterator GetAfterSlicesInsertPoint(llvm::Instruction &I) {
	auto It = I.getIterator();
	It++;
	for (; It != I.getParent()->end(); ++It) {
		if (isa<llvm::TruncInst>(&*It)) {
			auto _src = It->getOperand(0);
			if (_src != &I)
				return It;
		} else if (auto CI = llvm::dyn_cast<llvm::CallInst>(&*It)) {
			if (IsBitRangeGet(CI)) {
				auto _src = CI->getArgOperand(0);
				if (_src != &I)
					return It;
			}
		} else {
			return It;
		}
	}
	return I.getParent()->end();
}

const std::string BitConcatName = "hwtHls.bitConcat";

llvm::Value* CreateBitConcat(llvm::IRBuilderBase *Builder,
		llvm::ArrayRef<llvm::Value*> _OpsLowFirst, const llvm::Twine &Name) {
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
		assert(o);
		if (auto t = dyn_cast<IntegerType>(o->getType())) {
			auto w = t->getBitWidth();
			assert(w > 0 && "Can concatenate only int bit vectors");
			bitWidth += w;
		} else {
			throw std::runtime_error(
					"CreateBitConcat called with non-integer type");
		}
		assert(
				(!lastWasConst || !lastWasUndef)
						&& "Only one of flags may be set at once");
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
				} else if (auto OAsI = dyn_cast<Instruction>(o)) {
					assert(
							OAsI->getParent()
									&& "Check that the value is not erased");
					assert(
							OAsI->getParent()->getParent()
									&& "Check that the value is not erased");
				}
				lastWasUndef = true;
			} else {
				lastWasUndef = false;
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
				return Builder->CreateZExt(OpsLowFirst[0], RetTy, Name);
			}
		}
	}

	Type *RetTy = Builder->getIntNTy(bitWidth);
	if (OpsLowFirst.size() > 1) {
		bool isSExt = true;
		Value* base = OpsLowFirst.front();
		bool baseIs1b = base->getType()->getIntegerBitWidth() == 1;
		for (auto member = OpsLowFirst.begin() + 1; member != OpsLowFirst.end();
				++member) {
			Value* memberV = *member;
			auto v = OffsetWidthValue::fromValue(memberV);
			if (v.isMsbOf(base))
				continue;
			if (baseIs1b && match(memberV, m_SExt(m_Specific(base)))) {
				// front is 1b and next item is just SExt of it
				continue;
			}
			isSExt = false;
			break;
		}
		if (isSExt)
			return Builder->CreateSExt(OpsLowFirst.front(), RetTy, Name);
	}
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();

	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(Intrinsic_getName(BitConcatName, ArgTys),
					FunctionType::get(RetTy, ArgTys, false)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	TheFn->addFnAttr(Attribute::Speculatable);

	CallInst *CI = Builder->CreateCall(TheFn, OpsLowFirst, Name);
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
	assert(
			F != nullptr
					&& "Function must have definition in parent Module if input code was valid");
	return F->getName().str().rfind(BitConcatName, 0) == 0;
}

bool isAnyFormOfBitRangeGet(llvm::Instruction *I) {
	size_t width, offset;
	Value *V;
	return match(I, m_Trunc(m_Value(V)))
			|| match(I,
					hwtHls::PatternMatch::m_BitrangeGet(m_Value(V), offset,
							width));
}

bool isAnyFormOfBitRangeGet(llvm::Instruction *I, llvm::Value *&src) {
	size_t width, offset;
	Value *V;
	if (match(I, m_Trunc(m_Value(V)))
			|| match(I,
					hwtHls::PatternMatch::m_BitrangeGet(m_Value(V), offset,
							width))) {
		if (src == nullptr) {
			src = V;
			return true;
		} else {
			return src == V;
		}
	}
	return false;
}

bool isAnyFormOfBitRangeGet(llvm::Instruction *I, llvm::Value *&src,
		size_t &offset) {
	size_t width;
	Value *V;
	if (match(I, m_Trunc(m_Value(V)))
			|| match(I,
					hwtHls::PatternMatch::m_BitrangeGet(m_Value(V), offset,
							width))) {
		if (src == nullptr) {
			src = V;
			return true;
		} else {
			return src == V;
		}
	}
	return false;
}

}
