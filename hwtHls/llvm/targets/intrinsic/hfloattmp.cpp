#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>
#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <llvm/ADT/StringExtras.h>

using namespace llvm;

namespace hwtHls {

bool HFloatTmpConfig::operator==(const HFloatTmpConfig &other) const {
	return std::memcmp(this, &other, sizeof *this) == 0;
}
size_t HFloatTmpConfig::__hash__() const {
	llvm::SmallVector<unsigned, 9> Bits;
	Bits.push_back(exponentOrIntWidth);
	Bits.push_back(mantissaOrFracWidth);
	Bits.push_back(isInQFromat);
	Bits.push_back(supportSubnormal);
	Bits.push_back(hasSign);
	Bits.push_back(hasIsNaN);
	Bits.push_back(hasIsInf);
	Bits.push_back(hasIs1);
	Bits.push_back(hasIs0);

	return llvm::hash_combine_range(Bits.begin(), Bits.end());

}
static uint64_t extractConstIntFromArg(User::op_iterator &A,
		User::op_iterator AEnd) {
	assert(A != AEnd);
	auto c = dyn_cast<ConstantInt>(A->get());
	A++;
	assert(
			c
					&& "Arguments specifying HFloatTmpConfig members should be only constant integers");
	return c->getZExtValue();
}

HFloatTmpConfig HFloatTmpConfig::fromCallArgs(llvm::CallInst &CI,
		size_t argsToSkip) {
	HFloatTmpConfig res;
	auto A = CI.arg_begin();
	auto AEnd = CI.arg_end();
	for (size_t i = 0; i < argsToSkip; i++) {
		assert(A != AEnd);
		A++;
	}
	res.exponentOrIntWidth = extractConstIntFromArg(A, AEnd);
	res.mantissaOrFracWidth = extractConstIntFromArg(A, AEnd);
	res.isInQFromat = extractConstIntFromArg(A, AEnd);
	res.supportSubnormal = extractConstIntFromArg(A, AEnd);
	res.hasSign = extractConstIntFromArg(A, AEnd);
	res.hasIsNaN = extractConstIntFromArg(A, AEnd);
	res.hasIsInf = extractConstIntFromArg(A, AEnd);
	res.hasIs1 = extractConstIntFromArg(A, AEnd);
	res.hasIs0 = extractConstIntFromArg(A, AEnd);
	return res;
}

#define HFloatTmpConfig_PARAMS \
		std::uint8_t exponentOrIntWidth, std::uint8_t mantissaOrFracWidth, \
		bool isInQFromat, bool supportSubnormal, \
		bool hasSign, bool hasIsNaN, bool hasIsInf, \
		bool hasIs1, bool hasIs0
#define HFloatTmpConfig_ARGS \
	exponentOrIntWidth, mantissaOrFracWidth, \
	isInQFromat, supportSubnormal,           \
	hasSign, hasIsNaN,                       \
	hasIsInf, hasIs1, hasIs0
#define HFloatTmpConfig_FROM_LOCALS \
		(HFloatTmpConfig ) { HFloatTmpConfig_ARGS }

#define HFloatTmpConfig_ARGS_TO_LLVM(Builder) \
	Builder->getInt8(exponentOrIntWidth),     \
	Builder->getInt8(mantissaOrFracWidth),    \
	Builder->getInt1(isInQFromat),            \
	Builder->getInt1(supportSubnormal),       \
	Builder->getInt1(hasSign),                \
	Builder->getInt1(hasIsNaN),               \
	Builder->getInt1(hasIsInf),               \
	Builder->getInt1(hasIs1),                 \
	Builder->getInt1(hasIs0)

const std::string CastToHFloatTmpName = "hwtHls.castToHFloatTmp";

#define HFloatTmpConfig_UN_OP_ARG_TYPES(Ops)\
	Ops[0]->getType(), Ops[1]->getType(),\
	Ops[2]->getType(), Ops[3]->getType(),\
	Ops[4]->getType(), Ops[5]->getType(),\
	Ops[6]->getType(), Ops[7]->getType(),\
	Ops[8]->getType(), Ops[9]->getType()

#define HFloatTmpConfig_BIN_OP_ARG_TYPES(Ops) \
	HFloatTmpConfig_UN_OP_ARG_TYPES(Ops), Ops[10]->getType()

llvm::CallInst* CreateCastToHFloatTmp(llvm::IRBuilder<> *Builder,
		llvm::Value *srcArg, HFloatTmpConfig_PARAMS, const llvm::Twine &Name) {
	assert(srcArg->getType()->isIntegerTy());
	if (isInQFromat)
		assert(
				!supportSubnormal
						&& "supportSubnormal is only relevant for floating point representation (not Q fixed point)");
	HFloatTmpConfig tyCfg = HFloatTmpConfig_FROM_LOCALS;
	assert(srcArg->getType()->getIntegerBitWidth() == tyCfg.getBitWidth());

	Value *Ops[] = { srcArg, HFloatTmpConfig_ARGS_TO_LLVM(Builder) };
	Type *ResT = Builder->getDoubleTy();
	Type *TysForName[] = { Ops[0]->getType() };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(CastToHFloatTmpName, TysForName), ResT,
					HFloatTmpConfig_UN_OP_ARG_TYPES(Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;

}
bool IsCastToHFloatTmp(const llvm::CallInst *C) {
	return IsCastToHFloatTmp(C->getCalledFunction());
}
bool IsCastToHFloatTmp(const llvm::Function *F) {
	return F->getName().str().rfind(CastToHFloatTmpName + ".", 0) == 0;
}

const std::string CastFromHFloatTmpName = "hwtHls.castFromHFloatTmp";

llvm::CallInst* CreateCastFromHFloatTmp(llvm::IRBuilder<> *Builder,
		llvm::Value *srcArg, HFloatTmpConfig_PARAMS, const llvm::Twine &Name) {
	if (isInQFromat)
		assert(
				!supportSubnormal
						&& "supportSubnormal is only relevant for floating point representation (not Q fixed point)");
	HFloatTmpConfig tyCfg = HFloatTmpConfig_FROM_LOCALS;

	assert(srcArg->getType()->isDoubleTy());

	Value *Ops[] = { srcArg, HFloatTmpConfig_ARGS_TO_LLVM(Builder) };
	Type *ResT = Builder->getIntNTy(tyCfg.getBitWidth());
	Type *TysForName[] = { ResT };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(CastFromHFloatTmpName, TysForName), ResT,
					HFloatTmpConfig_UN_OP_ARG_TYPES(Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}
bool IsCastFromHFloatTmp(const llvm::CallInst *C) {
	return IsCastFromHFloatTmp(C->getCalledFunction());
}
bool IsCastFromHFloatTmp(const llvm::Function *F) {
	return F->getName().str().rfind(CastFromHFloatTmpName + ".", 0) == 0;
}

bool IsHwtHlsFp(const llvm::CallInst *C) {
	return IsHwtHlsFp(C->getCalledFunction());
}
bool IsHwtHlsFp(const llvm::Function *F) {
	return F->getName().str().rfind("hwtHls.fp.", 0) == 0;
}


llvm::CallInst* CreateHwtHlsFBinOp(llvm::IRBuilder<> *Builder,
		const std::string &intrinsicFnName, llvm::Value *op0, llvm::Value *op1,
		HFloatTmpConfig_PARAMS, const llvm::Twine &Name) {
	if (isInQFromat)
		assert(
				!supportSubnormal
						&& "supportSubnormal is only relevant for floating point representation (not Q fixed point)");
	HFloatTmpConfig tyCfg = HFloatTmpConfig_FROM_LOCALS;
	assert(op0->getType()->isIntegerTy());
	assert(op0->getType() == op1->getType());

	Value *Ops[] = { op0, op1, HFloatTmpConfig_ARGS_TO_LLVM(Builder) };
	Type *ResT = Builder->getIntNTy(tyCfg.getBitWidth());
	Type *TysForName[] = { ResT };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn =
			cast<Function>(
					M->getOrInsertFunction(
							Intrinsic_getName(intrinsicFnName, TysForName),
							ResT, HFloatTmpConfig_BIN_OP_ARG_TYPES(Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}

#define CONCAT_(prefix, suffix) prefix##suffix
/// Concatenate `prefix, suffix` into `prefixsuffix`
#define CONCAT(prefix, suffix) CONCAT_(prefix, suffix)
#define DEFINE_FP_BINOP(name, intrinsicName)                                           \
const std::string CONCAT(CONCAT(hwtHlsFp, name), Name) = "hwtHls.fp." #intrinsicName;  \
llvm::CallInst* CreateHwtHlsFp##name(llvm::IRBuilder<> *Builder, llvm::Value *op0,     \
		llvm::Value *op1, HFloatTmpConfig_PARAMS, const llvm::Twine &Name) {           \
	return CreateHwtHlsFBinOp(Builder, CONCAT(CONCAT(hwtHlsFp, name), Name), op0, op1, \
			HFloatTmpConfig_ARGS, Name);                                               \
}                                                                                      \
bool IsHwtHlsFp##name(const llvm::CallInst *C) {                                       \
	return IsHwtHlsFpFAdd(C->getCalledFunction());                                     \
}                                                                                      \
bool IsHwtHlsFp##name(const llvm::Function *F) {                                       \
	return F->getName().str().rfind(hwtHlsFpFAddName + ".", 0) == 0;               \
}

DEFINE_FP_BINOP(FAdd, fadd)
DEFINE_FP_BINOP(FSub, fsub)
DEFINE_FP_BINOP(FMul, fmul)
DEFINE_FP_BINOP(FDiv, fdiv)
DEFINE_FP_BINOP(FRem, frem)

}
