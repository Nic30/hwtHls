#pragma once
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>

#include <hwtHls/llvm/ADT/bimap.h>
#include <hwtHls/llvm/targets/Analysis/VRegLiveins.h>

namespace hwtHls {

// try to find the register with a negation of specified register for a place defined by TargetMBB and TargetIp
// :returns: defining machine operand
llvm::MachineOperand* getRegisterNegationIfExits(llvm::MachineRegisterInfo &MRI,
		llvm::MachineBasicBlock &TargetMBB,
		llvm::MachineBasicBlock::iterator TargetIp, llvm::Register reg, bool& wasOriginallyKill);

// create register with a negation of the register
llvm::MachineOperand& _negateRegister(llvm::MachineRegisterInfo &MRI,
		llvm::MachineIRBuilder &Builder, llvm::Register reg,
		bool isKill = false);

// return existing register with negation if negation of register exits
// or create register with a negation of the register
llvm::Register negateRegister(llvm::MachineRegisterInfo &MRI,
		llvm::MachineIRBuilder &Builder, llvm::Register reg,
		bool isKill = false);

std::pair<llvm::MachineIRBuilder, llvm::Register> negateRegisterForInstr(
		llvm::MachineInstr &MI, llvm::Register reg, bool isKill = false);

bool machineInstructionIsSuccessorInSameBlock(const llvm::MachineInstr &MI0,
		const llvm::MachineInstr &MI1);

bool registerIsUsedOnlyInPhisOfSuccessorOrInternallyInBlock(
		const llvm::MachineInstr &defInstr, llvm::Register reg);

bool registerDefinedInEveryBlock(const llvm::MachineRegisterInfo &MRI,
		llvm::iterator_range<llvm::MachineBasicBlock::const_pred_iterator> blocks,
		llvm::Register reg);

/*
 * Replace all def operands, which register is liveout, with a newly generated register.
 * This register should then be used in all successor instructions in this block (def and use).
 * After block there should be a mux/select to select value if predication was successful.

 * :note: This should be used for non predictable instructions.
 *  The instruction may not be modified if all defs are not liveouts.
 *
 * :param regReplaces: map original register -> new replacement and back
 * */
void predicateInstructionUsingDefRegRename(llvm::MachineRegisterInfo &MRI,
		const HwtHlsVRegLiveins &VRegLiveins, llvm::MachineInstr &MI,
		bimap<llvm::Register, llvm::Register> &regReplaces);
/*
 * In specified block insert a set of MUXes to conditionally copy speculated register values to a final register.
 * */
void createSpeculationMergeMuxes(llvm::MachineBasicBlock &insertPointBlock,
		llvm::MachineBasicBlock::iterator insertPointIt,
		const bimap<llvm::Register, llvm::Register> &regsForSpeculation,
		const llvm::ArrayRef<llvm::MachineOperand> &Predicate,
		llvm::MachineRegisterInfo &MRI);

/*
 * If not TII.SubsumesPredicate then
 * Create an AND of two conditions and place the result in second condition
 * */
void Condition_and(llvm::MachineIRBuilder &Builder,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op0,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op1AndDst);
void Condition_or(llvm::MachineIRBuilder &Builder,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op0,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op1AndDst);

/*
 * Op0, Op1AndDst are in KNF, in form of tuples (reg, isNegated flag)
 * */
void Condition_and_or(unsigned opcode_and_or, llvm::MachineIRBuilder &Builder,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op0,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op1AndDst);
/*
 * After CvtTMBB was ifconverted update or replace PHIs in NextMBB
 *
 * :param CvtTMBB: block which was just merged into TopMBB
 * :param Cond: condition which enables instructions from CvtTMBB which are now merged into TopMBB
 * :param NextMBB: successor of TopMBB and CvtTMBB
 * */
void PHIsToSelectAfterIfCvt(HwtHlsVRegLiveins &VRegLiveins,
		llvm::MachineBasicBlock &TopMBB,
		const llvm::SmallVectorImpl<llvm::MachineOperand> &Cond,
		llvm::MachineBasicBlock &CvtTMBB, llvm::MachineBasicBlock &NextMBB);

}
