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
	// :param Builder: builder used to build IMPLICIT_DEF for undefs at the beginning of the entry block
	void addAsUse(llvm::MachineIRBuilder &Builder,
			llvm::MachineInstrBuilder &MIB) const;
};


/*
 * Record about MUX value operands used to discover which bits are directly driven by
 * condition operand or its negation.
 * Such a bit can be removed from MUX as its value is exactly the cond operand value.
 * */
class MuxDirectlyCondDrivenBits {
public:
	struct MaskAndNegationMask {
		llvm::APInt val;
		llvm::APInt isNegated;
	};
	llvm::SmallVector<MaskAndNegationMask, 4> valIsSel; // for each cond of the mux
};

struct DefiningRegisterInfo {
	size_t bitOffset; // bit index where this part starts in result
	size_t bitCnt; // bit length of this segment of bits used from register
	llvm::Register reg; // defining src register
	size_t regOffset; // how many bits to skip from reg beginning when resolving value of this
	size_t regWidth; // number of the source register
};

/*
 * Record about MUX value operands used to discover which bits have some known value in all cases of the MUX
 * */
class MuxReducibleValuesInfo {
public:
	llvm::APInt constBitMask; // mask which marks which bits are constant in output
	llvm::APInt constVal;  // value for bits defined by constBitMask
	llvm::APInt regBitMask; // mask which marks which bits are defined by a single reg in output
	std::list<DefiningRegisterInfo> regVal; // tuples used to store information about bits defined by some reg
	llvm::APInt valDefined; // mask which marks which bits are defined to be const or reg

	// :note: constBitMask and regBitMask have never 1 on same position, both have 0 in bits where valDefined has 0
	MuxReducibleValuesInfo() :
			MuxReducibleValuesInfo(1) {
	}
	MuxReducibleValuesInfo(size_t width) {
		constBitMask = llvm::APInt::getZero(width);
		constVal = llvm::APInt::getZero(width);
		regBitMask = llvm::APInt::getZero(width);
		valDefined = llvm::APInt::getZero(width);
	}

	void _erraseMatchingRegBit(size_t resBitI);
	std::list<DefiningRegisterInfo>::iterator _getRecordForRegisterBitOrAfter(
			size_t resBitI, std::list<DefiningRegisterInfo>::iterator begin);
	// if this bit is continuation of previous record just extend
	// else insert new element to regVal
	// :param regValAfterThis: used to skip definitions in regVal to searching for mergable element
	void _defineBitAsRegBit(
			std::list<DefiningRegisterInfo>::iterator regValAfterThis,
			size_t resBitI, size_t bitI, llvm::Register reg, size_t regWidth);
	// :param recursionLimit: decreased on each HWTFPGA_MERGE_VALUES, if reaches 0 another HWTFPGA_MERGE_VALUES is not probed and
	// processValueOperand         instead its dst register is used as it is
	void loadKnonwBitsFromValueOperand(const llvm::MachineOperand &MO,
			size_t offset, size_t MOWidth, llvm::MachineRegisterInfo &MRI,
			int recursionLimit);
};

llvm::iterator_range<llvm::MachineOperand*> MERGE_VALUES_iter_values(
		llvm::MachineInstr &MI);

// returns Imm operands with width of each value
llvm::iterator_range<llvm::MachineOperand*> MERGE_VALUES_iter_widths(
		llvm::MachineInstr &MI);

// srcWidth == 0 is used for unknown src width, in this case extract is always build
// without asking
CImmOrRegOrUndefWithWidth buildHWTFPGA_EXTRACT(llvm::MachineIRBuilder &Builder,
		llvm::Register src, size_t srcWidth, size_t offset, size_t resWidth);
CImmOrRegOrUndefWithWidth buildHWTFPGA_EXTRACT(llvm::MachineIRBuilder &Builder,
		const llvm::MachineOperand &src, size_t srcWidth, size_t offset,
		size_t resWidth);
CImmOrRegOrUndefWithWidth buildHWTFPGA_MERGE_VALUES(
		llvm::MachineIRBuilder &Builder,
		llvm::SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> &ConcatMembers);
llvm::Register buildMsbGet(llvm::MachineIRBuilder &Builder,
		llvm::GISelChangeObserver &Observer, CImmOrReg x, unsigned bitWidth,
		std::optional<llvm::Register> dst);

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

}
