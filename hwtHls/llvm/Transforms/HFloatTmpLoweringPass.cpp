#include <hwtHls/llvm/Transforms/HFloatTmpLoweringPass.h>

#include <unordered_map>
#include <unordered_set>

#include <llvm/IR/Instructions.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Constants.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>

using namespace llvm;

namespace hwtHls {

// :note: newInstructionType is used also as a defToUse seen set

void propagateTypeUseToDef(const HFloatTmpConfig &fpCfg, Instruction &I,
		std::unordered_map<Instruction*, HFloatTmpConfig> &newInstructionType,
		std::unordered_set<Instruction*> &useToDefSeen);

void propagateTypeDefToUse(const HFloatTmpConfig &fpCfg, Instruction &I,
		std::unordered_map<Instruction*, HFloatTmpConfig> &newInstructionType,
		std::unordered_set<Instruction*> &useToDefSeen) {
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
		if (auto UserInstr = dyn_cast<Instruction>(_UI)) {
			if (!UserInstr->getType()->isDoubleTy()) {
				newInstructionType[UserInstr] = fpCfg;
				continue;
			}
			propagateTypeDefToUse(fpCfg, *UserInstr, newInstructionType,
					useToDefSeen);
			propagateTypeUseToDef(fpCfg, *UserInstr, newInstructionType,
					useToDefSeen);
		}
	}
}

void propagateTypeUseToDef(const HFloatTmpConfig &fpCfg, Instruction &I,
		std::unordered_map<Instruction*, HFloatTmpConfig> &newInstructionType,
		std::unordered_set<Instruction*> &useToDefSeen) {
	// :note: seen is required because DefToUse search can
	// propagate type use->def until CastToHFloatTmp is found
	auto curUserFpCfg = newInstructionType.find(&I);
	if (curUserFpCfg != newInstructionType.end()) {
		assert(
				curUserFpCfg->second == fpCfg
						&& "All paths in code must resolve to the same type");
		if (useToDefSeen.contains(&I))
			return;
	} else {
		newInstructionType[&I] = fpCfg;
	}
	useToDefSeen.insert(&I);
	for (auto &O : I.operands()) {
		if (!O.get()->getType()->isDoubleTy())
			continue;

		if (auto UsedInstr = dyn_cast<Instruction>(O.get())) {
			if (auto CI = dyn_cast<CallInst>(UsedInstr)) {
				if (IsCastToHFloatTmp(CI))
					continue;
			}

			propagateTypeDefToUse(fpCfg, *UsedInstr, newInstructionType,
					useToDefSeen);
			propagateTypeUseToDef(fpCfg, *UsedInstr, newInstructionType,
					useToDefSeen);
		}
	}
}

ConstantInt* bitCastConstantFPToHFloatTmp(const HFloatTmpConfig &fpCfg,
		const ConstantFP &CF) {
	auto v = CF.getValue();
	auto res = fpCfg.bitCastAPFloatToHFloatTmpAPInt(v);
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
		return bitCastConstantFPToHFloatTmp(fpCfg, *CF);
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
		if (auto binOp = dyn_cast<BinaryOperator>(&I)) {
			auto *opConstructor = &CreateHwtHlsFpFAdd;
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
			assert(op0->getType() == op1->getType());
			Builder.SetInsertPoint(&I);
			newI = (*opConstructor)(&Builder, op0, op1,
					__HFloatTmpConfig_opts(newFpTyCfg), I.getName());

		} else if (auto UnI = dyn_cast<UnaryInstruction>(&I)) {
			auto *opConstructor = &CreateHwtHlsFpFNeg;
			switch (UnI->getOpcode()) {
			case UnaryInstruction::UnaryOps::FNeg:
				opConstructor = &CreateHwtHlsFpFNeg;
				break;
			default:
				errs() << I << "\n";
				llvm_unreachable("Unsupported value for HFloatTmpLoweringPass");
			}
			auto op0 = UnI->getOperand(0);
			op0 = createSpecializedValue(Builder, newFpTyCfg, *op0,
					newInstructionType, newInstructions);
			Builder.SetInsertPoint(&I);
			newI = (*opConstructor)(&Builder, op0,
					__HFloatTmpConfig_opts(newFpTyCfg), I.getName());

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
			assert(opT->getType() == opF->getType());
			Builder.SetInsertPoint(&I);
			newI = Builder.CreateSelect(opC, opT, opF, I.getName());
		} else if (auto CI = dyn_cast<CallInst>(&I)) {
			if (IsCastToHFloatTmp(CI)) {
				auto *srcOp = CI->getArgOperand(0);
				assert(srcOp->getType() == newTy);
				newI = srcOp;
			} else if (IsCastFromHFloatTmp(CI)) {
				auto *srcOp = CI->getArgOperand(0);
				assert(CI->getType() == newTy);
				Builder.SetInsertPoint(&I);
				newI = createSpecializedValue(Builder, newFpTyCfg, *srcOp,
						newInstructionType, newInstructions);
			} else {
				errs() << I << "\n";
				llvm_unreachable("Unsupported value for HFloatTmpLoweringPass");
			}
		} else if (auto CMP = dyn_cast<FCmpInst>(&I)) {
			auto op0 = CMP->getOperand(0);
			op0 = createSpecializedValue(Builder, newFpTyCfg, *op0,
					newInstructionType, newInstructions);
			auto op1 = CMP->getOperand(1);
			op1 = createSpecializedValue(Builder, newFpTyCfg, *op1,
					newInstructionType, newInstructions);
			assert(op0->getType() == op1->getType());
			Builder.SetInsertPoint(&I);
			newI = CreateHwtHlsFpFCmp(&Builder, CMP->getPredicate(), op0, op1,
					__HFloatTmpConfig_opts(newFpTyCfg), I.getName());
		} else {
			errs() << I << "\n";
			llvm_unreachable(
					"Unsupported Instruction for HFloatTmpLoweringPass");
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
				propagateTypeDefToUse(fpCfg, *CI, newInstructionType,
						useToDefSeen);
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
					I.replaceAllUsesWith(PoisonValue::get(I.getType()));
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

