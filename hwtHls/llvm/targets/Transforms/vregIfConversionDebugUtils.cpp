#include <hwtHls/llvm/targets/Transforms/vregIfConversionPriv.h>

using namespace llvm;

namespace hwtHls {

const char* VRegIfConverter::IfcvtKind_toStr(VRegIfConverter::IfcvtKind Kind) {
	switch (Kind) {
	case ICSimple:
		return ".Simple";
	case ICSimpleFalse:
		return ".SimpleFalse";
	case ICTriangle:
		return ".Triangle";
	case ICTriangleRev:
		return ".TriangleRev";
	case ICTriangleFalse:
		return ".TriangleFalse";
	case ICTriangleFRev:
		return ".TriangleFRev";
	case ICDiamond:
		return ".Diamond";
	case ICForkedDiamond:
		return ".ForkedDiamond";
	case ICLoopTail:
		return ".LoopTail";
	case ICLoopTailFalse:
		return ".LoopTailFalse";
	case ICLoopTailRev:
		return ".LoopTailRev";
	case ICLoopTailFRev:
		return ".LoopTailFRev";
	default:
		llvm_unreachable("Unexpected IfcvtKind value!");
	}
}

void VRegIfConverter::consistencyCheck(MachineBasicBlock &MBB) const {
	BBInfo BBI;
	BBI.BB = &MBB;
	BBI.IsBrAnalyzable = !TII->analyzeBranch(*BBI.BB, BBI.TrueBB, BBI.FalseBB,
			BBI.BrCond);
	auto &MF = *MBB.getParent();
	if (BBI.IsBrAnalyzable) {
		if (BBI.TrueBB) {
			bool isPred = BBI.TrueBB->isPredecessor(BBI.BB);
			if (!isPred) {
				if (enableTrace)
					hwtHls::writeCFGToDotFile(MF,
							std::string("IC.") + std::to_string(dbgCntr)
									+ ".error.dot");
				llvm_unreachable("Successor/predecessor list inconsistent");
			}
		}
		if (BBI.FalseBB) {
			bool isPred = BBI.FalseBB->isPredecessor(BBI.BB);
			if (!isPred) {
				if (enableTrace)
					hwtHls::writeCFGToDotFile(MF,
							std::string("IC.") + std::to_string(dbgCntr)
									+ ".error.dot");
				llvm_unreachable("Successor/predecessor list inconsistent");
			}
		}
	}
}

}
