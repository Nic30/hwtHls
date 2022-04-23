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
#include <llvm/CodeGen/TargetLowering.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/CodeGen/TargetRegisterInfo.h>

#include "genericFpgaCallLoweringInfo.h"
#include "genericFpgaTargetLowering.h"
#include "genericFpgaTargetFrameLowering.h"
#include "genericFpgaRegisterInfo.h"

#define GET_SUBTARGETINFO_HEADER
#include "GenericFpgaGenSubtargetInfo.inc"

namespace llvm {

class GlobalValue;
class StringRef;
class TargetMachine;

class GenericFpgaTargetMachine;

// must be in llvm namespace because of tblgen generated code
class GenericFpgaTargetSubtarget: public llvm::GenericFpgaTargetGenSubtargetInfo {
	friend GenericFpgaTargetMachine;
	std::vector<llvm::SubtargetFeatureKV> _PF;
	static std::vector<llvm::SubtargetSubTypeKV> _PD;
	static std::vector<llvm::MCWriteProcResEntry> _WPR;
	static std::vector<llvm::MCWriteLatencyEntry> _WL;
	static std::vector<llvm::MCReadAdvanceEntry> _RA;

protected:
	//llvm::TargetTransformInfo TTI;
	std::unique_ptr<llvm::GenericFpgaTargetLowering> TLI;
	llvm::GenericFpgaRegisterInfo TRI;
	std::unique_ptr<llvm::GenericFpgaTargetFrameLowering> TargetFrameLoweringInfo;

	std::unique_ptr<llvm::SelectionDAGTargetInfo> SelectionDAGTargetInfoInfo;
	// GlobalISel related APIs.
	std::unique_ptr<llvm::GenericFpgaCallLowering> CallLoweringInfo;
	//std::unique_ptr<llvm::InstructionSelector> InstSelector;
	std::unique_ptr<llvm::LegalizerInfo> Legalizer;
	std::unique_ptr<llvm::RegisterBankInfo> RegBankInfo;

public:
	GenericFpgaTargetSubtarget(const llvm::Triple &TT, llvm::StringRef CPU,
			llvm::StringRef TuneCPU, llvm::StringRef FS,
			llvm::StringRef ABIName, const llvm::TargetMachine &TM);

	/// Parses a subtarget feature string, setting appropriate options.
	/// \note Definition of function is auto generated by `tblgen`.
	void ParseSubtargetFeatures(StringRef CPU, StringRef TuneCPU, StringRef FS);

	/// getRegisterInfo - If register information is available, return it.  If
	/// not, return null.
	const llvm::TargetRegisterInfo* getRegisterInfo() const override;
	const llvm::TargetLowering* getTargetLowering() const override;
	const llvm::SelectionDAGTargetInfo* getSelectionDAGInfo() const override;
	const llvm::TargetInstrInfo* getInstrInfo() const override;
	const llvm::CallLowering* getCallLowering() const override {
		return CallLoweringInfo.get();
	}
	//llvm::InstructionSelector* getInstructionSelector() const override {
	//	return InstSelector.get();
	//}
	const llvm::LegalizerInfo* getLegalizerInfo() const override {
		return Legalizer.get();
	}
	const llvm::TargetFrameLowering* getFrameLowering() const override {
		return TargetFrameLoweringInfo.get();
	}
	const llvm::RegisterBankInfo* getRegBankInfo() const override {
		return RegBankInfo.get();
	}
	virtual bool enableMachineScheduler() const override {
		return false;
	}
	virtual bool enableMachineSchedDefaultSched() const {
		return false;
	}
	virtual bool enableMachinePipeliner() const {
		return false;
	}
};

}

