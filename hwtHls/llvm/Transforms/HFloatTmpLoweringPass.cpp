#include <hwtHls/llvm/Transforms/HFloatTmpLoweringPass.h>

#include <unordered_map>
#include <unordered_set>

#include <llvm/IR/Instructions.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Constants.h>
#include <llvm/Analysis/TargetLibraryInfo.h>

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
		if (curUserFpCfg->second != fpCfg) {
			std::string errStr =
					"HFloatTmpLoweringPass: All paths in HFloatTmp code island must resolve to the same type (propagateTypeDefToUse): ";
			llvm::raw_string_ostream ss(errStr);
			I.print(ss);
			ss << ",   cur:" << curUserFpCfg->second << ", new: " << fpCfg;
			throw std::runtime_error(ss.str());
		}
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
		if (curUserFpCfg->second != fpCfg) {
			std::string errStr =
					"HFloatTmpLoweringPass: All paths in HFloatTmp code island must resolve to the same type (propagateTypeUseToDef): ";
			llvm::raw_string_ostream ss(errStr);
			I.print(ss);
			ss << ",   cur:" << curUserFpCfg->second << ", new: " << fpCfg;
			throw std::runtime_error(ss.str());
		}
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

class HFloatTmplRewriter {
public:
	IRBuilder<> &Builder;
	const TargetLibraryInfo &TLI;
	std::unordered_map<Instruction*, HFloatTmpConfig> &newInstructionType;
	std::unordered_map<Value*, Value*> newInstructions;
	HFloatTmplRewriter(IRBuilder<> &Builder, const TargetLibraryInfo &TLI,
			std::unordered_map<Instruction*, HFloatTmpConfig> &newInstructionType) :
			Builder(Builder), TLI(TLI), newInstructionType(newInstructionType) {
	}
	Value* createSpecializedInstruction(Instruction &I);
	template<typename T>
	void extractAndSpecializeConstantArray(const HFloatTmpConfig &fpCfg, T &CA,
			std::vector<Constant*> &romData) {
		size_t elmCnt = CA.getType()->getNumElements();
		romData.reserve(elmCnt);
		for (size_t i = 0; i < elmCnt; ++i) {
			auto *item = CA.getAggregateElement(i);
			auto _item = createSpecializedValue(fpCfg, *item);
			item = static_cast<Constant*>(_item);
			romData.push_back(item);
		}
	}
	Value* createSpecializedValue(const HFloatTmpConfig &fpCfg, Value &V);
	Value* applyFunctionSpecialization(CallInst &I,
			const HFloatTmpConfig &newFpTyCfg,
			CallInst* (*unOpConstructor)(IRBuilderBase&, Value*,
					const HFloatTmpConfig&, const Twine&),
			CallInst* (*binopConstructor)(IRBuilderBase&, Value*, Value*,
					const HFloatTmpConfig&, const Twine&));
};

Value* HFloatTmplRewriter::createSpecializedValue(const HFloatTmpConfig &fpCfg,
		Value &V) {
	auto T = V.getType();
	if (!T->isDoubleTy()) {
		if (T->isPointerTy()) {
			auto newV = newInstructions.find(&V);
			if (newV != newInstructions.end()) {
				return newV->second;
			}
			if (auto I = dyn_cast<Instruction>(&V)) {
				Builder.SetInsertPoint(I);
				auto newTy = Builder.getIntNTy(fpCfg.getBitWidth());
				if (auto GEP = dyn_cast<GetElementPtrInst>(I)) {
					auto ptr = createSpecializedValue(fpCfg,
							*GEP->getPointerOperand());
					SmallVector<Value*, 4> IdxList;
					for (auto &ind : GEP->indices()) {
						IdxList.push_back(ind.get());
					}
					auto origArrTy = dyn_cast<ArrayType>(
							GEP->getSourceElementType());
					if (!origArrTy) {
						llvm_unreachable("NotImplemented gep on non array");
					}

					auto newArrTy = ArrayType::get(newTy,
							origArrTy->getNumElements());
					auto newI = Builder.CreateGEP(newArrTy, ptr, IdxList, "", /*IsInBounds*/
					GEP->isInBounds());
					newInstructions[I] = newI;
					if (auto _newI = dyn_cast<Instruction>(newI)) {
						_newI->copyMetadata(*I);
					}
					return newI;
				} else {
					errs() << V << "\n";
					llvm_unreachable(
							"Unsupported value (pointer instruction) for HFloatTmpLoweringPass");
				}
			} else if (auto GV = dyn_cast<GlobalValue>(&V)) {
				std::vector<Constant*> romData;

				if (ConstantArray *CA = dyn_cast<ConstantArray>(
						GV->getOperand(0))) {
					extractAndSpecializeConstantArray(fpCfg, *CA, romData);
				} else if (ConstantDataArray *CA = dyn_cast<ConstantDataArray>(
						GV->getOperand(0))) {
					extractAndSpecializeConstantArray(fpCfg, *CA, romData);
				} else {
					errs() << *GV->getOperand(0) << "\n";
					llvm_unreachable(
							"Unsupported value (GlobalValue not a ConstantArray) for HFloatTmpLoweringPass");
				}
				auto *ArrayTy = ArrayType::get(romData[0]->getType(),
						romData.size());
				auto *newCRom = ConstantArray::get(ArrayTy, romData);
				auto *newArray = new GlobalVariable(*GV->getParent(), ArrayTy, /*isConstant=*/
				true, GV->getLinkage(), newCRom, GV->getName());
				newArray->setUnnamedAddr(GV->getUnnamedAddr());
				// Set the alignment to that of an array items. We will be only loading one
				// value out of it.
				newArray->setAlignment(Align(1));
				newInstructions[I] = newArray;
				return newArray;

			} else {
				errs() << V << "\n";
				llvm_unreachable(
						"Unsupported value (pointer) for HFloatTmpLoweringPass");

			}
		}
		return &V;
	} else if (auto I = dyn_cast<Instruction>(&V)) {
		return createSpecializedInstruction(*I);
	} else if (auto CF = dyn_cast<ConstantFP>(&V)) {
		return bitCastConstantFPToHFloatTmp(fpCfg, *CF);
	} else if (isa<PoisonValue>(&V)) {
		return PoisonValue::get(Builder.getIntNTy(fpCfg.getBitWidth()));
	} else if (isa<UndefValue>(&V)) {
		return UndefValue::get(Builder.getIntNTy(fpCfg.getBitWidth()));
	} else {
		errs() << V << "\n";
		llvm_unreachable("Unsupported value for HFloatTmpLoweringPass");
	}
}

Value* HFloatTmplRewriter::applyFunctionSpecialization(CallInst &I,
		const HFloatTmpConfig &newFpTyCfg,
		CallInst* (*unOpConstructor)(IRBuilderBase&, Value*,
				const HFloatTmpConfig&, const Twine&),
		CallInst* (*binopConstructor)(IRBuilderBase&, Value*, Value*,
				const HFloatTmpConfig&, const Twine&)) {
	assert(unOpConstructor || binopConstructor);
	auto op0 = I.getArgOperand(0);
	op0 = createSpecializedValue(newFpTyCfg, *op0);
	if (unOpConstructor) {
		return (*unOpConstructor)(Builder, op0, newFpTyCfg, I.getName());
	} else {
		auto op1 = I.getArgOperand(1);
		op1 = createSpecializedValue(newFpTyCfg, *op1);
		Builder.SetInsertPoint(&I);
		return (*binopConstructor)(Builder, op0, op1, newFpTyCfg, I.getName());
	}
}

Value* HFloatTmplRewriter::createSpecializedInstruction(Instruction &I) {
	auto newInstr = newInstructions.find(&I);
	if (newInstr != newInstructions.end()) {
		auto newI = newInstr->second;
		for (;;) {
			// try search also if replacement was replaced
			newInstr = newInstructions.find(newI);
			if (newInstr == newInstructions.end())
				break;
			newI = newInstr->second;
		}
		return newI;
	}
	auto _newFpTyCfg = newInstructionType.find(&I);
	if (_newFpTyCfg == newInstructionType.end())
		return &I; // not relevant instr
	HFloatTmpConfig newFpTyCfg = _newFpTyCfg->second;

	Builder.SetInsertPoint(&I);
	try {
		auto newTy = Builder.getIntNTy(newFpTyCfg.getBitWidth());
		if (auto phi = dyn_cast<PHINode>(&I)) {
			auto newI = Builder.CreatePHI(newTy, phi->getNumIncomingValues(),
					I.getName());
			newInstructions[&I] = newI;
			for (const auto& [BB, V] : zip(phi->blocks(),
					phi->incoming_values())) {
				auto newIncV = createSpecializedValue(newFpTyCfg, *V);
				newI->addIncoming(newIncV, BB);
			}
			return newI;
		} else {
			Value *newI = nullptr;
			if (auto binOp = dyn_cast<BinaryOperator>(&I)) {
				auto *opConstructor = &CreateHwtHlsFpFAdd;
				opConstructor = nullptr;
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
					llvm_unreachable(
							"Unsupported binary operator for HFloatTmpLoweringPass");
				}
				auto op0 = binOp->getOperand(0);
				op0 = createSpecializedValue(newFpTyCfg, *op0);
				auto op1 = binOp->getOperand(1);
				op1 = createSpecializedValue(newFpTyCfg, *op1);
				assert(op0->getType() == op1->getType());
				Builder.SetInsertPoint(&I);
				newI = (*opConstructor)(Builder, op0, op1, newFpTyCfg,
						I.getName());
			} else if (auto LdI = dyn_cast<LoadInst>(&I)) {
				auto op0 = LdI->getPointerOperand();
				op0 = createSpecializedValue(newFpTyCfg, *op0);
				auto newTy = Builder.getIntNTy(newFpTyCfg.getBitWidth());
				newI = Builder.CreateLoad(newTy, op0, LdI->isVolatile());
				LoadInst *newLdI = static_cast<LoadInst*>(newI);
				newLdI->setAlignment(LdI->getAlign());
				newLdI->setOrdering(LdI->getOrdering());
				newLdI->setSyncScopeID(LdI->getSyncScopeID());

			} else if (auto UnI = dyn_cast<UnaryInstruction>(&I)) {
				auto *opConstructor = &CreateHwtHlsFpFNeg;
				switch (UnI->getOpcode()) {
				case UnaryInstruction::UnaryOps::FNeg:
					opConstructor = &CreateHwtHlsFpFNeg;
					break;
				default:
					errs() << I << "\n";
					llvm_unreachable(
							"Unsupported unary instruction for HFloatTmpLoweringPass");
				}
				auto op0 = UnI->getOperand(0);
				op0 = createSpecializedValue(newFpTyCfg, *op0);
				Builder.SetInsertPoint(&I);
				newI = (*opConstructor)(Builder, op0, newFpTyCfg, I.getName());

			} else if (auto SI = dyn_cast<SelectInst>(&I)) {
				auto opC = SI->getCondition();
				opC = createSpecializedValue(newFpTyCfg, *opC);
				auto opT = SI->getTrueValue();
				opT = createSpecializedValue(newFpTyCfg, *opT);
				auto opF = SI->getFalseValue();
				opF = createSpecializedValue(newFpTyCfg, *opF);
				assert(opT->getType() == opF->getType());
				Builder.SetInsertPoint(&I);
				newI = Builder.CreateSelect(opC, opT, opF, I.getName());
			} else if (auto II = dyn_cast<IntrinsicInst>(&I)) {
				// :attention: IntrinsicInst is CallInst so it must be before
				auto *unOpConstructor = &CreateHwtHlsFpFNeg;
				auto *binOpConstructor = &CreateHwtHlsFpFAdd;
				unOpConstructor = nullptr; // previously initialized to be able to use "auto" to avoid writing whole type
				binOpConstructor = nullptr;
				switch (II->getIntrinsicID()) {
				case Intrinsic::ceil:
					unOpConstructor = &CreateHwtHlsFpCeil;
					break;
				case Intrinsic::acos:
					unOpConstructor = &CreateHwtHlsFpAcos;
					break;
				case Intrinsic::cos:
					unOpConstructor = &CreateHwtHlsFpCos;
					break;
				case Intrinsic::cosh:
					unOpConstructor = &CreateHwtHlsFpCosh;
					break;
				case Intrinsic::exp:
					unOpConstructor = &CreateHwtHlsFpExp;
					break;
				case Intrinsic::exp10:
					unOpConstructor = &CreateHwtHlsFpExp10;
					break;
				case Intrinsic::exp2:
					unOpConstructor = &CreateHwtHlsFpExp2;
					break;
				case Intrinsic::fabs:
					unOpConstructor = &CreateHwtHlsFpFAbs;
					break;
				case Intrinsic::floor:
					unOpConstructor = &CreateHwtHlsFpFloor;
					break;
				case Intrinsic::log:
					unOpConstructor = &CreateHwtHlsFpLog;
					break;
				case Intrinsic::log10:
					unOpConstructor = &CreateHwtHlsFpLog10;
					break;
				case Intrinsic::log2:
					unOpConstructor = &CreateHwtHlsFpLog2;
					break;
				case Intrinsic::pow:
					binOpConstructor = &CreateHwtHlsFpFPow;
					break;
				case Intrinsic::powi:
					binOpConstructor = &CreateHwtHlsFpFPowi;
					break;
				case Intrinsic::round:
					unOpConstructor = &CreateHwtHlsFpRound;
					break;
				case Intrinsic::roundeven:
					unOpConstructor = &CreateHwtHlsFpRoundeven;
					break;
				case Intrinsic::asin:
					unOpConstructor = &CreateHwtHlsFpAsin;
					break;
				case Intrinsic::sin:
					unOpConstructor = &CreateHwtHlsFpSin;
					break;
				case Intrinsic::sinh:
					unOpConstructor = &CreateHwtHlsFpSinh;
					break;
				case Intrinsic::tan:
					unOpConstructor = &CreateHwtHlsFpTan;
					break;
				case Intrinsic::atan:
					unOpConstructor = &CreateHwtHlsFpAtan;
					break;
				case Intrinsic::tanh:
					unOpConstructor = &CreateHwtHlsFpTanh;
					break;
				case Intrinsic::atan2:
					binOpConstructor = &CreateHwtHlsFpAtan2;
					break;
				case Intrinsic::sqrt:
					unOpConstructor = &CreateHwtHlsFpSqrt;
					break;
				default:
					errs() << I << "\n";
					llvm_unreachable(
							"Unsupported intrinsic for HFloatTmpLoweringPass");
				}
				newI = applyFunctionSpecialization(*II, newFpTyCfg,
						unOpConstructor, binOpConstructor);
			} else if (auto CI = dyn_cast<CallInst>(&I)) {
				LibFunc libFn;
				if (TLI.getLibFunc(*CI, libFn)) {
					auto *unOpConstructor = &CreateHwtHlsFpFNeg;
					auto *binOpConstructor = &CreateHwtHlsFpFAdd;
					unOpConstructor = nullptr; // previously initialized to be able to use "auto" to avoid writing whole type
					binOpConstructor = nullptr;
					switch (libFn) {
					case LibFunc::LibFunc_fmod:
						binOpConstructor = &CreateHwtHlsFpFMod;
						break;
					case LibFunc::LibFunc_sinpi:
						unOpConstructor = &CreateHwtHlsFpSinpi;
						break;
					case LibFunc::LibFunc_cospi:
						unOpConstructor = &CreateHwtHlsFpCospi;
						break;
					case LibFunc::LibFunc_asin:
						unOpConstructor = &CreateHwtHlsFpAsin;
						break;
					case LibFunc::LibFunc_sinh:
						unOpConstructor = &CreateHwtHlsFpSinh;
						break;
					case LibFunc::LibFunc_acos:
						unOpConstructor = &CreateHwtHlsFpAcos;
						break;
					case LibFunc::LibFunc_cosh:
						unOpConstructor = &CreateHwtHlsFpCosh;
						break;
					case LibFunc::LibFunc_tan:
						unOpConstructor = &CreateHwtHlsFpTan;
						break;
					case LibFunc::LibFunc_atan:
						unOpConstructor = &CreateHwtHlsFpAtan;
						break;
					case LibFunc::LibFunc_tanh:
						unOpConstructor = &CreateHwtHlsFpTanh;
						break;
					case LibFunc::LibFunc_atan2:
						binOpConstructor = &CreateHwtHlsFpAtan2;
						break;
					default:
						errs() << I << "\n";
						llvm_unreachable(
								"Unsupported Library function for HFloatTmpLoweringPass");
						break;
					}
					newI = applyFunctionSpecialization(*CI, newFpTyCfg,
							unOpConstructor, binOpConstructor);
				} else if (IsCastToHFloatTmp(CI)) {
					auto *srcOp = CI->getArgOperand(0);
					assert(srcOp->getType() == newTy);
					newI = srcOp;
				} else if (IsCastFromHFloatTmp(CI)) {
					auto *srcOp = CI->getArgOperand(0);
					assert(CI->getType() == newTy);
					Builder.SetInsertPoint(&I);
					newI = createSpecializedValue(newFpTyCfg, *srcOp);
					newInstructionType[&I] = newFpTyCfg; // because new
				} else {
					auto op0 = createSpecializedValue(newFpTyCfg,
							*CI->getArgOperand(0));
					Builder.SetInsertPoint(&I);
					auto *shOp = &CreateHwtHlsFpShl;
					if (IsHwtHlsFpUnspecializedShl(CI)) {
						shOp = CreateHwtHlsFpShl;
					} else if (IsHwtHlsFpUnspecializedShr(CI)) {
						shOp = CreateHwtHlsFpShr;
					} else {
						errs() << I << "\n";
						llvm_unreachable(
								"Unsupported CallInst for HFloatTmpLoweringPass");
					}
					newI = (*shOp)(Builder, op0, CI->getArgOperand(1),
							newFpTyCfg, I.getName());
				}
			} else if (auto CMP = dyn_cast<FCmpInst>(&I)) {
				auto op0 = CMP->getOperand(0);
				op0 = createSpecializedValue(newFpTyCfg, *op0);
				auto op1 = CMP->getOperand(1);
				op1 = createSpecializedValue(newFpTyCfg, *op1);
				assert(op0->getType() == op1->getType());
				Builder.SetInsertPoint(&I);
				newI = CreateHwtHlsFpFCmp(Builder, CMP->getPredicate(), op0,
						op1, newFpTyCfg, I.getName());
			} else {
				errs() << I << "\n";
				llvm_unreachable(
						"Unsupported FCmpInst for HFloatTmpLoweringPass");
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
	} catch (HFloatTmpConversionError &err) {
		std::string errStr =
				"HFloatTmpLoweringPass: Can not convert (createSpecializedInstruction) ";
		llvm::raw_string_ostream ss(errStr);
		ss << err.what() << "  " << newFpTyCfg << ": " << I;
		throw std::runtime_error(ss.str());
	}
}

llvm::PreservedAnalyses HFloatTmpLoweringPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	auto &TLI = AM.getResult<llvm::TargetLibraryAnalysis>(F);

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
		IRBuilder<> Builder(F.getContext());
		HFloatTmplRewriter rewriter(Builder, TLI, newInstructionType);
		for (BasicBlock &BB : F) {
			for (auto &I : BB) {
				auto newTy = newInstructionType.find(&I);
				if (newTy != newInstructionType.end()) {
					rewriter.createSpecializedInstruction(I);

				}
			}
		}
		// erase replaced instruction working with HFloatTmp
		for (BasicBlock &BB : F) {
			for (auto &I : make_early_inc_range(BB)) {
				if (newInstructionType.find(&I) != newInstructionType.end()) {
					for (auto *U : I.users()) {
						assert(
								newInstructionType.find(
										dyn_cast<Instruction>(U))
										!= newInstructionType.end()
										&& "There can not be any user which will not be removed ad this point");
					}
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

