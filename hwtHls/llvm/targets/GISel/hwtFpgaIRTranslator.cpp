#include <hwtHls/llvm/targets/GISel/hwtFpgaIRTranslator.h>
#include <llvm/IR/Attributes.h>

using namespace llvm;

namespace hwtHls {

// A class with implements RAII
class WithMinSizeSet {
	Function &F;
	bool hadMinSize;
public:
	WithMinSizeSet(Function &F) :
			F(F), hadMinSize(F.hasMinSize()) {
		F.addFnAttr(Attribute::MinSize);
	}
	~WithMinSizeSet() {
		if (!hadMinSize)
			F.removeFnAttr(Attribute::MinSize);
	}
};

bool HwtFpgaIRTranslator::runOnMachineFunction(llvm::MachineFunction &MF) {
	Function &F = MF.getFunction();
	WithMinSizeSet _(F);
	return IRTranslator::runOnMachineFunction(MF);
}

}
