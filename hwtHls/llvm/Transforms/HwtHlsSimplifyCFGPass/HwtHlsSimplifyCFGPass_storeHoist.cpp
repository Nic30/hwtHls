#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_storeHoist.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Instructions.h>

#include <hwtHls/llvm/intrinsic/metadataSideEffect.h>

using namespace llvm;

namespace hwtHls {


bool HwtHlsSimplifyCFGPass_storeHoist(llvm::BasicBlock &BB) {
	SmallVector<BasicBlock *> unreachableBBs;
	SmallVector<std::pair<BasicBlock *, StoreInst *>> toHoist;

	StoreInst *representativeSt = findInstrAtSuccessorsBegin<StoreInst>(BB, true, toHoist, &unreachableBBs);
	if (!representativeSt)
		return false; // some block does not contain compatible store
	if (toHoist.empty())
		return false; // case for blocks without suc
	assert(unreachableBBs.size() + toHoist.size() == succ_size(&BB));
	auto BBTer = BB.getTerminator()->getIterator();
	for (const auto &[suc, st] : toHoist) {
		// hoist everything before st to BB
		BB.splice(BBTer, suc, suc->begin(), st->getIterator());
	}

	auto BBBr = dyn_cast<BranchInst>(&*BBTer);
	auto BBSw = dyn_cast<SwitchInst>(&*BBTer);
	Value *srcVal = nullptr;
	for (const auto &[suc, st] : toHoist) {
		auto v = st->getValueOperand();
		if (srcVal) {
			if (BBBr) {
				assert(BBBr->isConditional() &&
					   "If this br is not conditional there can not be "
					   "multiple values");
				auto c = BBBr->getCondition();
				if (BBBr->getSuccessor(0) == suc) {
					srcVal = SelectInst::Create(c, v, srcVal, "", BBTer);
				} else {
					srcVal = SelectInst::Create(c, srcVal, v, "", BBTer);
				}

			} else if (BBSw) {
				if (BBSw->getDefaultDest() == suc) {
					assert(!srcVal &&
						   "[todo] Expect default successor to be the first");
				}
				Value *caseC = BBSw->getCondition();
				bool sucFound = false;
				for (auto case_ : BBSw->cases()) {
					if (case_.getCaseSuccessor() == suc) {
						assert(
							!srcVal &&
							"[todo] Expect default successor to be the first");
						Value *cv = case_.getCaseValue();
						auto c = new ICmpInst(
							BBTer, CmpInst::Predicate::ICMP_EQ, caseC, cv, "");
						srcVal = SelectInst::Create(c, v, srcVal, "", BBTer);
						sucFound = true;
						break;
					}
				}
				assert(sucFound);
			} else {
				llvm_unreachable("HwtHlsSimplifyCFGPassstoreHoist: "
								 "NotImplemened: Unsupported terminator");
			}
		} else {
			srcVal = v;
		}
	}
	assert(srcVal);
	auto isFirstSuc = true;
	for (const auto &[suc, st] : toHoist) {
		if (isFirstSuc) {
			st->moveBefore(BBTer);
			st->setOperand(0, srcVal);
			isFirstSuc = false;
		} else {
			st->eraseFromParent();
		}
	}
	return true;
}

}
