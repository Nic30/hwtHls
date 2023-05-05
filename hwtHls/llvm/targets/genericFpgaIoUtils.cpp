#include "genericFpgaIoUtils.h"
#include "genericFpgaInstrInfo.h"
#include "bitMathUtils.h"

#include <llvm/IR/Constants.h>
#include <llvm/IR/Metadata.h>

using namespace llvm;

namespace hwtHls {

MachineInstr* getLoadOrStoreFromAddrOperand(MachineRegisterInfo &MRI,
		MachineOperand &addrOp) {
	if (!addrOp.isReg())
		return nullptr;
	MachineInstr *MI = addrOp.getParent();
	switch (MI->getOpcode()) {
	case TargetOpcode::G_LOAD:
	case TargetOpcode::G_STORE:
	case GenericFpga::GENFPGA_CLOAD:
	case GenericFpga::GENFPGA_CSTORE:
		return MI;
	}
	for (auto u : MRI.use_operands(addrOp.getReg())) {
		auto res = getLoadOrStoreFromAddrOperand(MRI, u);
		if (res != nullptr)
			return res;
	}
	return nullptr;
}

std::pair<Type*, size_t> getLoadOrStoreElementType(MachineRegisterInfo &MRI,
		MachineInstr &MI) {
	switch (MI.getOpcode()) {
	case TargetOpcode::G_LOAD:
	case TargetOpcode::G_STORE:
	case GenericFpga::GENFPGA_CLOAD:
	case GenericFpga::GENFPGA_CSTORE:
		//MachineOperand &addrMO = MI.getOperand(1);
		for (auto MO : MI.memoperands()) {
			auto t = MO->getValue()->getType();
			if (!t->isPointerTy()) {
				llvm_unreachable(
						"Memory operand should have be always of pointer type");
			}
			auto addrSpace = t->getPointerAddressSpace();
			if (addrSpace == 0) {
				auto *addrDef = MRI.getVRegDef(MI.getOperand(1).getReg());
				if (!addrDef) {
					llvm_unreachable(
							"Address for instruction is never defined");
				}
				auto addrDefOpc = addrDef->getOpcode();
				while (addrDefOpc == TargetOpcode::G_PTR_ADD) {
					addrDef = MRI.getVRegDef(addrDef->getOperand(1).getReg());
					addrDefOpc = addrDef->getOpcode();
				}
				if (addrDefOpc != TargetOpcode::G_GLOBAL_VALUE) {
					errs() << *addrDef << "address defined in:\n" << *addrDef;
					llvm_unreachable(
							"In address space 0 there should be only G_GLOBAL_VALUE");
				}
				return getGlobalValueElementTypeAndAddressWidth(*addrDef);
			}
			Function &F = MI.getParent()->getParent()->getFunction();
			if (addrSpace > F.arg_size()) {
				llvm_unreachable(
						"The address space should be index in function arguments");
			}
			auto *_param_addr_width = F.getMetadata("hwtHls.param_addr_width");
			if (!_param_addr_width)
				llvm_unreachable(
						"Function is missing hwtHls.param_addr_width metadata");
			MDTuple *argAddrWidths = dyn_cast_or_null<MDTuple>(
					_param_addr_width->getOperand(1));
			auto &awOp = argAddrWidths->getOperand(addrSpace - 1);
			size_t aw =
					mdconst::extract<ConstantInt>(awOp.get())->getSExtValue();
			auto resT = IntegerType::getIntNTy(F.getContext(),
					MO->getSizeInBits());
			return {resT, aw};
		}
	}
	llvm_unreachable(
			"Only instructions with previous opcode should be store in MI and it should have memory operand");
}

std::optional<std::pair<Type*, size_t>> getPointerElementTypeFromAnyLoadOrStore(
		MachineRegisterInfo &MRI, MachineOperand &addrOp) {
	auto *MI = getLoadOrStoreFromAddrOperand(MRI, addrOp);
	if (!MI) {
		return std::nullopt;
	}
	return getLoadOrStoreElementType(MRI, *MI);
}

std::pair<Type*, size_t> getGlobalValueElementTypeAndAddressWidth(
		llvm::MachineInstr &MI) {
	auto vT = MI.getOperand(1).getGlobal()->getValueType();
	if (!vT->isArrayTy()) {
		llvm_unreachable("For global value only ArrayTy is implemented");
	}
	size_t SizeInBits = log2ceil(vT->getArrayNumElements());
	return {vT->getArrayElementType(), SizeInBits};
}
}
