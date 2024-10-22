#include <hwtHls/llvm/Transforms/utils/irConsistencyChecks.h>

using namespace llvm;

namespace hwtHls {

void verifyUsesList(const llvm::Function &F) {
	for (auto &BB : F) {
		for (auto &I : BB) {
			for (auto &Op : I.operands()) {
				auto OpV = Op.get();
				if (!isa<GlobalValue>(OpV)){
					if (auto OpVasI = dyn_cast<Instruction>(OpV)) {
						assert(OpVasI->getParent() && "Check that the the operand is not erased");
						assert(OpVasI->getParent()->getParent() == &F);
					}
				}
				bool found = false;
				for (auto &U : OpV->uses()) {
					found |= U.getUser() == &I
							&& U.getOperandNo() == Op.getOperandNo();
					if (found)
						break;
				}
				assert(found);
			}
		}
	}
}
}
