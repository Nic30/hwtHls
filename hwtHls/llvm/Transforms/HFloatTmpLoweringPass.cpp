#include <hwtHls/llvm/Transforms/HFloatTmpLoweringPass.h>

#include <unordered_map>
#include <unordered_set>
#include <math.h>

#include <llvm/IR/Instructions.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Constants.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>

using namespace llvm;

namespace hwtHls {

void propagateTypeDefToUse(const HFloatTmpConfig &fpCfg, Instruction &I,
		std::unordered_map<Instruction*, HFloatTmpConfig> &newInstructionType) {
	auto curUserFpCfg = newInstructionType.find(&I);
	if (curUserFpCfg != newInstructionType.end()) {
		assert(
				curUserFpCfg->second == fpCfg
						&& "All paths in code must resolve to the same type");
		return;
	}

	newInstructionType[&I] = fpCfg;
	// propagate type def->use until CastFromHFloatTmp, FCmp is found
	for (auto *_UI : I.users()) {
		if (auto UI = dyn_cast<Instruction>(_UI)) {
			if (!UI->getType()->isDoubleTy()) {
				newInstructionType[&I] = fpCfg;
				continue;
			}
			propagateTypeDefToUse(fpCfg, *UI, newInstructionType);
		}
	}
}

void propagateTypeUseToDef(const HFloatTmpConfig &fpCfg, Instruction &I,
		std::unordered_map<Instruction*, HFloatTmpConfig> &newInstructionType,
		std::unordered_set<Instruction*> &seen) {
	// :note: seen is required because DefToUse search can
	// propagate type use->def until CastToHFloatTmp is found
	auto curUserFpCfg = newInstructionType.find(&I);
	if (curUserFpCfg != newInstructionType.end()) {
		assert(
				curUserFpCfg->second == fpCfg
						&& "All paths in code must resolve to the same type");
		if (seen.contains(&I))
			return;
	} else {
		newInstructionType[&I] = fpCfg;
	}
	seen.insert(&I);
	for (auto &O : I.operands()) {
		if (!O.get()->getType()->isDoubleTy())
			continue;

		if (auto UI = dyn_cast<Instruction>(O.get())) {
			if (auto CI = dyn_cast<CallInst>(UI)) {
				if (IsCastToHFloatTmp(CI))
					continue;
			}
			propagateTypeUseToDef(fpCfg, *UI, newInstructionType, seen);
		}
	}
}

template<typename INT_T>
INT_T mask(size_t numberOfBits) {
	static_assert(!std::is_signed<INT_T>::value);
	INT_T v = -1;
	v >>= (sizeof v) * 8 - numberOfBits;
	return v;
}

ConstantInt* bitCastConstantFPToHFlowatTmp(const HFloatTmpConfig &fpCfg,
		const ConstantFP &CF) {
	// IEEE-754 s special meanings
	//
	// Meaning             Sign Field   Exponent Field    Mantissa Field
	// Zero                Don't care   All 0s            All 0s
	// Positive subnormal  0            All 0s            Non-zero
	// Negative subnormal  1            All 0s            Non-zero
	// Positive Infinity   0            All 1s            All 0s
	// Negative Infinity   1            All 1s            All 0s
	// Not a Number(NaN)   Don't care   All 1s            Non-zero
	auto res = APInt(fpCfg.getBitWidth(), 0);
	auto v = CF.getValue();
	auto vAsDouble = v.convertToDouble();
	auto vAsAPInt = v.bitcastToAPInt();
	// bool issubnormal_ = issubnormal(vAsDouble);
	size_t CUR_MANTISA_W = 52;
	size_t CUR_EXP_W = 11;

	uint64_t mantissa = vAsAPInt.extractBits(CUR_MANTISA_W, 0).getZExtValue();
	uint64_t _exponent =
			vAsAPInt.extractBits(CUR_EXP_W, CUR_MANTISA_W).getZExtValue();
	int exponent = ((int) _exponent) + -mask<unsigned>(CUR_EXP_W - 1);
	uint64_t sign =
			vAsAPInt.extractBits(1, CUR_EXP_W + CUR_MANTISA_W).getZExtValue();
	size_t offset = 0;
	bool isInf = isinf(vAsDouble);
	// resolve mantissa/exponent or int and frac part if it is in Q format
	if (fpCfg.isInQFromat) {
		const size_t numWidth = fpCfg.exponentOrIntWidth
				+ fpCfg.mantissaOrFracWidth;
		if (isnan(vAsDouble) || vAsDouble == 0.0
				|| (issubnormal(vAsDouble) && !fpCfg.supportSubnormal)) {
			// keep all bits 0
			offset += numWidth;
		} else if (isinf(vAsDouble)) {
			// set to max value
			res.setBits(offset, offset + fpCfg.mantissaOrFracWidth);
			offset += fpCfg.mantissaOrFracWidth;
			res.setBits(offset, offset + fpCfg.exponentOrIntWidth);
			offset += fpCfg.exponentOrIntWidth;
		} else {
			assert(
					fpCfg.exponentOrIntWidth + fpCfg.mantissaOrFracWidth < 64
							&& "Rounding may have happened");
			if (issubnormal(vAsDouble))
				llvm_unreachable(
						"NotImplemented: convert subnormal constant to Q format");
			// shift mantissa on proper position
			mantissa |= 1 << CUR_MANTISA_W; // set first 1 which was omitted in FP mantissa format
			int fracWidth = CUR_MANTISA_W;
			int requiredFracWidth = fpCfg.mantissaOrFracWidth;
			int rshiftAmountToAliginFrac = fracWidth - requiredFracWidth;
			int rshiftAmount = rshiftAmountToAliginFrac + exponent;
			if (rshiftAmount < 0) {
				mantissa <<= -rshiftAmount;
			} else {
				mantissa >>= rshiftAmount;
			}
			res |= mantissa & mask<uint64_t>(numWidth);
			offset += numWidth;
		}
	} else {
		size_t newMantisaW = fpCfg.mantissaOrFracWidth;
		if (_exponent == 0) {
			// exponent == all 0
			if (mantissa == 0) {
				// zero case
			} else {
				// subnormal case
				if (fpCfg.supportSubnormal) {
					if (newMantisaW < CUR_MANTISA_W)
						mantissa >>= CUR_MANTISA_W - newMantisaW;
				} else {
					mantissa = 0;
				}
			}
		} else if (_exponent == mask<uint64_t>(CUR_EXP_W)) {
			// exponent == all 1
			if (mantissa == 0) {
				// inf case
			} else {
				// nan case
				mantissa = mask<uint64_t>(newMantisaW);
			}
		} else {
			size_t shiftedOutBits = 0;
			if (CUR_MANTISA_W > newMantisaW) {
				// need to shift mantissa and update exponent
				auto shAmount = CUR_MANTISA_W - newMantisaW;
				shiftedOutBits |= (mantissa & mask<uint64_t>(shAmount)) << (64 - shAmount);
				mantissa >>= shAmount;
			}
			int newExpOffset = -mask<unsigned>(fpCfg.exponentOrIntWidth - 1);
			int newExpMin = newExpOffset;
			int newExpMax = -newExpOffset + 1;
			if (exponent < newExpMin) {
				// may become 0 or subnormal
				size_t shAmount = -exponent - -newExpMin;
				shiftedOutBits >>= shAmount;
				shiftedOutBits |= (mantissa & mask<uint64_t>(shAmount)) << (64 - shAmount);
				if (shiftedOutBits != 0 && fpCfg.supportSubnormal) {
					llvm_unreachable("NotImplemented: convert fp constant which become subnormal to a fp type of a different width");
				}
			} else if (exponent > newExpMax) {
				// become +-inf
				isInf = true;
				exponent = newExpMin - 1;
				mantissa = 0;
			}
			res.insertBits(mantissa, offset, fpCfg.mantissaOrFracWidth);
			offset += fpCfg.mantissaOrFracWidth;
			size_t newExponent = (exponent + -newExpOffset) & mask<uint64_t>(fpCfg.exponentOrIntWidth);
			res.insertBits(newExponent, offset, fpCfg.exponentOrIntWidth);
			offset += fpCfg.exponentOrIntWidth;
		}
	}

	// fill sign and other special flags
	if (fpCfg.hasSign) {
		if (sign) {
			res.setBit(offset);
		}
		offset += 1;
	} else {
		assert(
				!sign
						&& "Can not convert negative float constant to type without sign");
	}
	if (fpCfg.hasIsNaN) {
		if (isnan(vAsDouble)) {
			res.setBit(offset);
		}
		offset += 1;
	} else {
		assert(
				!(fpCfg.isInQFromat && isnan(vAsDouble))
						&& "Can not convert NaN constant to q formated number without isNaN flag");
	}
	if (fpCfg.hasIsInf) {
		if (isInf) {
			res.setBit(offset);
		}
		offset += 1;
	} else {
		assert(
				!(fpCfg.isInQFromat && isInf)
						&& "Can not convert Inf constant to q formated number without isInf flag");
	}
	if (fpCfg.hasIs1) {
		if (vAsDouble == 1.0) {
			res.setBit(offset);
		}
		offset += 1;
	}
	if (fpCfg.hasIs0) {
		if (vAsDouble == 0.0) {
			res.setBit(offset);
		}
		offset += 1;
	}
	return ConstantInt::get(CF.getContext(), res);
}

Value* createSpecializedInstruction(IRBuilder<> &Builder, Instruction &I,
		std::unordered_map<Instruction*, HFloatTmpConfig> &newInstructionType,
		std::unordered_map<Instruction*, Value*> &newInstructions);
Value* createSpecializedValue(IRBuilder<> &Builder,
		const HFloatTmpConfig &fpCfg, Value &V,
		std::unordered_map<Instruction*, HFloatTmpConfig> &newInstructionType,
		std::unordered_map<Instruction*, Value*> &newInstructions) {
	if (!V.getType()->isDoubleTy())
		return &V;
	if (auto I = dyn_cast<Instruction>(&V)) {
		return createSpecializedInstruction(Builder, *I, newInstructionType,
				newInstructions);
	} else if (auto CF = dyn_cast<ConstantFP>(&V)) {
		return bitCastConstantFPToHFlowatTmp(fpCfg, *CF);
	} else {
		errs() << V << "\n";
		llvm_unreachable("Unsupported value for HFloatTmpLoweringPass");
	}
}
Value* createSpecializedInstruction(IRBuilder<> &Builder, Instruction &I,
		std::unordered_map<Instruction*, HFloatTmpConfig> &newInstructionType,
		std::unordered_map<Instruction*, Value*> &newInstructions) {
	auto newInstr = newInstructions.find(&I);
	if (newInstr != newInstructions.end()) {
		return newInstr->second;
	}
	auto _newFpTyCfg = newInstructionType.find(&I);
	if (_newFpTyCfg == newInstructionType.end())
		return &I; // not relevant instr
	HFloatTmpConfig newFpTyCfg = _newFpTyCfg->second;

	Builder.SetInsertPoint(&I);
	auto newTy = Builder.getIntNTy(newFpTyCfg.getBitWidth());
	if (auto phi = dyn_cast<PHINode>(&I)) {
		auto newI = Builder.CreatePHI(newTy, phi->getNumIncomingValues(),
				I.getName());
		newInstructions[&I] = newI;
		for (const auto& [BB, V] : zip(phi->blocks(), phi->incoming_values())) {
			auto newIncV = createSpecializedValue(Builder, newFpTyCfg, *V,
					newInstructionType, newInstructions);
			newI->addIncoming(newIncV, BB);
		}
		return newI;
	} else {
		Value *newI = nullptr;
		auto *opConstructor = &CreateHwtHlsFpFAdd;
		if (auto binOp = dyn_cast<BinaryOperator>(&I)) {
			switch (binOp->getOpcode()) {
			case BinaryOperator::BinaryOps::FAdd:
				opConstructor = &CreateHwtHlsFpFAdd;
				break;
			case BinaryOperator::BinaryOps::FSub:
				opConstructor = &CreateHwtHlsFpFSub;
				break;
			case BinaryOperator::BinaryOps::FMul:
				opConstructor = &CreateHwtHlsFpFMul;
				break;
			case BinaryOperator::BinaryOps::FDiv:
				opConstructor = &CreateHwtHlsFpFDiv;
				break;
			case BinaryOperator::BinaryOps::FRem:
				opConstructor = &CreateHwtHlsFpFRem;
				break;
			default:
				errs() << I << "\n";
				llvm_unreachable("Unsupported value for HFloatTmpLoweringPass");
			}
			auto op0 = binOp->getOperand(0);
			op0 = createSpecializedValue(Builder, newFpTyCfg, *op0,
					newInstructionType, newInstructions);
			auto op1 = binOp->getOperand(1);
			op1 = createSpecializedValue(Builder, newFpTyCfg, *op1,
					newInstructionType, newInstructions);
			newI = (*opConstructor)(&Builder, op0, op1,
					newFpTyCfg.exponentOrIntWidth,
					newFpTyCfg.mantissaOrFracWidth, newFpTyCfg.isInQFromat,
					newFpTyCfg.supportSubnormal, newFpTyCfg.hasSign,
					newFpTyCfg.hasIsNaN, newFpTyCfg.hasIsInf, newFpTyCfg.hasIs1,
					newFpTyCfg.hasIs0, I.getName());
		} else if (auto SI = dyn_cast<SelectInst>(&I)) {
			auto opC = SI->getCondition();
			opC = createSpecializedValue(Builder, newFpTyCfg, *opC,
					newInstructionType, newInstructions);
			auto opT = SI->getTrueValue();
			opT = createSpecializedValue(Builder, newFpTyCfg, *opT,
					newInstructionType, newInstructions);
			auto opF = SI->getFalseValue();
			opF = createSpecializedValue(Builder, newFpTyCfg, *opF,
					newInstructionType, newInstructions);
			newI = Builder.CreateSelect(opC, opT, opF, I.getName());
		} else if (auto CI = dyn_cast<CallInst>(&I)) {
			if (IsCastToHFloatTmp(CI)) {
				auto *srcOp = CI->getArgOperand(0);
				assert(srcOp->getType() == newTy);
				newI = srcOp;
			} else if (IsCastFromHFloatTmp(CI)) {
				auto *srcOp = CI->getArgOperand(0);
				assert(CI->getType() == newTy);
				newI = createSpecializedValue(Builder, newFpTyCfg, *srcOp,
						newInstructionType, newInstructions);
			} else {
				errs() << I << "\n";
				llvm_unreachable("Unsupported value for HFloatTmpLoweringPass");
			}
		} else {
			errs() << I << "\n";
			llvm_unreachable("Unsupported value for HFloatTmpLoweringPass");
		}
		newInstructions[&I] = newI;
		if (auto _newI = dyn_cast<Instruction>(newI)) {
			_newI->copyMetadata(I);
		}
		if (!I.getType()->isDoubleTy()) {
			assert(newI->getType() == newI->getType());
			I.replaceAllUsesWith(newI);
		}

		return newI;
	}
}

llvm::PreservedAnalyses HFloatTmpLoweringPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	bool Changed = false;

	// find all values which are working with HFloatTmp (which is currently represented as double)
	// HFloatTmpConfig is specified for operands of instruction and result of instruction may be of a different type
	// except for CastToHFloatTmp which has specification for result
	std::unordered_map<Instruction*, HFloatTmpConfig> newInstructionType;
	std::unordered_set<Instruction*> useToDefSeen;
	for (BasicBlock &BB : F) {
		for (auto &I : BB) {
			auto CI = dyn_cast<CallInst>(&I);
			if (!CI)
				continue;
			// [todo] cover when only floating point primary inputs to expression are constants (which do not use CastToHFloatTmp)
			//        and any output does not use CastFromHFloatTmp (e.g. expression tree ending with FCmp)
			if (IsCastToHFloatTmp(CI)) {
				auto fpCfg = HFloatTmpConfig::fromCallArgs(*CI);
				propagateTypeDefToUse(fpCfg, *CI, newInstructionType);
			} else if (IsCastFromHFloatTmp(CI)) {
				auto fpCfg = HFloatTmpConfig::fromCallArgs(*CI);
				propagateTypeUseToDef(fpCfg, *CI, newInstructionType,
						useToDefSeen);
			}
		}
	}
	if (newInstructionType.size()) {
		Changed = true;
		// construct new instructions which are working only in specialized floating point type
		std::unordered_map<Instruction*, Value*> newInstructions;
		IRBuilder<> Builder(F.getContext());
		for (BasicBlock &BB : F) {
			for (auto &I : BB) {
				auto newTy = newInstructionType.find(&I);
				if (newTy != newInstructionType.end()) {
					createSpecializedInstruction(Builder, I, newInstructionType,
							newInstructions);

				}
			}
		}
		// erase replaced instruction working with HFloatTmp
		for (BasicBlock &BB : F) {
			for (auto &I : make_early_inc_range(BB)) {
				if (newInstructionType.find(&I) != newInstructionType.end()) {
					I.eraseFromParent();
				}
			}
		}
	}

	if (Changed) {
		PreservedAnalyses PA;
		return PA;
	} else {
		return PreservedAnalyses::all();
	}

}

}

