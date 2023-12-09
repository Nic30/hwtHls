#include <hwtHls/llvm/targets/Transforms/vregIfConversionPriv.h>

using namespace llvm;

namespace hwtHls {

#ifdef VREG_IF_CONVERTER_DUMP
size_t VRegIfConverter::dbg_cntr = 0;
#endif


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

void VRegIfConverter::consystencyCheck(MachineBasicBlock &MBB) const {
	BBInfo BBI;
	BBI.BB = &MBB;
    BBI.IsBrAnalyzable =
	      !TII->analyzeBranch(*BBI.BB, BBI.TrueBB, BBI.FalseBB, BBI.BrCond);
#ifdef VREG_IF_CONVERTER_DUMP
    auto& MF = *MBB.getParent();
#endif
    if (BBI.IsBrAnalyzable) {
		if (BBI.TrueBB) {
			bool isPred = BBI.TrueBB->isPredecessor(BBI.BB);
			if (!isPred) {
#ifdef VREG_IF_CONVERTER_DUMP
				hwtHls::writeCFGToDotFile(MF,
						std::string("IC.") + std::to_string(dbg_cntr)
								+ ".error.dot");
#endif
				llvm_unreachable("Successor/predecessor list inconsistent");
			}
		}
		if (BBI.FalseBB) {
			bool isPred = BBI.FalseBB->isPredecessor(BBI.BB);
			if (!isPred) {
#ifdef VREG_IF_CONVERTER_DUMP
				hwtHls::writeCFGToDotFile(MF,
						std::string("IC.") + std::to_string(dbg_cntr)
								+ ".error.dot");
#endif
				llvm_unreachable("Successor/predecessor list inconsistent");
			}
		}
	}
}

}
