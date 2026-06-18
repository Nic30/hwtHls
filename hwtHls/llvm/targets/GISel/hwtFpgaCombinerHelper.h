#pragma once

#include <llvm/CodeGen/GlobalISel/CombinerHelper.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtilsInstrFns.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtilsInstrReducibleValuesInfo.h>
#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>
#include <string>

namespace llvm {

class MatchFMulByPow2MatchInfo {
public:
	hwtHls::HFloatTmpConfig fpCfg;
	bool isZero;
	int sh;

	MatchFMulByPow2MatchInfo() :
			isZero(false), sh(0) {
	}
	void clear() {
		isZero = false;
		sh = 0;
	}
};

class MatchFDivByPowiMatchInfo {
public:
	hwtHls::HFloatTmpConfig fpCfg;
	bool isDiv0; // is in format x / (0.0 ** sh)
	bool isDiv1; // is in format x / (1.0 ** sh)
	std::optional<bool> knownValueOfShMsb;
	std::optional<size_t> shWidth;
	MatchFDivByPowiMatchInfo() {
		clear();
	}
	void clear() {
		fpCfg = hwtHls::HFloatTmpConfig();
		isDiv0 = false;
		isDiv1 = false;
		knownValueOfShMsb = { };
		shWidth = { };
	}
};

class MatchMulHLOperand {
public:
	SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> opParts;
	size_t width;
	bool isSigned;
	MachineInstr *def; // insert point for potential operand value construction
	MatchMulHLOperand() {
		clear();
	}
	void clear() {
		opParts.clear();
		width = 0;
		isSigned = false;
		def = nullptr;

	}
};
class MatchMulHL {
public:
	std::array<MatchMulHLOperand, 2> ops;
	MatchMulHL() {
		clear();
	}
	void clear() {
		ops[0].clear();
		ops[1].clear();
	}
};

/* Helper class for GISel framework to implement hwtHls combination rules.
 * It contains c++ implementation of matching and rewrite functions which are used in HwtFpgaCombine.td.
 * .td file also contains doc for functions defined there;
 * */
class HwtFpgaCombinerHelper: public llvm::CombinerHelper {
public:
	
	struct ConcatMember {
		const MachineOperand &op;
		const ConstantInt *constOverride; // if specified the op should not be used and this const should be used instead
		uint64_t offsetOfUse;
		uint64_t width;
		uint64_t widthOfUse;
		MachineInstr *existingSlice; //  optional pointer to HWTFPGA_EXTRACT instruction implementing bit extraction
		// as specified by this struct

		ConcatMember(const MachineOperand &op, uint64_t offsetOfUse,
				uint64_t width, uint64_t widthOfUse);
	};
	std::function<void(const std::string & ruleName, const llvm::MachineFunction & MF)> * _dbgMirGISelCombinerChangeCallbackFn;
	HwtFpgaCombinerHelper(GISelChangeObserver &Observer, MachineIRBuilder &B,
	               bool IsPreLegalize, const TargetPassConfig *TPC, GISelValueTracking *VT = nullptr,
	               MachineDominatorTree *MDT = nullptr,
	               const LegalizerInfo *LI = nullptr);

	void replaceInstWithUndef(llvm::MachineInstr & MI);

	// :note: does not require SSA
	bool matchEqualDefs(const llvm::MachineOperand &MO0,
			const llvm::MachineOperand &MO1); // override
	bool matchEqualDefs(const MachineInstr &MI0, const MachineInstr &MI1,
			size_t opI);
	/* If register is defined only by an instruction of the specified code return it*/
	MachineInstr* getOpcodeDef(unsigned Opcode, Register Reg,
			const llvm::MachineRegisterInfo &MRI);
	bool isUndefOperand(const llvm::MachineOperand &MO);
	bool matchAnyExplicitUseIsUndef(llvm::MachineInstr &MI);
	//bool replaceInstWithUndefNonGeneric(MachineInstr &MI);

	MachineOperand* getNextUseOfRegInBlock(MachineInstr &MI,
			Register &DstRegNo);
	bool checkAnyOperandRedefined(MachineInstr &MI, MachineInstr &MIEnd);
	MachineOperand* getNextUseOfRegAfterInstructionExceptMI(Register DstRegNo,
			MachineInstr &MI);

	bool hasG_CONSTANTasUse(MachineInstr &MI);
	static bool hasG_CONSTANTasUse(llvm::MachineRegisterInfo &MRI,
			llvm::MachineInstr &MI);
	static void rewriteG_CONSTANTasUseAsCImm(llvm::MachineIRBuilder &Builder,
			llvm::GISelChangeObserver *Observer, llvm::MachineInstr &MI);
	void rewriteG_CONSTANTasUseAsCImm(llvm::MachineInstr &MI);

	bool matchAllOnesConstantOp(const llvm::MachineOperand &MOP);
	bool matchOperandIsAllOnes(llvm::MachineInstr &MI, unsigned OpIdx);
	void rewriteXorToNot(llvm::MachineInstr &MI);

	void rewriteConstBinOp(llvm::MachineInstr &MI,
			std::function<APInt(const APInt&, const APInt&)>);

	// :attention: this is only for instructions in same block
	//             extract/merge instruction does copy of original data, it must be proven that
	//             correct copy is used and we can not just take any register with output
	bool matchIsExtractOnMergeValues(llvm::MachineInstr &MI,
			std::vector<ConcatMember> &concatMembers);
	void rewriteExtractOnMergeValues(llvm::MachineInstr &MI,
			const std::vector<ConcatMember> &concatMembers);

	bool matchIsExtractOnConstShift(llvm::MachineInstr &MI);
	void rewriteExtractOnConstShift(llvm::MachineInstr &MI);

	bool matchExtractOfSameWidth(llvm::MachineInstr &MI);
	void rewriteExtractOfSameWidthToCopy(llvm::MachineInstr &MI);

	bool matchNestedMERGE_VALUES(MachineInstr &MI);
	void rewriteNestedMERGE_VALUES(MachineInstr &MI);

	/*
	 * Recursively collect members of concatenations, looks through HWTFPGA_EXTRACT and HWTFPGA_MERGE_VALUES instructions
	 *
	 * :param MIOp: an operand from where to collect concat members
	 * :param members: output vector of records containing the operand and the information about which bits are selected
	 * :param mainOffset: offsets (number of bits) where selected value from whole value begins
	 * :param mainWidth: number of bits to select in total
	 * :param mainOffsetCurrent: a number of bits already collected
	 * :param MIOpOffset: offsets (number of bits) where selected value from this operand starts
	 * :param MIOpWidth: a number of bits for MIOp (the result operand of some instruction)
	 * :param MIOpSelectedWidth: a number of bits extracted from MIOpWidth used by this member (MIOp value may actually be wider MIOpWidth)
	 * */
	bool collectConcatMembers(llvm::MachineOperand &MIOp,
			std::vector<ConcatMember> &members, uint64_t mainOffset,
			uint64_t mainWidth, uint64_t &mainOffsetCurrent,
			uint64_t MIOpOffset, uint64_t MIOpWidth,
			uint64_t MIOpSelectedWidth);
	// fallback of collectConcatMembers which just takes MIOp as is and put it inside of members vector
	bool collectConcatMembersAsItIs(llvm::MachineOperand &MIOp,
			std::vector<HwtFpgaCombinerHelper::ConcatMember> &members,
			uint64_t mainOffset, uint64_t mainWidth,
			uint64_t &mainOffsetCurrent, uint64_t MIOpOffset,
			uint64_t MIOpWidth, uint64_t MIOpSelectedWidth);
	MachineInstrBuilder buildHwtFpgaCopy(MachineOperand opDst,
			MachineOperand opSrc);
	MachineInstrBuilder buildHwtFpgaCopy(MachineOperand opSrc);

	void copyOperand(MachineInstrBuilder &MIB, MachineRegisterInfo &MRI,
			MachineFunction &MF, MachineOperand &MO);
	void copyOperandsForHFloatTmpAndPredicate(MachineInstrBuilder &MIB,
			size_t offset, MachineInstr &MI);
	void convertG_SELECT_to_HWTFPGA_MUX(llvm::MachineInstr &MI);
	void convertPHI_to_HWTFPGA_MUX(llvm::MachineInstr &MI);
	bool hasSomeConstConditions(llvm::MachineInstr &MI);
	void rewriteConstCondMux(llvm::MachineInstr &MI);

	bool matchMuxForConstPropagation(llvm::MachineInstr &MI,
			hwtHls::MuxReducibleValuesInfo &matchInfo);
	/*
	 * Build a value which represents the original value before some bits were reduced
	 * */
	[[nodiscard]] Register _rewriteMuxConstPropagationExpandReducedBits(
			llvm::MachineInstr &MI, hwtHls::MuxReducibleValuesInfo &matchInfo,
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
	bool matchMuxDuplicitCaseReduce(llvm::MachineInstr &MI,
			llvm::SmallVector<unsigned> &duplicitCaseConditions);
	bool matchMuxRedundantCase(llvm::MachineInstr &MI,
			llvm::SmallVector<unsigned> &caseConditionsToRm);
	void rewriteMuxRmCases(llvm::MachineInstr &MI,
			const llvm::SmallVector<unsigned> &caseConditionsToRm);

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

	// :note: similarity with matchIsExtractOnMergeValues, rewriteExtractOnMergeValues, collectConcatMembers
	bool matchIsMergeValueContinuousSlice(llvm::MachineInstr &MI,
			std::vector<ConcatMember> &concatMembers);
	void rewriteMergeValueContinuousSlice(llvm::MachineInstr &MI,
			const std::vector<ConcatMember> &concatMembers);

	bool matchTrivialInstrDuplication(llvm::MachineInstr &MI);
	void rewriteTrivialInstrDuplication(llvm::MachineInstr &MI);

	bool matchAndOrSequenceReduce(llvm::MachineInstr &MI, bool &removeRightOp);
	void rewriteAndOrSequenceReduce(llvm::MachineInstr &MI, bool removeRightOp);

	void rewriteConstShift(llvm::MachineInstr &MI);
	void rewriteConstFunnelShift(llvm::MachineInstr &MI);

	bool matchMulHL(llvm::MachineInstr &MI, MatchMulHL &matchinfo);
	void rewriteMulToMulHL(llvm::MachineInstr &MI, const MatchMulHL &matchinfo);

	// hwtFpgaCombinerHelperFP.cpp
	bool matchFMulByPow2(llvm::MachineInstr &MI,
			MatchFMulByPow2MatchInfo &shValue);
	void rewriteFMulByPow2(llvm::MachineInstr &MI,
			MatchFMulByPow2MatchInfo shValue);
	bool matchFDivByPowi(llvm::MachineInstr &MI,
			MatchFDivByPowiMatchInfo &shValue);
	void rewriteFDivByPowi(llvm::MachineInstr &MI,
			MatchFDivByPowiMatchInfo shValue);

	bool matchCombineSinCos(MachineInstr &MI, MachineInstr *&OtherMI);
	void applyCombineSinCos(MachineInstr &MI, MachineInstr *&OtherMI);

	void onChangeTestCallback(const std::string & ruleName);
};

}
