#pragma once
#include <llvm/CodeGen/GlobalISel/LegalizerInfo.h>

namespace llvm {

class GenericFpgaTargetSubtarget;

/// This class provides the information for the target register banks.
/// :note: same as `RISCVLegalizerInfo`
class GenericFpgaLegalizerInfo: public LegalizerInfo {
public:
	GenericFpgaLegalizerInfo(const GenericFpgaTargetSubtarget &ST);
};

}
