#pragma once

// LegalizerInfo inherited class must be compiled with same
// NDEBUG options otherwise the thing will end up segfaulting
// on check of the members which are initialized and used only in debug build
#ifdef LLVM_NDEBUG
#define NDEBUG 1
#define LLVM_MUST_UNDEF_NDEBUG 1
#endif

#include <llvm/CodeGen/GlobalISel/LegalizerInfo.h>
#include <llvm/CodeGen/GlobalISel/GenericMachineInstrs.h>
namespace llvm {

class GenericFpgaTargetSubtarget;

/// This class provides the information for the target register banks.
/// :note: same as `RISCVLegalizerInfo`
class GenericFpgaLegalizerInfo: public LegalizerInfo {
public:
	GenericFpgaLegalizerInfo(const GenericFpgaTargetSubtarget &ST);
	bool customLowerLoad(LegalizerHelper &Helper, GAnyLoad &LoadMI) const;
	/// Called for instructions with the Custom LegalizationAction.
	virtual bool legalizeCustom(LegalizerHelper &Helper, MachineInstr &MI) const
			override;
};

}

#ifdef LLVM_MUST_UNDEF_NDEBUG
#undef NDEBUG
#undef LLVM_MUST_UNDEF_NDEBUG
#endif

