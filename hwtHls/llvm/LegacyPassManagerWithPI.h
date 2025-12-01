#pragma once
#include <llvm/IR/LegacyPassManager.h>
#include <llvm/IR/PassInstrumentation.h>

namespace hwtHls {

class LegacyPassManagerWithPI: public llvm::legacy::PassManager {
	llvm::PassInstrumentation PI;
public:
	LegacyPassManagerWithPI(llvm::PassInstrumentationCallbacks &PIC) :
			llvm::legacy::PassManager(), PI(&PIC) {
	}
	void addPassCallbackFromPI(llvm::Pass *P);
	void add(llvm::Pass *P) override;
};

}
