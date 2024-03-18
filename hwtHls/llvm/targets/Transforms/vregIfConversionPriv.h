#pragma once

#include <hwtHls/llvm/targets/Transforms/vregIfConversion.h>
#include <hwtHls/llvm/targets/Transforms/vregConditionUtils.h>
#include <hwtHls/llvm/llvmSrc/BranchFolding.h>
#include <hwtHls/llvm/targets/Transforms/liveVRegs.h>

#include <llvm/ADT/SmallSet.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/Analysis/ProfileSummaryInfo.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineBlockFrequencyInfo.h>
#include <llvm/CodeGen/MachineBranchProbabilityInfo.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/CodeGen/MachineInstrBuilder.h>
#include <llvm/CodeGen/MachineOperand.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/TargetInstrInfo.h>
#include <llvm/CodeGen/TargetLowering.h>
#include <llvm/CodeGen/TargetRegisterInfo.h>
#include <llvm/CodeGen/TargetSchedule.h>
#include <llvm/CodeGen/TargetSubtargetInfo.h>
#include <llvm/Support/BranchProbability.h>
#include <llvm/Support/CommandLine.h>
#include <llvm/Support/raw_ostream.h>
#include <algorithm>
#include <functional>

#include <hwtHls/llvm/targets/Analysis/VRegLiveins.h>


#include <hwtHls/llvm/targets/Transforms/writeCFGToDotFile.h>
#define VREG_IF_CONVERTER_DUMPID << " " << dbgCntr


namespace hwtHls {

class VRegIfConverter: public llvm::MachineFunctionPass {
	enum IfcvtKind {
		ICNotClassfied,  // BB data valid, but not classified.
		ICSimpleFalse,   // Same as ICSimple, but on the false path.
		ICSimple,        // BB is entry of an one split, no rejoin sub-CFG.
		ICTriangleFRev, // Same as ICTriangleFalse, but false path rev condition.
		ICTriangleRev,   // Same as ICTriangle, but true path rev condition.
		ICTriangleFalse, // Same as ICTriangle, but on the false path.
		ICTriangle,      // BB is entry of a triangle sub-CFG.
		ICDiamond,       // BB is entry of a diamond sub-CFG.
		ICForkedDiamond, // BB is entry of an almost diamond sub-CFG, with a
						 // common tail that can be shared.
		ICLoopTail,      // EBB is entry of the loop and true successor BB has EBB as a T successor and EBB as a single predecessor (BBI is for block BB)
		ICLoopTailFalse, // same as ICLoopWithTail but the successor BB is on F branch
		ICLoopTailRev,   // same as ICLoopWithTail but EBB is on F branch from successor BB
		ICLoopTailFRev,  // same as ICLoopWithTail but successor BB is on F branch and EBB is on F branch from successor BB
	};
	const char * IfcvtKind_toStr(VRegIfConverter::IfcvtKind Kind);

	/// One per MachineBasicBlock, this is used to cache the result
	/// if-conversion feasibility analysis. This includes results from
	/// TargetInstrInfo::analyzeBranch() (i.e. TBB, FBB, and Cond), and its
	/// classification, and common tail block of its successors (if it's a
	/// diamond shape), its size, whether it's predicable, and whether any
	/// instruction can clobber the 'would-be' predicate.
	///
	/// IsDone          - True if BB is not to be considered for ifcvt.
	/// IsBeingAnalyzed - True if BB is currently being analyzed.
	/// IsAnalyzed      - True if BB has been analyzed (info is still valid).
	/// IsEnqueued      - True if BB has been enqueued to be ifcvt'ed.
	/// IsBrAnalyzable  - True if analyzeBranch() returns false.
	/// HasFallThrough  - True if BB may fallthrough to the following BB.
	/// IsUnpredicable  - True if BB is known to be unpredicable.
	/// ClobbersPred    - True if BB could modify predicates (e.g. has
	///                   cmp, call, etc.)
	/// NonPredSize     - Number of non-predicated instructions.
	/// ExtraCost       - Extra cost for multi-cycle instructions.
	/// ExtraCost2      - Some instructions are slower when predicated
	/// BB              - Corresponding MachineBasicBlock.
	/// TrueBB / FalseBB- See analyzeBranch().
	/// BrCond          - Conditions for end of block conditional branches.
	/// Predicate       - Predicate used in the BB.
	struct BBInfo {
		bool IsDone :1;
		bool IsBeingAnalyzed :1;
		bool IsAnalyzed :1;
		bool IsEnqueued :1;
		bool IsBrAnalyzable :1;
		bool IsBrReversible :1;
		bool HasFallThrough :1;
		bool IsUnpredicable :1;
		bool CannotBeCopied :1;
		bool ClobbersPred :1;
		unsigned NonPredSize = 0;
		unsigned ExtraCost = 0;
		unsigned ExtraCost2 = 0;
		llvm::MachineBasicBlock *BB = nullptr;
		llvm::MachineBasicBlock *TrueBB = nullptr;
		llvm::MachineBasicBlock *FalseBB = nullptr;
		llvm::SmallVector<llvm::MachineOperand, 4> BrCond;
		llvm::SmallVector<llvm::MachineOperand, 4> Predicate;

		BBInfo() :
				IsDone(false), IsBeingAnalyzed(false), IsAnalyzed(false), IsEnqueued(
						false), IsBrAnalyzable(false), IsBrReversible(false), HasFallThrough(
						false), IsUnpredicable(false), CannotBeCopied(false), ClobbersPred(
						false) {
		}
	};

	/// Record information about pending if-conversions to attempt:
	/// BBI             - Corresponding BBInfo.
	/// Kind            - Type of block. See IfcvtKind.
	/// NeedSubsumption - True if the to-be-predicated BB has already been
	///                   predicated.
	/// NumDups      - Number of instructions that would be duplicated due
	///                   to this if-conversion. (For diamonds, the number of
	///                   identical instructions at the beginnings of both
	///                   paths).
	/// NumDups2     - For diamonds, the number of identical instructions
	///                   at the ends of both paths.
	struct IfcvtToken {
		BBInfo &BBI;
		IfcvtKind Kind;
		unsigned NumDups;
		unsigned NumDups2;
		bool NeedSubsumption :1;
		bool TClobbersPred :1;
		bool FClobbersPred :1;

		IfcvtToken(BBInfo &b, IfcvtKind k, bool s, unsigned d, unsigned d2 = 0,
				bool tc = false, bool fc = false) :
				BBI(b), Kind(k), NumDups(d), NumDups2(d2), NeedSubsumption(s), TClobbersPred(
						tc), FClobbersPred(fc) {
		}
	};

	/// Results of if-conversion feasibility analysis indexed by basic block
	/// number.
	std::vector<BBInfo> BBAnalysis;
	llvm::TargetSchedModel SchedModel;

	const llvm::TargetLoweringBase *TLI;
	const llvm::TargetInstrInfo *TII;
	const llvm::TargetRegisterInfo *TRI;
	const llvm::MachineBranchProbabilityInfo *MBPI;
	llvm::MachineRegisterInfo *MRI;
	hwtHls::HwtHlsVRegLiveins *VRegLiveins;

	hwtHls::LiveVRegs Redefs;

	bool PreRegAlloc;
	bool MadeChange;
	int FnNum = -1;
	std::function<bool(const llvm::MachineFunction&)> PredicateFtor;

	// debug variables
	bool enableTrace;
	size_t dbgCntr;

public:
	static char ID;

	VRegIfConverter(std::function<bool(const llvm::MachineFunction&)> Ftor = nullptr);
	void getAnalysisUsage(llvm::AnalysisUsage &AU) const override;

	bool runOnMachineFunction(llvm::MachineFunction &MF) override;

	llvm::MachineFunctionProperties getRequiredProperties() const override;

private:
	bool reverseBranchCondition(BBInfo &BBI);
	bool ValidSimple(BBInfo &TrueBBI, BBInfo &OtherBBI, unsigned &Dups,
			llvm::BranchProbability Prediction) const;
	bool ValidTriangle(BBInfo &TrueBBI, BBInfo &FalseBBI, bool FalseBranch,
			unsigned &Dups, llvm::BranchProbability Prediction) const;
	bool CountDuplicatedInstructions(llvm::MachineBasicBlock::iterator &TIB,
			llvm::MachineBasicBlock::iterator &FIB, llvm::MachineBasicBlock::iterator &TIE,
			llvm::MachineBasicBlock::iterator &FIE, unsigned &Dups1, unsigned &Dups2,
			llvm::MachineBasicBlock &TBB, llvm::MachineBasicBlock &FBB,
			bool SkipUnconditionalBranches) const;
	bool ValidDiamond(BBInfo &TrueBBI, BBInfo &FalseBBI, unsigned &Dups1,
			unsigned &Dups2, BBInfo &TrueBBICalc, BBInfo &FalseBBICalc) const;
	bool ValidForkedDiamond(BBInfo &TrueBBI, BBInfo &FalseBBI, unsigned &Dups1,
			unsigned &Dups2, BBInfo &TrueBBICalc, BBInfo &FalseBBICalc);
	bool ValidForkedTriangle(BBInfo &BBI, BBInfo &SuccBBI, BBInfo &OtherSuccBBI,
			bool FalseBranch, unsigned &Dups, bool& OtherSuccIsTrueSucOfSucc,
			llvm::BranchProbability Prediction) const;
	bool ValidLoopTail(BBInfo &BBI, BBInfo &SuccBBI, BBInfo &OtherSuccBBI, unsigned &Dups, bool &HeadCondRev,
			llvm::BranchProbability Prediction) const;
	bool ValidLoopTailForLoopHeader(BBInfo &LoopHeadBBI,
			BBInfo &SuccBBI, BBInfo &OtherSuccBBI, unsigned &Dups,
			bool &TailBBCondRev, llvm::BranchProbability Prediction) const;
	void AnalyzeBranches(BBInfo &BBI);
	void ScanInstructions(BBInfo &BBI, llvm::MachineBasicBlock::iterator &Begin,
			llvm::MachineBasicBlock::iterator &End,
			bool BranchUnpredicable = false) const;
	bool RescanInstructions(llvm::MachineBasicBlock::iterator &TIB,
			llvm::MachineBasicBlock::iterator &FIB, llvm::MachineBasicBlock::iterator &TIE,
			llvm::MachineBasicBlock::iterator &FIE, BBInfo &TrueBBI,
			BBInfo &FalseBBI) const;
	void AnalyzeBlock(llvm::MachineBasicBlock &MBB,
			std::vector<std::unique_ptr<IfcvtToken>> &Tokens);
	bool FeasibilityAnalysis(BBInfo &BBI, llvm::SmallVectorImpl<llvm::MachineOperand> &Pred,
			bool isTriangle = false, bool RevBranch = false,
			bool hasCommonTail = false);
	void AnalyzeBlocks(llvm::MachineFunction &MF,
			std::vector<std::unique_ptr<IfcvtToken>> &Tokens);
	void InvalidatePreds(llvm::MachineBasicBlock &MBB);
	bool IfConvertSimple(BBInfo &BBI, IfcvtKind Kind);
	bool IfConvertTriangle(BBInfo &BBI, IfcvtKind Kind);
	bool IfConvertDiamondCommon(BBInfo &BBI, BBInfo &TrueBBI, BBInfo &FalseBBI,
			unsigned NumDups1, unsigned NumDups2, bool TClobbersPred,
			bool FClobbersPred, bool RemoveBranch, bool MergeAddEdges);
	bool IfConvertDiamond(BBInfo &BBI, IfcvtKind Kind, unsigned NumDups1,
			unsigned NumDups2, bool TClobbers, bool FClobbers);
	bool IfConvertForkedDiamond(BBInfo &BBI, IfcvtKind Kind, unsigned NumDups1,
			unsigned NumDups2, bool TClobbers, bool FClobbers);
	bool IfConvertLoopTail(BBInfo &BBI, IfcvtKind Kind);

	void PredicateBlock(BBInfo &BBI, llvm::MachineBasicBlock::iterator E,
			llvm::SmallVectorImpl<llvm::MachineOperand> &Cond,
			hwtHls::bimap<llvm::Register, llvm::Register> &regsForSpeculation,
			llvm::SmallSet<llvm::Register, 4> *LaterRedefs = nullptr);
	void CopyAndPredicateBlock(BBInfo &ToBBI, BBInfo &FromBBI,
			llvm::SmallVectorImpl<llvm::MachineOperand> &Cond, bool IgnoreBr = false);
	void MergeBlocks(BBInfo &ToBBI, BBInfo &FromBBI,
			const hwtHls::bimap<llvm::Register, llvm::Register> *regsForSpeculation,
			const llvm::SmallVector<llvm::MachineOperand, 4> & Cond, bool AddEdges = true,
			bool TransferTerminator = true);

	bool MeetIfcvtSizeLimit(llvm::MachineBasicBlock &BB, unsigned Cycle,
			unsigned Extra, llvm::BranchProbability Prediction) const;

	bool MeetIfcvtSizeLimit(BBInfo &TBBInfo, BBInfo &FBBInfo,
			llvm::MachineBasicBlock &CommBB, unsigned Dups,
			llvm::BranchProbability Prediction, bool Forked) const;

	/// Returns true if Block ends without a terminator.
	bool blockAlwaysFallThrough(BBInfo &BBI) const;

	/// Used to sort if-conversion candidates.
	static bool IfcvtTokenCmp(const std::unique_ptr<IfcvtToken> &C1,
			const std::unique_ptr<IfcvtToken> &C2);

	// try to swap branch operands to eliminate negation from the branch condition
	bool normalizeBranchCondition(BBInfo & BBI);
	bool normalizeBranchConditions(MachineFunction & MF);

	// replace all blocks with just return instruction with a single block
	bool returnBlockMerge(MachineFunction & MF);
	/// Inserts an unconditional branch from \p MBB to \p ToMBB.
	inline void InsertUncondBranch(MachineBasicBlock &MBB, MachineBasicBlock &ToMBB,
	                               const TargetInstrInfo *TII) {
	  DebugLoc dl;  // FIXME: this is nowhere
	  SmallVector<MachineOperand, 0> NoCond;
	  TII->insertBranch(MBB, &ToMBB, nullptr, NoCond, dl);
	}
	static MachineBasicBlock* findFalseBlock(MachineBasicBlock *BB,
	    MachineBasicBlock *TrueBB);
	void consystencyCheck(MachineBasicBlock & MBB) const;
};


bool canFallThroughTo(llvm::MachineBasicBlock &MBB, llvm::MachineBasicBlock &ToMBB);
llvm::MachineBasicBlock* findFalseBlock(llvm::MachineBasicBlock *BB,
		llvm::MachineBasicBlock *TrueBB);

}
