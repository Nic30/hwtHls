#pragma once

#include <llvm/CodeGen/GlobalISel/CombinerHelper.h>
namespace llvm {

struct CImmOrRegWithNegFlag {
	bool Negate;
	const ConstantInt *CImm;
	Register Reg;
};

class GenFpgaCombinerHelper: public llvm::CombinerHelper {
public:
	struct ConcatMember {
		MachineOperand &op;
		uint64_t offsetOfUse, width, widthOfUse;
	};

	using llvm::CombinerHelper::CombinerHelper;

	bool hashOnlyConstUses(llvm::MachineInstr &MI);
	bool rewriteConstExtract(llvm::MachineInstr &MI);
	bool rewriteConstMergeValues(llvm::MachineInstr &MI);

	bool hasG_CONSTANTasUse(llvm::MachineInstr &MI);
	bool rewriteG_CONSTANTasUseAsCImm(llvm::MachineInstr &MI);

	bool matchAllOnesConstantOp(const llvm::MachineOperand &MOP);
	bool matchOperandIsAllOnes(llvm::MachineInstr &MI, unsigned OpIdx);
	bool rewriteXorToNot(llvm::MachineInstr &MI);

	bool rewriteConstBinOp(llvm::MachineInstr &MI,
			std::function<APInt(const APInt&, const APInt&)>);

	bool hashSomeConstConditions(llvm::MachineInstr &MI);
	bool rewriteConstCondMux(llvm::MachineInstr &MI);

	bool matchIsExtractOnMergeValues(llvm::MachineInstr &MI);
	bool rewriteExtractOnMergeValues(llvm::MachineInstr &MI);
	bool collectConcatMembers(llvm::MachineOperand &MIOp,
			std::vector<ConcatMember> &members, uint64_t mainOffset,
			uint64_t mainWidth, uint64_t &currentOffset, uint64_t offsetOfIRes,
			uint64_t widthOfIRes);
	// check if can merge two GENFPGA_MUX instructions
	bool matchNestedMux(llvm::MachineInstr &MI);
	bool rewriteNestedMuxToMux(llvm::MachineInstr &MI);

	bool hasAll1AndAll0Values(llvm::MachineInstr &MI,
			CImmOrRegWithNegFlag &matchinfo);
	bool rewriteConstValMux(llvm::MachineInstr &MI,
			const CImmOrRegWithNegFlag &matchinfo);

};

}
