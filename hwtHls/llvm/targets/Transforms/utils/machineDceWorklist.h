#pragma once

#include <hwtHls/llvm/targets/Transforms/liveVRegs.h>

namespace hwtHls {

class MachineDceWorklist {
protected:
	llvm::SmallSetVector<llvm::MachineInstr*, 16> WorkList; // main worklist containing instructions which are suspected to be dead
	llvm::MachineRegisterInfo &MRI;
	LiveVRegs *liveVregs;
public:
	MachineDceWorklist(llvm::MachineRegisterInfo &MRI, LiveVRegs *liveVregs) :
			MRI(MRI), liveVregs(liveVregs) {
	}
	bool empty() const;
	void insert(llvm::MachineInstr &MI);
	void insert(llvm::Register R);
	bool tryRemoveIfDead(llvm::MachineInstr &MI);
	bool runToCompletition();
};

}
