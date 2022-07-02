#include "genericFpgaCombinerHelper.h"
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include "../genericFpgaInstrInfo.h"

namespace llvm {

bool GenFpgaCombinerHelper::matchAllOnesConstantOp(
		const llvm::MachineOperand &MOP) {
	if (!MOP.isReg())
		return false;
	auto *MI = MRI.getVRegDef(MOP.getReg());
	auto MaybeCst = isConstantOrConstantSplatVector(*MI, MRI);
	return MaybeCst.hasValue() && MaybeCst->isAllOnes();
}
bool GenFpgaCombinerHelper::matchOperandIsAllOnes(llvm::MachineInstr &MI,
		unsigned OpIdx) {
	return matchAllOnesConstantOp(MI.getOperand(OpIdx))
			&& canReplaceReg(MI.getOperand(0).getReg(),
					MI.getOperand(OpIdx).getReg(), MRI);
}
bool GenFpgaCombinerHelper::rewriteXorToNot(llvm::MachineInstr &MI) {
	Builder.setInstrAndDebugLoc(MI);
	Builder.buildInstr(GenericFpga::GENFPGA_NOT, { MI.getOperand(0).getReg() },
			{ MI.getOperand(1).getReg() }, MI.getFlags());
	MI.eraseFromParent();
	return true;
}

bool GenFpgaCombinerHelper::matchIsExtractOnMergeValues(
		llvm::MachineInstr &MI) {
	if (auto *src = MRI.getOneDef(MI.getOperand(1).getReg())) {
		return src->getParent()->getOpcode()
				== GenericFpga::GENFPGA_MERGE_VALUES;
	}
	return false;
}

inline bool collectConcatMembersAsItIs(llvm::MachineOperand &MIOp,
		std::vector<GenFpgaCombinerHelper::ConcatMember> &members,
		uint64_t mainOffset, uint64_t mainWidth, uint64_t &currentOffset,
		uint64_t offsetOfIRes, uint64_t widthOfIRes) {
	uint64_t mainEnd = mainOffset + mainWidth;
	// take slice from this instruction as it is
	uint64_t bitsToTake = std::min(widthOfIRes, mainEnd - currentOffset);
	currentOffset += widthOfIRes;
	if (currentOffset < mainOffset) {
		// skip prefix
		return true;
	} else {
		members.push_back(GenFpgaCombinerHelper::ConcatMember { MIOp,
				offsetOfIRes, widthOfIRes, bitsToTake });
		return false;
	}
}
/*
 * Recursively collect members of concatenations, looks trought GENFPGA_EXTRACT and GENFPGA_MERGE_VALUES instructions
 *
 * :param MIOp: an operand from where to collect concat embers
 * :param members: output vector of records containing the operand and the information about which bits are selected
 * :param mainOffset: offsets (number of bits) where selected value from whole value
 * :param mainWidth: number of bits to select in total
 * :param currentOffset: a number of bits already collected
 * :param offsetOfIRes: offsets (number of bits) where selected value from this operand starts
 * :param widthOfIRes: a number of bits to select from this operand
 * */
bool GenFpgaCombinerHelper::collectConcatMembers(llvm::MachineOperand &MIOp,
		std::vector<ConcatMember> &members, uint64_t mainOffset,
		uint64_t mainWidth, uint64_t &currentOffset, uint64_t offsetOfIRes,
		uint64_t widthOfIRes) {
	uint64_t mainEnd = mainOffset + mainWidth;
	MachineInstr &MI = *MIOp.getParent();
	switch (MI.getOpcode()) {
	case GenericFpga::GENFPGA_MERGE_VALUES: {
		//  $dst $src{N}, $width{N} (lowest bits first)
		uint64_t srcCnt = (MI.getNumOperands() - 1) / 2;
		bool didReduce = false;
		for (unsigned i = 0; i < srcCnt; ++i) {
			uint64_t thisMemberOffset = 0;
			uint64_t width = MI.getOperand(1 + srcCnt + i).getImm();
			if (offsetOfIRes) {
				if (offsetOfIRes > width) {
					thisMemberOffset = width;
					offsetOfIRes -= width;
					width = 0;
				} else {
					thisMemberOffset = offsetOfIRes;
					width -= offsetOfIRes;
					offsetOfIRes = 0;
				}
			}
			if (currentOffset + width < mainOffset || width == 0) {
				didReduce = true;
				currentOffset += width;
				// skipping the unused prefix
			} else {
				auto &op = MI.getOperand(1 + i);
				MachineOperand *src = nullptr;
				if (op.isReg())
					src = MRI.getOneDef(op.getReg());
				if (src) {
					// can look trough
					didReduce |= collectConcatMembers(*src, members, mainOffset,
							mainWidth, currentOffset, thisMemberOffset, width);
				} else {
					// must take as it is
					collectConcatMembersAsItIs(op, members, mainOffset,
							mainWidth, currentOffset, thisMemberOffset, width);
				}
			}
			if (currentOffset >= mainEnd) {
				// we do not care about successors because parent EXTRACT does not select them
				didReduce |= i != srcCnt;
				break;
			}
		}
		return didReduce;
	}
	case GenericFpga::GENFPGA_EXTRACT: {
		// $dst $src $offset $dstWidth
		uint64_t subSliceOffset = MI.getOperand(2).getImm();
		uint64_t subSliceWidth = MI.getOperand(3).getImm();
		subSliceOffset += offsetOfIRes;
		assert(widthOfIRes == subSliceWidth);
		//subSliceWidth = std::min(std::min(subSliceWidth - offsetOfIRes,
		//		mainEnd - currentOffset), );
		if (auto *src = MRI.getOneDef(MI.getOperand(1).getReg())) {
			// look trough the source operand of this extract instruction
			bool didReduce = collectConcatMembers(*src, members, mainOffset,
					mainWidth, currentOffset, subSliceOffset, subSliceWidth);
			assert(members.size());
			const auto &lastAdded = members.back();
			didReduce |= &lastAdded.op != src;
			return didReduce;
		}

		break;
	}
	}
	return collectConcatMembersAsItIs(MIOp, members, mainOffset, mainWidth,
			currentOffset, offsetOfIRes, widthOfIRes);
}

bool GenFpgaCombinerHelper::rewriteExtractOnMergeValues(
		llvm::MachineInstr &MI) {
	// MI.operands() == $dst $src $offset $dstWidth
	std::vector<ConcatMember> concatMembers;
	//uint64_t mainOffset = MI.getOperand(2).getImm();
	uint64_t mainWidth = MI.getOperand(3).getImm();
	uint64_t currentOffset = 0;
	bool didReduce = collectConcatMembers(MI.getOperand(0), concatMembers, 0,
			mainWidth, currentOffset, 0, mainWidth);
	if (didReduce) {
		assert(
				concatMembers.size()
						&& "There must be something which EXTRACT selects");
		if (concatMembers.size() == 1) {
			auto &src = concatMembers.back();
			// we may be able to use item directly of we may build an EXTRACT
			if (src.offsetOfUse == 0 && src.width == src.widthOfUse) {
				MRI.replaceRegWith(MI.getOperand(0).getReg(), src.op.getReg()); // [fixme] the src.op can be imm or cost
				MI.eraseFromParent();
				return true;
			} else {
				Builder.setInstrAndDebugLoc(MI);
				auto MIB = Builder.buildInstr(GenericFpga::GENFPGA_EXTRACT);
				// $dst $src $offset $dstWidth
				MIB.addDef(MI.getOperand(0).getReg(), MI.getFlags());
				MIB.add(src.op);
				MIB.addImm(src.offsetOfUse);
				MIB.addImm(src.widthOfUse);
				MI.eraseFromParent();
				return true;
			}
		} else {
			// we must build GENFPGA_MERGE_VALUE for members
			Builder.setInstrAndDebugLoc(MI);
			auto currentInsertionPoint = Builder.getInsertPt();
			auto MIB = Builder.buildInstr(GenericFpga::GENFPGA_MERGE_VALUES);
			MIB.addDef(MI.getOperand(0).getReg(), MI.getFlags());

			for (auto &src : concatMembers) {
				if (src.offsetOfUse == 0 && src.width == src.widthOfUse) {
					// use member directly
					MIB.add(src.op);
				} else {
					// slice the member using GENFPGA_EXTRACT
					Builder.setInstrAndDebugLoc(MI);
					Builder.setInsertPt(*MI.getParent(),
							--currentInsertionPoint);
					auto memberMIB = Builder.buildInstr(
							GenericFpga::GENFPGA_EXTRACT);
					// $dst $src $offset $dstWidth
					Register memberReg = MRI.createVirtualRegister(
							&GenericFpga::AnyRegClsRegClass);
					memberMIB.addDef(memberReg, MI.getFlags());
					memberMIB.add(src.op);
					memberMIB.addImm(src.offsetOfUse);
					memberMIB.addImm(src.widthOfUse);
					MIB.addReg(memberReg);
				}
			}
			for (auto &src : concatMembers) {
				MIB.addImm(src.widthOfUse);
			}
			MI.eraseFromParent();
			return true;
		}
	}
	return false;
}
}