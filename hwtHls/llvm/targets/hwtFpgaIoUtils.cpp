#include <hwtHls/llvm/targets/hwtFpgaIoUtils.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/bitMathUtils.h>

#include <llvm/IR/Constants.h>
#include <llvm/IR/Metadata.h>

using namespace llvm;

namespace hwtHls {

MachineInstr* getMirLoadOrStoreFromAddrOperand(MachineRegisterInfo &MRI,
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
		auto res = getMirLoadOrStoreFromAddrOperand(MRI, u);
		if (res != nullptr)
			return res;
	}
	return nullptr;
}
llvm::MachineInstr* getMirReferencedGlobalValue(MachineRegisterInfo &MRI,
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
			if (auto addrDef = getMirReferencedGlobalValue(MRI, seen,
					nextAddrDefMI)) {
				return addrDef;
			}
		}
		return nullptr;
	} else {
		return AddrDefMI;
	}
}

IoElementMeta getMirLoadOrStoreElementType(
		MachineRegisterInfo &MRI, MachineInstr &MI) {
	switch (MI.getOpcode()) {
	case TargetOpcode::G_LOAD:
	case TargetOpcode::G_STORE:
	case HwtFpga::HWTFPGA_CLOAD:
	case HwtFpga::HWTFPGA_CSTORE: {
		std::optional<size_t> expectedResWidth;
		switch (MI.getOpcode()) {
		case HwtFpga::HWTFPGA_CLOAD:
		case HwtFpga::HWTFPGA_CSTORE:
			expectedResWidth = MI.getOperand(3).getImm();
			break;
		default:
			break;
		}
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
				addrDef = getMirReferencedGlobalValue(MRI, seen, addrDef);
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
				auto res = getMirGlobalValueElementTypeAndAddressWidth(*addrDef);
				return {res.first, res.second, addrDef, {}};
			}
			Function &F = MI.getParent()->getParent()->getFunction();
			auto hwtHlsIO = HwtHlsIoMetadata_get(F, addrSpace - 1);
			IntegerType *resT = nullptr;
			size_t addressWidth = 0;
			if (hwtHlsIO.has_value()) {
				addressWidth = hwtHlsIO.value().addrWidth;
				size_t bitwidth = std::max(hwtHlsIO.value().readWordWidth,
									       hwtHlsIO.value().writeWordWidth);
				auto vec = hwtHlsIO.value().ioVectorization;
				if (vec.has_value()) {
					assert(vec.value().laneCnt.has_value() && "At this point the number of lanes should be already resolved");
					if (vec.value().laneCnt.value() != 1) {
						bitwidth = (bitwidth + 1) * vec.value().laneCnt.value(); // +1 for segment enable
					}
				}		
				resT = IntegerType::getIntNTy(F.getContext(), bitwidth);
				if (expectedResWidth.has_value())
					assert(MO->getSizeInBits() == expectedResWidth);
			} else {
				if (expectedResWidth.has_value()) {
					resT = IntegerType::get(F.getContext(),
							expectedResWidth.value());
				}
			}
			MachineInstr *ioArgDefiningInstr = nullptr;
			for (MachineInstr &FirstBBMI : *MI.getMF()->begin()) {
				switch (FirstBBMI.getOpcode()) {
				case HwtFpga::HWTFPGA_ARG_GET: {
					auto argType =
							F.getArg(FirstBBMI.getOperand(1).getImm())->getType();
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
			return {resT, addressWidth, ioArgDefiningInstr, hwtHlsIO};
		}
		break;
	}
	default:
		break;
	}
	llvm_unreachable(
			"Only instructions with previous opcodes should be store in MI and it should have memory operand");
}

std::optional<IoElementMeta> getMirPointerElementTypeFromAnyLoadOrStore(
		MachineRegisterInfo &MRI, MachineOperand &addrOp) {
	auto *MI = getMirLoadOrStoreFromAddrOperand(MRI, addrOp);
	if (!MI) {
		return std::nullopt;
	}
	return getMirLoadOrStoreElementType(MRI, *MI);
}

std::pair<Type*, size_t> getMirGlobalValueElementTypeAndAddressWidth(
		llvm::MachineInstr &MI) {
	auto vT = MI.getOperand(1).getGlobal()->getValueType();
	if (!vT->isArrayTy()) {
		llvm_unreachable("For global value only ArrayTy is implemented");
	}
	size_t SizeInBits = log2ceil(vT->getArrayNumElements());
	return {vT->getArrayElementType(), SizeInBits};
}

}
