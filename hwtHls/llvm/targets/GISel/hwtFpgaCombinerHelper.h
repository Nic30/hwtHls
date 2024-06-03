#pragma once

#include <llvm/CodeGen/GlobalISel/CombinerHelper.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>

namespace llvm {


/* Helper class for GISel framework to implement hwtHls combination rules.
 * It contains c++ implementation of matching and rewrite functions which are used in HwtFpgaCombine.td.
 * .td file also contains doc for functions defined there;
 * */
class HwtFpgaCombinerHelper: public llvm::CombinerHelper {
public:
	struct ConcatMember {
		MachineOperand &op;
		uint64_t offsetOfUse, width, widthOfUse;
	};

	using llvm::CombinerHelper::CombinerHelper;
	MachineInstr* getOpcodeDef(unsigned Opcode, Register Reg,
			const MachineRegisterInfo &MRI);
	bool isUndefOperand(const MachineOperand &MO);
	bool matchAnyExplicitUseIsUndef(MachineInstr &MI);
	//bool replaceInstWithUndefNonGeneric(MachineInstr &MI);



	bool hasG_CONSTANTasUse(llvm::MachineInstr &MI);
	void rewriteG_CONSTANTasUseAsCImm(llvm::MachineInstr &MI);

	bool matchAllOnesConstantOp(const llvm::MachineOperand &MOP);
	bool matchOperandIsAllOnes(llvm::MachineInstr &MI, unsigned OpIdx);
	void rewriteXorToNot(llvm::MachineInstr &MI);

	void rewriteConstBinOp(llvm::MachineInstr &MI,
			std::function<APInt(const APInt&, const APInt&)>);

	// :attention: this is only for instructions in same block
	//             extract/merge instruction does copy of original data, it must be proven that
	//             correct copy is used and we can no just take any register with output
	bool matchIsExtractOnMergeValues(llvm::MachineInstr &MI);
	void rewriteExtractOnMergeValues(llvm::MachineInstr &MI);
	bool matchIsExtractOnConstShift(llvm::MachineInstr &MI);
	void rewriteExtractOnConstShift(llvm::MachineInstr &MI);
	/*
	 * Recursively collect members of concatenations, looks through HWTFPGA_EXTRACT and HWTFPGA_MERGE_VALUES instructions
	 *
	 * :param MIOp: an operand from where to collect concat members
	 * :param members: output vector of records containing the operand and the information about which bits are selected
	 * :param mainOffset: offsets (number of bits) where selected value from whole value
	 * :param mainWidth: number of bits to select in total
	 * :param currentOffset: a number of bits already collected
	 * :param offsetOfIRes: offsets (number of bits) where selected value from this operand starts
	 * :param widthOfIRes: a number of bits to select from this operand
	 * */
	bool collectConcatMembers(llvm::MachineOperand &MIOp,
			std::vector<ConcatMember> &members, uint64_t mainOffset,
			uint64_t mainWidth, uint64_t &currentOffset, uint64_t offsetOfIRes,
			uint64_t widthOfIRes);
	void convertG_SELECT_to_HWTFPGA_MUX(llvm::MachineInstr &MI);
	void convertPHI_to_HWTFPGA_MUX(llvm::MachineInstr &MI);
	bool hasSomeConstConditions(llvm::MachineInstr &MI);
	void rewriteConstCondMux(llvm::MachineInstr &MI);

	bool matchMuxForConstPropagation(llvm::MachineInstr &MI,
			hwtHls::MuxReducibleValuesInfo &matchInfo);
	[[nodiscard]] Register _rewriteMuxConstPropagationExpandReducedBits(llvm::MachineInstr &MI,
			hwtHls::MuxReducibleValuesInfo &matchInfo,
			const std::vector<std::pair<bool, unsigned>> &usedBitsVec);
	bool rewriteMuxConstPropagation(llvm::MachineInstr &MI,
			hwtHls::MuxReducibleValuesInfo &matchInfo);
	//bool matchMuxSinkDirectlyCondDrivenValBits(llvm::MachineInstr &MI,
	//		hwtHls::MuxDirectlyCondDrivenBits &matchInfo);
	//bool rewriteMuxSinkDirectlyCondDrivenValBits(llvm::MachineInstr &MI,
	//			hwtHls::MuxDirectlyCondDrivenBits &matchInfo);

	// check if can merge two HWTFPGA_MUX instructions
	bool matchNestedMux(llvm::MachineInstr &MI,
			llvm::SmallVector<bool> &requiresAndWithParentCond);
	void rewriteNestedMuxToMux(llvm::MachineInstr &MI,
			const llvm::SmallVector<bool> &requiresAndWithParentCond);
	bool matchMuxDuplicitCaseReduce(llvm::MachineInstr &MI, llvm::SmallVector<unsigned> & duplicitCaseConditions);
	bool matchMuxRedundantCase(llvm::MachineInstr &MI, llvm::SmallVector<unsigned> &caseConditionsToRm);
	void rewriteMuxRmCases(llvm::MachineInstr &MI, const llvm::SmallVector<unsigned> & caseConditionsToRm);

	bool hasAll1AndAll0Values(llvm::MachineInstr &MI,
			hwtHls::CImmOrRegWithNegFlag &matchinfo);
	void rewriteConstValMux(llvm::MachineInstr &MI,
			const hwtHls::CImmOrRegWithNegFlag &matchinfo);
	bool matchMuxMask(llvm::MachineInstr &MI, BuildFnTy &rewriteFn);

	bool matchCmpToMsbCheck(llvm::MachineInstr &MI, BuildFnTy &rewriteFn);

	bool matchConstCmpConstAdd(llvm::MachineInstr &MI, BuildFnTy &rewriteFn);

	/*
	 * Search if HWTFPGA_MUX used as a copy could be removed by using src/dst register directly
	 **/
	bool isTrivialRemovableCopy(llvm::MachineInstr &MI, bool &replaceMuxSrcReg);
	void rewriteTrivialRemovableCopy(llvm::MachineInstr &MI,
			bool replaceMuxSrcReg);

	void rewriteGenericOpcodeToHwtFpga(llvm::MachineInstr &MI);

	bool hashOnlyConstUses(llvm::MachineInstr &MI);
	void rewriteConstExtract(llvm::MachineInstr &MI);
	void rewriteConstMergeValues(llvm::MachineInstr &MI);
	bool matchConstMergeValues(llvm::MachineInstr &MI,
			llvm::APInt &replacement);
	void rewriteConstMergeValues(llvm::MachineInstr &MI,
			const llvm::APInt &replacement);

	bool matchTrivialInstrDuplication(llvm::MachineInstr &MI);
	void rewriteTrivialInstrDuplication(llvm::MachineInstr &MI);

	bool matchAndOrSequenceReduce(llvm::MachineInstr &MI, bool& removeRightOp);
	void rewriteAndOrSequenceReduce(llvm::MachineInstr &MI, bool removeRightOp);
};

}
