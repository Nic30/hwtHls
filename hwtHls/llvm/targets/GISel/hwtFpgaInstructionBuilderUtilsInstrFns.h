#pragma once
#include <llvm/CodeGen/MachineOperand.h>
#include <llvm/IR/Constants.h>
#include <llvm/CodeGen/MachineInstrBuilder.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>

namespace hwtHls {

size_t MERGE_VALUES_getResultWidth(llvm::MachineInstr &MI);
size_t MERGE_VALUES_getSrcOperandCount(const llvm::MachineInstr &MI);
llvm::iterator_range<llvm::MachineOperand*> MERGE_VALUES_iter_values(
		llvm::MachineInstr &MI);
// returns Imm operands with width of each value
llvm::iterator_range<llvm::MachineOperand*> MERGE_VALUES_iter_widths(
		llvm::MachineInstr &MI);
llvm::detail::zippy<llvm::detail::zip_first,
		llvm::iterator_range<llvm::MachineOperand*>,
		llvm::iterator_range<llvm::MachineOperand*>> MERGE_VALUES_iter_valuesWidthPairs(
		llvm::MachineInstr &MI);

struct HWTFPGA_EXTRACTOptions {
	size_t srcWidth;
	size_t offset;
	size_t dstWidth;
	static HWTFPGA_EXTRACTOptions get(llvm::MachineInstr &MI);
	bool isMsbGet();
};

// srcWidth == 0 is used for unknown src width, in this case extract is always build
// without asking
CImmOrRegOrUndefWithWidth buildHWTFPGA_EXTRACT(llvm::MachineIRBuilder &Builder,
		llvm::Register src, size_t srcWidth, size_t offset, size_t resWidth);
CImmOrRegOrUndefWithWidth buildHWTFPGA_EXTRACT(llvm::MachineIRBuilder &Builder,
		const llvm::MachineOperand &src, size_t srcWidth, size_t offset,
		size_t resWidth);
llvm::MachineInstrBuilder buildHWTFPGA_EXTRACT(llvm::MachineIRBuilder &Builder,
		llvm::GISelChangeObserver *Observer, llvm::Register DstReg,
		const llvm::MachineOperand &SrcValMO, size_t srcWidth, size_t offset,
		size_t dstWidth);
CImmOrRegOrUndefWithWidth buildHWTFPGA_EXTRACT(llvm::MachineIRBuilder &Builder,
		llvm::GISelChangeObserver *Observer,
		const llvm::MachineOperand &SrcValMO, size_t srcWidth, size_t offset,
		size_t dstWidth);

CImmOrRegOrUndefWithWidth buildHWTFPGA_MERGE_VALUES(
		llvm::MachineIRBuilder &Builder,
		llvm::SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> &ConcatMembers,
		llvm::GISelChangeObserver *Observer = nullptr);
llvm::MachineInstrBuilder buildHWTFPGA_MERGE_VALUES(
		llvm::MachineIRBuilder &Builder, llvm::GISelChangeObserver *Observer,
		llvm::Register DstReg,
		const llvm::SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> &ConcatMembers,
		size_t *_width = nullptr);

llvm::Register buildMsbGet(llvm::MachineIRBuilder &Builder,
				   llvm::GISelChangeObserver *Observer,
				   const llvm::Register x, unsigned bitWidth,
				   std::optional<llvm::Register> dst={});
llvm::Register buildMsbGet(llvm::MachineIRBuilder &Builder,
						   llvm::GISelChangeObserver *Observer,
						   CImmOrReg x, unsigned bitWidth,
						   std::optional<llvm::Register> dst={});
}
