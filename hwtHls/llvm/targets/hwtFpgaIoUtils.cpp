#include <hwtHls/llvm/targets/hwtFpgaIoUtils.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/bitMathUtils.h>

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
	case HwtFpga::HWTFPGA_CLOAD:
	case HwtFpga::HWTFPGA_CSTORE:
		return MI;
	}
	for (auto u : MRI.use_operands(addrOp.getReg())) {
		auto res = getLoadOrStoreFromAddrOperand(MRI, u);
		if (res != nullptr)
			return res;
	}
	return nullptr;
}
llvm::MachineInstr* getReferencedGlobalValue(MachineRegisterInfo &MRI,
		llvm::DenseSet<MachineInstr*> &seen, llvm::MachineInstr *AddrDefMI) {
	auto addrDefOpc = AddrDefMI->getOpcode();
	while (addrDefOpc == TargetOpcode::G_PTR_ADD) {
		seen.insert(AddrDefMI);
		AddrDefMI = MRI.getVRegDef(AddrDefMI->getOperand(1).getReg());
		addrDefOpc = AddrDefMI->getOpcode();
	}
	if (AddrDefMI->getOpcode() == TargetOpcode::G_PHI) {
		seen.insert(AddrDefMI);
		for (unsigned OpI = 1; OpI < AddrDefMI->getNumExplicitOperands(); OpI +=
				2) {
			auto MO = AddrDefMI->getOperand(OpI);
			assert(MO.isReg());
			auto nextAddrDefMI = MRI.getVRegDef(MO.getReg());
			if (seen.contains(nextAddrDefMI))
				continue;
			if (auto addrDef = getReferencedGlobalValue(MRI, seen,
					nextAddrDefMI)) {
				return addrDef;
			}
		}
		return nullptr;
	} else {
		return AddrDefMI;
	}
}
std::tuple<Type*, size_t, MachineInstr*> getLoadOrStoreElementType(
		MachineRegisterInfo &MRI, MachineInstr &MI) {
	switch (MI.getOpcode()) {
	case TargetOpcode::G_LOAD:
	case TargetOpcode::G_STORE:
	case HwtFpga::HWTFPGA_CLOAD:
	case HwtFpga::HWTFPGA_CSTORE:
		//MachineOperand &addrMO = MI.getOperand(1);
		for (auto MO : MI.memoperands()) {
			auto t = MO->getValue()->getType();
			if (!t->isPointerTy()) {
				llvm_unreachable(
						"Memory operand should have be always of pointer type");
			}
			auto addrSpace = t->getPointerAddressSpace();
			if (addrSpace == 0) {
				// case of G_GLOBAL_VALUE/HWTFPGA_GLOBAL_VALUE
				auto *addrDef = MRI.getVRegDef(MI.getOperand(1).getReg());
				if (!addrDef) {
					llvm_unreachable(
							"Address for instruction is never defined");
				}
				llvm::DenseSet<MachineInstr*> seen;
				addrDef = getReferencedGlobalValue(MRI, seen, addrDef);
				if (!addrDef) {
					llvm_unreachable(
							"Unable to find memory for GLOBAL_VALUE read or store");
				}
				auto addrDefOpc = addrDef->getOpcode();
				if (addrDefOpc != TargetOpcode::G_GLOBAL_VALUE
						&& addrDefOpc != HwtFpga::HWTFPGA_GLOBAL_VALUE) {
					errs() << *addrDef << "address defined in:\n" << *addrDef;
					llvm_unreachable(
							"In address space 0 there should be only G_GLOBAL_VALUE or HWTFPGA_GLOBAL_VALUE");
				}
				auto res = getGlobalValueElementTypeAndAddressWidth(*addrDef);
				return {res.first, res.second, addrDef};
			}
			Function &F = MI.getParent()->getParent()->getFunction();
			IntegerType *resT = nullptr;
			size_t addressWidth = 0;
			auto *_param_addr_width = F.getMetadata("hwtHls.param_addr_width");
			if (addrSpace > F.arg_size() || !_param_addr_width) {
			} else {
				MDTuple *argAddrWidths = dyn_cast_or_null<MDTuple>(
						_param_addr_width->getOperand(1));
				auto &awOp = argAddrWidths->getOperand(addrSpace - 1);
				addressWidth =
						mdconst::extract<ConstantInt>(awOp.get())->getSExtValue();
				resT = IntegerType::getIntNTy(F.getContext(),
						MO->getSizeInBits());
			}
			MachineInstr *ioArgDefiningInstr = nullptr;
			for (MachineInstr &FirstBBMI : *MI.getMF()->begin()) {
				switch (FirstBBMI.getOpcode()) {
				case HwtFpga::HWTFPGA_ARG_GET: {
					auto argType = F.getArg(FirstBBMI.getOperand(1).getImm())->getType();
					assert(argType->isPointerTy());
					if (argType->getPointerAddressSpace() == addrSpace) {
						ioArgDefiningInstr = &FirstBBMI;
						break;
					}
					continue;
				}
				default:
					break;
				}
				break;
			}
			if (!ioArgDefiningInstr) {
				errs() << MI << "\n";
				llvm_unreachable(
						"Can not find associated HWTFPGA_ARG_GET in the first block");
			}
			return {resT, addressWidth, ioArgDefiningInstr};
		}
	}
	llvm_unreachable(
			"Only instructions with previous opcode should be store in MI and it should have memory operand");
}

std::optional<std::tuple<llvm::Type*, size_t, llvm::MachineInstr*>> getPointerElementTypeFromAnyLoadOrStore(
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
