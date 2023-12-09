#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlicesBinOp.h>

#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Verifier.h>

#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;

namespace hwtHls {

bool mergeConsequentSlicesBinOp(BinaryOperator &I, const CreateBitRangeGetFn &createSlice,
		DceWorklist &dce) {
	bool modified;
	Value *widerOp0;
	Value *widerOp1;
	IRBuilder<> builder(&I);
	ParallelInstVec parallelInstrOnSameVec;
	const auto noPredicate = [](Instruction &I) {
		return true;
	};
	std::tie(modified, widerOp0, widerOp1) =
			mergeConsequentSlicesExtractWiderOperads(createSlice, dce,
					builder, parallelInstrOnSameVec, I, noPredicate, true, 0,
					1);
	if (widerOp0 && widerOp1) {
		Value *res = nullptr;
		switch (I.getOpcode()) {
		case Instruction::BinaryOps::And:
			res = builder.CreateAnd(widerOp0, widerOp1);
			break;
		case Instruction::BinaryOps::Or:
			res = builder.CreateOr(widerOp0, widerOp1);
			break;
		case Instruction::BinaryOps::Xor:
			res = builder.CreateXor(widerOp0, widerOp1);
			break;
		default:
			errs() << I << "\n";
			llvm_unreachable("Not implemented binary operator");
		}
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		auto &F = *I.getParent()->getParent();
		auto &M = *F.getParent();
		if (verifyModule(M)) {
			F.dump();
			I.dump();
			res->dump();
			throw std::runtime_error("getInstructionClosesToBlockEnd broken");
		}
#endif
		assert(parallelInstrOnSameVec.size() && parallelInstrOnSameVec[0].I == &I);
		replaceMergedInstructions(parallelInstrOnSameVec, createSlice, builder,
				res, dce);

	}
	return modified;
}

}
