#include <hwtHls/llvm/Transforms/slicesMerge/slicesMergeCombiner.h>

#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Verifier.h>

#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;

namespace hwtHls {

llvm::Instruction* SlicesMergeCombiner::mergeConsequentSlicesBinOp(BinaryOperator &I) {
	bool modified;
	Value *widerOp0;
	Value *widerOp1;
	Builder.SetInsertPoint(&I);
	ParallelInstVec parallelInstrOnSameVec;
	const auto noPredicate = [](Instruction &I) {
		return true;
	};
	std::tie(modified, widerOp0, widerOp1) =
			mergeConsequentSlicesExtractWiderOperads(parallelInstrOnSameVec, I, noPredicate, true, 0,
					1);
	if (widerOp0 && widerOp1) {
		Value *res;
		switch (I.getOpcode()) {
		case Instruction::BinaryOps::And:
			res = Builder.CreateAnd(widerOp0, widerOp1);
			break;
		case Instruction::BinaryOps::Or:
			res = Builder.CreateOr(widerOp0, widerOp1);
			break;
		case Instruction::BinaryOps::Xor:
			res = Builder.CreateXor(widerOp0, widerOp1);
			break;
		default:
			errs() << I << "\n";
			llvm_unreachable("Not implemented binary operator");
		}
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		verifyAfterUpdate("getInstructionClosesToBlockEnd broken", &I);
#endif
		assert(parallelInstrOnSameVec.size() && parallelInstrOnSameVec[0].I == &I);
		//if (auto resI = dyn_cast<Instruction>(res)) {
		//	Builder.SetInsertPoint(resI->getNextNode());
		//}
		replaceMergedInstructions(parallelInstrOnSameVec,
				res);
		return &I; // return I to mark that it was replaced

	}
	return nullptr;
}

}
