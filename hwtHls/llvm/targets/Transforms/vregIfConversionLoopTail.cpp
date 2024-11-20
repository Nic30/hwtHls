#include <hwtHls/llvm/targets/Transforms/vregIfConversionPriv.h>

using namespace llvm;
using namespace hwtHls;

namespace hwtHls {

bool VRegIfConverter::ValidLoopTailForLoopHeader(BBInfo &LoopHeadBBI,
		BBInfo &SuccBBI, BBInfo &OtherSuccBBI, unsigned &Dups,
		bool &TailBBCondRev, llvm::BranchProbability Prediction) const {
	// Loop tail:
	//   EBB<----- (LoopHeadBB)
	//   | \___  |
	//   |     | |
	//   |     V |
	//   |    TBB(SuccBB, tail)
	//   |   / (optional)
	//   FBB (OtherSuccBB)
	auto *SuccBBIFalse = findFalseBlock(SuccBBI.BB, SuccBBI.TrueBB);
	bool isNonRev = SuccBBI.TrueBB == LoopHeadBBI.BB
			&& (SuccBBIFalse == nullptr || SuccBBIFalse == OtherSuccBBI.BB);
	bool isRev = SuccBBIFalse == LoopHeadBBI.BB;
	TailBBCondRev = isRev;
	bool HeadCondRev = false;
	auto res = (isNonRev || isRev)
			&& ValidLoopTail(SuccBBI, LoopHeadBBI, OtherSuccBBI, Dups,
					HeadCondRev, Prediction);
	if (res) {
		assert((LoopHeadBBI.TrueBB != SuccBBI.BB) == HeadCondRev);
	}
	return res;
}

bool VRegIfConverter::ValidLoopTail(BBInfo &BBI, BBInfo &SuccBBI,
		BBInfo &OtherSuccBBI, unsigned &Dups, bool &HeadCondRev,
		llvm::BranchProbability Prediction) const {
	// Loop tail:
	//   EBB<----- (SuccBB, head)
	//   | \___  |
	//   |     | |
	//   |     V |
	//   |    TBB(BB, tail)
	//   |   / (optional)
	//   FBB (OtherSuccBB)
	Dups = 0;
	if (!SuccBBI.IsBrAnalyzable)
		return false; // can not be merge tail if main loop body can not be analyzed
	auto tail = BBI.BB;
	auto head = SuccBBI.BB;
	// SuccBBI successor of BBI and also potential predecessor and head of the loop
	if (tail->pred_size() != 1 || !head->isSuccessor(tail))
		return false;

	MachineBasicBlock *SuccBBIFalse = findFalseBlock(head, SuccBBI.TrueBB);
	MachineBasicBlock *BBIFalse = findFalseBlock(tail, BBI.TrueBB);
	if (SuccBBI.TrueBB == tail) { // check for loop head jump to BB
		HeadCondRev = false;
		if (SuccBBIFalse != OtherSuccBBI.BB) // check that loop head jumps to FBB
			return false;
		// check that other successor of BB is FBB
		if (BBIFalse) {
			if (!((BBI.TrueBB == head && BBIFalse == SuccBBIFalse)
					|| (BBI.TrueBB == SuccBBIFalse && BBIFalse == head))) {
				return false;
			}
		}

	} else {
		assert(SuccBBIFalse == tail);
		HeadCondRev = true;
		if (SuccBBI.TrueBB != OtherSuccBBI.BB) // check that loop head jumps to FBB
			return false;
		// check that other successor of BB is FBB
		if (BBIFalse) {
			if (!((BBI.TrueBB == head && BBIFalse == SuccBBI.TrueBB)
					|| (BBI.TrueBB == SuccBBI.TrueBB && BBIFalse == head))) {
				return false;
			}
		}
	}

	return true;
}

bool VRegIfConverter::IfConvertLoopTail(BBInfo &BBI, IfcvtKind Kind) {
	BBInfo &TrueBBI = BBAnalysis[BBI.TrueBB->getNumber()];
	auto *_FalseBB =
			BBI.FalseBB ? BBI.FalseBB : findFalseBlock(BBI.BB, BBI.TrueBB); // (resolve fallthrough if any)
	BBInfo *ParentBBI = &TrueBBI;
	if (Kind == ICLoopTailFRev || Kind == ICLoopTailRev) {
		assert(_FalseBB);
		assert(BBI.BB->isPredecessor(_FalseBB));
		ParentBBI = &BBAnalysis[_FalseBB->getNumber()];
	}
	bool success = false;
	if (_FalseBB) {
		// if there is false this is Triangle like pattern
		IfcvtKind TriangleKind;
		// :note: for triangle the 1st T branch is ifconverted block
		// and 2nd T branch is common tail
		// while for LoopTail the true branches lead back to loop header
		// False is related to condition in parent, Rev is related to condition in BBI
		switch (Kind) {
		case ICLoopTail:
			TriangleKind = ICTriangleRev;
			break;
		case ICLoopTailFalse:
			TriangleKind = ICTriangleFRev;
			break;
		case ICLoopTailRev:
			TriangleKind = ICTriangle;
			break;
		case ICLoopTailFRev:
			TriangleKind = ICTriangleFalse;
			break;
		default:
			llvm_unreachable("Unexpected!");
		}

		success = IfConvertTriangle(*ParentBBI, TriangleKind);
	} else {
		// if there is no false this is Simple like pattern where we can not remove branch in tail (BBI)
		switch (Kind) {
		case ICLoopTail:
			success = IfConvertSimple(*ParentBBI, ICSimple);
			break;
		case ICLoopTailFalse:
			success = IfConvertSimple(*ParentBBI, ICSimpleFalse);
			break;
			// Rev variants are invalid because there is unconditional jump in BBI which can not be reversed
		default:
			llvm_unreachable("Unexpected!");
		}
	}
#ifdef VREG_IF_CONVERTER_CONSYSTENCY_CHECKS
	consistencyCheck(*BBI.BB);
#endif
	return success;
}

}
