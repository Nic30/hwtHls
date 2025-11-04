#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtilsInstrFns.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <llvm/CodeGen/GlobalISel/MIPatternMatch.h>

using namespace llvm;
using namespace llvm::MIPatternMatch;

namespace hwtHls {

CImmOrReg::CImmOrReg(llvm::Register reg) :
		c(nullptr), reg(reg) {
}
CImmOrReg::CImmOrReg(const MachineOperand &MOP) {
	if (MOP.isReg()) {
		c = nullptr;
		reg = MOP.getReg();
	} else if (MOP.isCImm()) {
		c = MOP.getCImm();
		reg = 0;
	} else {
		llvm_unreachable("need reg or CImm for HWTFPGA_EXTRACT");
	}
}

CImmOrReg::CImmOrReg(const ConstantInt *c) {
	assert(c->getType()->getIntegerBitWidth() > 0);
	this->c = c;
	reg = 0;
}

void CImmOrReg::addAsUse(MachineInstrBuilder &MIB) const {
	if (c) {
		assert(c->getType()->getIntegerBitWidth() > 0);
		MIB.addCImm(c);
	} else {
		MIB.addUse(reg);
	}
}

CImmOrRegOrUndefWithWidth::CImmOrRegOrUndefWithWidth(const ConstantInt *_c) :
		width(_c->getType()->getIntegerBitWidth()), isUndef(false), c(_c), reg(
				0) {
	assert(c != nullptr);
	assert(width > 0);
}

CImmOrRegOrUndefWithWidth::CImmOrRegOrUndefWithWidth(size_t _width) :
		width(_width), isUndef(true), c(nullptr), reg(0) {
	assert(width > 0);
}

CImmOrRegOrUndefWithWidth::CImmOrRegOrUndefWithWidth(size_t _width,
		Register _reg) :
		width(_width), isUndef(false), c(nullptr), reg(_reg) {
	assert(width > 0);
}

void CImmOrRegOrUndefWithWidth::addAsUse(llvm::MachineIRBuilder &Builder, MachineInstrBuilder &MIB) const {
	MachineRegisterInfo &MRI = MIB.getInstr()->getMF()->getRegInfo();
	assert(width > 0);
	if (isUndef) {
		MachineFunction& MF = Builder.getMF();
		MachineInsertPointGuard(Builder, *MF.begin(), MF.begin()->begin());
		Register res = MRI.createVirtualRegister(&HwtFpga::anyregclsRegClass);
		MRI.setType(res, LLT::scalar(width));
		Builder.buildInstr(HwtFpga::HWTFPGA_IMPLICIT_DEF, {res}, {width});
		MIB.addUse(res, RegState::Undef);
	} else if (c) {
		assert(c->getType()->getIntegerBitWidth() == width);
		MIB.addCImm(c);
	} else {
#ifndef NDEBUG
		auto regTy = MRI.getType(reg);
		if (regTy.isValid()) {
			assert(regTy.getScalarSizeInBits() == width);
		}
#endif
		MIB.addUse(reg);
	}
}

MachineInsertPointGuard::MachineInsertPointGuard(
		llvm::MachineIRBuilder &Builder, llvm::MachineInstr *newIP) :
		Builder(Builder), origIPMBB(Builder.getMBB()), origIP(
				Builder.getInsertPt()) {
	Builder.setInsertPt(*newIP->getParent(), newIP);
}

MachineInsertPointGuard::MachineInsertPointGuard(
		llvm::MachineIRBuilder &Builder, llvm::MachineBasicBlock &newIPMBB) :
		Builder(Builder), origIPMBB(Builder.getMBB()), origIP(
				Builder.getInsertPt()) {
	Builder.setInsertPt(newIPMBB, newIPMBB.end());
}

MachineInsertPointGuard::MachineInsertPointGuard(
		llvm::MachineIRBuilder &Builder, llvm::MachineBasicBlock &newIPMBB,
		llvm::MachineBasicBlock::iterator newIP) :
		Builder(Builder), origIPMBB(Builder.getMBB()), origIP(
				Builder.getInsertPt()) {
	Builder.setInsertPt(newIPMBB, newIP);
}

MachineInsertPointGuard::~MachineInsertPointGuard() {
	Builder.setInsertPt(origIPMBB, origIP);
}

size_t hwtFpgaMuxFindValueWidth(const llvm::MachineInstr &MI,
		MachineRegisterInfo &MRI) {
	auto OpIt = MI.operands_begin() + 1; // skip dst
	while (OpIt != MI.operands_end()) {
		const auto &V = *OpIt;
		if (V.isReg()) {
			MachineOperand *VDef = MRI.getOneDef(V.getReg());
			if (!VDef)
				return 0;
			auto &DefMI = *VDef->getParent();
			if (DefMI.getOpcode() != HwtFpga::HWTFPGA_MERGE_VALUES)
				return 0;

			return hwtHls::MERGE_VALUES_getResultWidth(DefMI);
		} else {
			assert(V.isCImm());
			return V.getCImm()->getType()->getIntegerBitWidth();
		}
		++OpIt;
		if (OpIt != MI.operands_end()) {
			++OpIt; // skip condition to get to next value
		}
	}
	return 0;
}

bool RegisterIsDefinedWithinRangeExclusive(const llvm::TargetRegisterInfo * TRI, llvm::Register r,
		llvm::MachineBasicBlock::iterator begin,
		llvm::MachineBasicBlock::iterator end) {
	if (begin == end)
		return false;
	begin++;
	return RegisterIsDefinedWithinRange(TRI, r, begin, end);
}

bool RegisterIsDefinedWithinRange(const llvm::TargetRegisterInfo * TRI, llvm::Register r,
		llvm::MachineBasicBlock::iterator begin,
		llvm::MachineBasicBlock::iterator end) {
	for (auto &I : make_range(begin, end)) {
		if (I.definesRegister(r, TRI))
			return true;
	}
	return false;
}

bool RegisterIsDefinedWithinRange(const llvm::TargetRegisterInfo * TRI, llvm::Register r,
		llvm::MachineBasicBlock::const_iterator begin,
		llvm::MachineBasicBlock::const_iterator end) {
	for (auto &I : make_range(begin, end)) {
		if (I.definesRegister(r, TRI))
			return true;
	}
	return false;
}

bool match_OperandIs1(MachineRegisterInfo &MRI, const MachineOperand &Op) {
	if (Op.isCImm() && Op.getCImm()->getBitWidth() == 1
			&& Op.getCImm()->equalsInt(1)) {
		return true;
	} else if (mi_match(Op.isReg(), MRI, m_AllOnesInt())) {
		return true;
	}
	if (MRI.hasOneDef(Op.getReg())) {
		if (auto VRegVal = getAnyConstantVRegValWithLookThrough(Op.getReg(),
				MRI)) {
			if (VRegVal.has_value() && VRegVal.value().Value == 1) {
				return true;
			}
		}
	}
	return false;
}

bool Register_isRedefinedInLinearBlockSequenceEndToBegin(const llvm::TargetRegisterInfo * TRI, Register reg,
		MachineBasicBlock::iterator begin, llvm::MachineBasicBlock &EndMBB,
		llvm::MachineBasicBlock::iterator EndIp) {
	llvm::MachineBasicBlock *_EndMBB = &EndMBB;
	llvm::SmallPtrSet<MachineBasicBlock*, 32> seenBlocks;
	for (;;) {
		while (EndIp != _EndMBB->begin()) {
			MachineInstr &prevInstr = *--EndIp;
			if (prevInstr == begin)
				return false;

			if (prevInstr.definesRegister(reg, TRI))
				return true;
		}
		assert(_EndMBB->pred_size() == 1);
		_EndMBB = *_EndMBB->pred_begin();
		EndIp = _EndMBB->end();
	}
	return false;
}

void Register_checkOrSetWidth(llvm::MachineRegisterInfo &MRI, llvm::Register R,
		unsigned bitWidth) {
	LLT T = MRI.getType(R);
	if (T.isValid()) {
		assert(T.getSizeInBits() != bitWidth);
	} else {
		MRI.setType(R, LLT::scalar(bitWidth));
	}

}

}
