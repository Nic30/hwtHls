#pragma once

#include <llvm/CodeGen/GlobalISel/CombinerHelper.h>
#include <llvm/IR/Constants.h>

namespace llvm {

struct CImmOrRegWithNegFlag {
	bool Negate;
	const ConstantInt *CImm;
	Register Reg;
};

class HwtFpgaCombinerHelper: public llvm::CombinerHelper {
public:
	struct ConcatMember {
		MachineOperand &op;
		uint64_t offsetOfUse, width, widthOfUse;
	};
	struct CImmOrReg {
		const ConstantInt *c;
		Register reg;
		CImmOrReg(const MachineOperand &MOP);
		CImmOrReg(const ConstantInt *c);
		void addAsUse(MachineInstrBuilder & MIB) const;
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

	bool matchIsExtractOnMergeValues(llvm::MachineInstr &MI);
	bool rewriteExtractOnMergeValues(llvm::MachineInstr &MI);
	bool collectConcatMembers(llvm::MachineOperand &MIOp,
			std::vector<ConcatMember> &members, uint64_t mainOffset,
			uint64_t mainWidth, uint64_t &currentOffset, uint64_t offsetOfIRes,
			uint64_t widthOfIRes);

	//bool matchMuxWithRedundantCases(llvm::MachineInstr &MI, llvm::SmallVector<unsigned> & uselessConditions);
	//bool rewriteMuxWithRedundantCases(llvm::MachineInstr &MI, const llvm::SmallVector<unsigned> & uselessConditions);

	bool hashSomeConstConditions(llvm::MachineInstr &MI);
	bool rewriteConstCondMux(llvm::MachineInstr &MI);

	// check if can merge two HWTFPGA_MUX instructions
	bool matchNestedMux(llvm::MachineInstr &MI,
			llvm::SmallVector<bool> &requiresAndWithParentCond);
	bool rewriteNestedMuxToMux(llvm::MachineInstr &MI,
			const llvm::SmallVector<bool> &requiresAndWithParentCond);

	bool hasAll1AndAll0Values(llvm::MachineInstr &MI,
			CImmOrRegWithNegFlag &matchinfo);
	bool rewriteConstValMux(llvm::MachineInstr &MI,
			const CImmOrRegWithNegFlag &matchinfo);
	bool matchMuxMask(llvm::MachineInstr &MI, BuildFnTy &rewriteFn);

	bool matchCmpToMsbCheck(llvm::MachineInstr &MI, BuildFnTy &rewriteFn);

	bool matchConstCmpConstAdd(llvm::MachineInstr &MI, BuildFnTy &rewriteFn);

	bool isTrivialRemovableCopy(llvm::MachineInstr &MI, bool& replaceMuxSrcReg);
	bool rewriteTrivialRemovableCopy(llvm::MachineInstr &MI, bool replaceMuxSrcReg);

};

}
