#pragma once
#include <llvm/ADT/Triple.h>
#include <llvm/CodeGen/TargetSubtargetInfo.h>
#include <llvm/CodeGen/CallingConvLower.h>
#include <llvm/CodeGen/GlobalISel/CallLowering.h>
#include <llvm/CodeGen/GlobalISel/InstructionSelector.h>
#include <llvm/CodeGen/TargetFrameLowering.h>
#include <llvm/CodeGen/GlobalISel/LegalizerInfo.h>
#include <llvm/Support/TypeSize.h>
#include <llvm/CodeGen/GlobalISel/RegisterBankInfo.h>
#include <llvm/CodeGen/SelectionDAGTargetInfo.h>
#include <llvm/IR/DataLayout.h>
#include <llvm/Target/TargetMachine.h>
#include <string>

namespace llvm {

class GlobalValue;
class StringRef;
class TargetMachine;
class GenericFpgaTargetMachine;

class GenericFpgaSubtarget: public TargetSubtargetInfo {
	friend GenericFpgaTargetMachine;
	std::vector<SubtargetFeatureKV> _PF;
	static std::vector<SubtargetSubTypeKV> _PD;
	static std::vector<MCWriteProcResEntry> _WPR;
	static std::vector<MCWriteLatencyEntry> _WL;
	static std::vector<MCReadAdvanceEntry> _RA;

protected:

	// GlobalISel related APIs.
	std::unique_ptr<CallLowering> CallLoweringInfo;
	std::unique_ptr<InstructionSelector> InstSelector;
	std::unique_ptr<LegalizerInfo> Legalizer;
	std::unique_ptr<RegisterBankInfo> RegBankInfo;

public:
	GenericFpgaSubtarget(const Triple &TT, StringRef CPU, StringRef TuneCPU,
			StringRef FS, StringRef ABIName, const TargetMachine &TM);

	const CallLowering* getCallLowering() const override {
		return CallLoweringInfo.get();
	}
	InstructionSelector* getInstructionSelector() const override {
		return InstSelector.get();
	}
	const LegalizerInfo* getLegalizerInfo() const override {
		return Legalizer.get();
	}
	const RegisterBankInfo* getRegBankInfo() const override {
		return RegBankInfo.get();
	}
};

}
