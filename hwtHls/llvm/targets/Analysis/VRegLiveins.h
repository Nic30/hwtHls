#pragma once

#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/ADT/SetVector.h>

#include <map>

namespace llvm {
void initializeHwtHlsVRegLiveinsPass(PassRegistry&);
}

namespace hwtHls {

class HwtHlsVRegLiveins: public llvm::MachineFunctionPass {
public:
	static char ID;
	std::map<llvm::MachineBasicBlock*, llvm::SetVector<llvm::Register>> _liveins;
	llvm::MachineFunction *MF;

	HwtHlsVRegLiveins();
	void getAnalysisUsage(llvm::AnalysisUsage &AU) const override;
	bool runOnMachineFunction(llvm::MachineFunction &MF) override;
	llvm::StringRef getPassName() const override {
		return "HwtFpgaMBBLiveIns";
	}
	const llvm::SetVector<llvm::Register>& liveins(
			const llvm::MachineBasicBlock &MBB) const;
	llvm::SetVector<llvm::Register>& liveinsMutable(
			const llvm::MachineBasicBlock &MBB);

	bool isLivein(const llvm::MachineBasicBlock &MBB, llvm::Register r) const;
	bool isLiveout(const llvm::MachineBasicBlock &MBB, llvm::Register r) const;
	bool isAnyPredecessorLiveout(const llvm::MachineBasicBlock &MBB,
			llvm::Register r) const;
	void collectLiveouts(const llvm::MachineBasicBlock &MBB,
			std::set<llvm::Register> &liveouts) const;

	void _addToLivenessUntillBlock(llvm::MachineBasicBlock &CurMBB,
			llvm::MachineBasicBlock &TargetMBB, llvm::Register RegToAdd);
	void _addToLivenessRecursively(llvm::MachineBasicBlock &CurMBB,
			llvm::Register RegToAdd);
	void addToLivenessRecursively(llvm::MachineBasicBlock &CurMBB,
			llvm::Register RegToAdd);
	/*
	 * After  TII->insertBranch() there may the defining register may be missing in liveness or branch condition operand may miss killed flag.
	 * :note: this should be called once all successors are also updated
	 * */
	void UpdateAfterInsertBranch(llvm::MachineBasicBlock &MBB);
	void UpdateKillAndDeadFlags(llvm::MachineBasicBlock &MBB);
	void UpdateKillAndDeadFlags(llvm::MachineFunction &MF);
	void recompute();

	void print(llvm::raw_ostream &O, const llvm::Module *M) const override;
};

}
namespace llvm {

inline llvm::raw_ostream& operator<<(llvm::raw_ostream &OS,
		const hwtHls::HwtHlsVRegLiveins &V) {
	V.print(OS, nullptr);
	return OS;
}

}
