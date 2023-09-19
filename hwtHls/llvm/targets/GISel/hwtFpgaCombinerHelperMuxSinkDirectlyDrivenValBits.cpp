#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>
#include <hwtHls/llvm/bitMath.h>

namespace llvm {

//bool HwtFpgaCombinerHelper::matchMuxSinkDirectlyCondDrivenValBits(llvm::MachineInstr &MI,
//		hwtHls::MuxDirectlyCondDrivenBits &matchInfo) {
//	if (MI.getNumOperands() < 1 + 3 || (MI.getNumOperands() - 1 % 2) != 1) {
//		// has no condition or is latching
//		return false;
//	}
//	size_t width = hwtHls::hwtFpgaMuxFindValueWidth(MI, MRI);
//	if (width == 0)
//		return false; // can not resolve width, can not probe possible MERGE_VALUES, must exit
//	matchInfo = hwtHls::MuxDirectlyCondDrivenBits(width, (MI.getNumOperands() / 2) - 1);
//	auto CondOpIt = MI.operands_begin() + 2;
//	while (CondOpIt != MI.operands_end()) {
//		auto ValOpIt = MI.operands_begin() + 1; // skip dst
//		bool valIsOnTSide = true;
//		while (ValOpIt != MI.operands_end()) {
//			const auto &V = *ValOpIt;
//			if (!matchInfo.loadKnonwBitsFromValueOperand(*CondOpIt, valIsOnTSide, V, 0, width, MRI, 1))
//				break; // all value bits known to be defined differently, no point in search for other operands
//
//			++ValOpIt; // move to condition
//			if (ValOpIt == CondOpIt)
//				valIsOnTSide = false;
//			++ValOpIt; // move to next value
//		}
//		CondOpIt += 2;
//	}
//	return matchInfo.haveSomethingToReduce();
//}
//
//bool HwtFpgaCombinerHelper::rewriteMuxSinkDirectlyCondDrivenValBits(llvm::MachineInstr &MI,
//			hwtHls::MuxDirectlyCondDrivenBits &matchInfo) {
//	llvm_unreachable("NotImplemented");
//}

}
