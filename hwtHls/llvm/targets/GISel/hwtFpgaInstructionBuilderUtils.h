#pragma once
#include <llvm/IR/Constants.h>
#include <list>
#include <llvm/CodeGen/MachineInstrBuilder.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>

namespace hwtHls {

struct CImmOrRegWithNegFlag {
	bool Negate;
	const llvm::ConstantInt *CImm;
	llvm::Register Reg;
};

struct CImmOrReg {
	const llvm::ConstantInt *c;
	llvm::Register reg;
	CImmOrReg(llvm::Register reg);
	CImmOrReg(const llvm::MachineOperand &MOP);
	CImmOrReg(const llvm::ConstantInt *c);
	void addAsUse(llvm::MachineInstrBuilder &MIB) const;
};

struct CImmOrRegOrUndefWithWidth {
	size_t width;
	bool isUndef;
	const llvm::ConstantInt *c;
	llvm::Register reg;

	CImmOrRegOrUndefWithWidth(const llvm::ConstantInt *c);
	CImmOrRegOrUndefWithWidth(size_t width);
	CImmOrRegOrUndefWithWidth(size_t width, llvm::Register reg);
	// :param Builder: builder used to build HWTFPGA_IMPLICIT_DEF for undefs at the beginning of the entry block
	void addAsUse(llvm::MachineIRBuilder &Builder, llvm::MachineInstrBuilder &MIB) const;
	bool isReg() const {
		return c == nullptr && !isUndef;
	}
};

// same as llvm::InsertPointGuard for IRBuilder just for MachineIRBuilder
// (simplifies temporal swaps of insertion point in builder)
class MachineInsertPointGuard {
	llvm::MachineIRBuilder &Builder;
	llvm::MachineBasicBlock &origIPMBB;
	llvm::MachineBasicBlock::iterator origIP;
public:
	MachineInsertPointGuard(llvm::MachineIRBuilder &Builder,
			llvm::MachineInstr *newIP); // insert before newIP
	MachineInsertPointGuard(llvm::MachineIRBuilder &Builder,
			llvm::MachineBasicBlock &newIPMBB); // insert on the end of block
	MachineInsertPointGuard(llvm::MachineIRBuilder &Builder,
			llvm::MachineBasicBlock &newIPMBB,
			llvm::MachineBasicBlock::iterator newIP);

	~MachineInsertPointGuard();
};

size_t hwtFpgaMuxFindValueWidth(const llvm::MachineInstr &MI,
		llvm::MachineRegisterInfo &MRI);

// like RegisterIsDefinedWithinRange but begin is not tested
bool RegisterIsDefinedWithinRangeExclusive(const llvm::TargetRegisterInfo * TRI, llvm::Register r,
		llvm::MachineBasicBlock::iterator begin,
		llvm::MachineBasicBlock::iterator end);
// test if the r is defined by begin or instructions before end
bool RegisterIsDefinedWithinRange(const llvm::TargetRegisterInfo * TRI, llvm::Register r,
		llvm::MachineBasicBlock::iterator begin,
		llvm::MachineBasicBlock::iterator end);
bool RegisterIsDefinedWithinRange(const llvm::TargetRegisterInfo * TRI, llvm::Register r,
		llvm::MachineBasicBlock::const_iterator begin,
		llvm::MachineBasicBlock::const_iterator end);
bool Register_isRedefinedInLinearBlockSequenceEndToBegin(const llvm::TargetRegisterInfo * TRI, llvm::Register reg,
		llvm::MachineBasicBlock::iterator begin,
		llvm::MachineBasicBlock &EndMBB,
		llvm::MachineBasicBlock::iterator EndIp);
bool match_OperandIs1(llvm::MachineRegisterInfo &MRI,
		const llvm::MachineOperand &Op);

void Register_checkOrSetWidth(llvm::MachineRegisterInfo &MRI, llvm::Register r,
		unsigned width);

}
