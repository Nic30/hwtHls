#include <hwtHls/llvm/targets/Transforms/vregIfConversionPriv.h>

using namespace llvm;

namespace hwtHls {

bool VRegIfConverter::ValidForkedTriangle(BBInfo &BBI, BBInfo &SuccBBI,
		BBInfo &OtherSuccBBI, bool FalseBranch, unsigned &Dups,
		bool &OtherSuccIsTrueSucOfSucc,
		llvm::BranchProbability Prediction) const {
	Dups = 0;
	if (BBI.BB->succ_size() != 2)
		return false; // can not be triangle if there are no two paths from a header block
	if (SuccBBI.IsBeingAnalyzed || SuccBBI.IsDone)
		return false;
	if (SuccBBI.BB->pred_size() != 1) {
		// this could interfere with cycles the SuccBBI can be a part of cycle
		// it must have a single predecessors
		return false;
	}
	if (!SuccBBI.IsBrAnalyzable)
		return false; // can not be forked if we can not analyze br

	if (SuccBBI.BB->succ_size() != 2)
		return false; // can not be forked if there are no 2 successors

	// check if some successor of successor is enclosing triangle with BB as head and OtherSucc as tail
	if (SuccBBI.TrueBB == OtherSuccBBI.BB) {
		OtherSuccIsTrueSucOfSucc = true;
		return true;
	} else if (SuccBBI.HasFallThrough) {
		if (canFallThroughTo(*SuccBBI.BB, *OtherSuccBBI.BB)) {
			OtherSuccIsTrueSucOfSucc = false;
			return true;
		}
	} else if (SuccBBI.FalseBB == OtherSuccBBI.BB) {
		OtherSuccIsTrueSucOfSucc = false;
		return true;
	}
	return false;
}

}
