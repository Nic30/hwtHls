#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelValueTracking.h>
#include <llvm/ADT/STLExtras.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/machineInstrUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>
#include <hwtHls/llvm/bitMath.h>

namespace llvm {

MachineInstr* tryGetDominatingDef(MachineRegisterInfo &MRI, const TargetRegisterInfo *TRI,
		MachineInstr &UserMI, Register reg) {
	auto *oneDef = MRI.getOneDef(reg);
	if (oneDef) {
		return oneDef->getParent();
	} else {
		auto *parentMB = UserMI.getParent();
		for (auto &def : MRI.def_operands(reg)) {
			MachineInstr *defMI = def.getParent();
			if (&UserMI != defMI && defMI->getParent() == parentMB) {
				// check if def is predecessor of UserMI
				for (auto MI = defMI->getIterator(); MI != parentMB->end();
						++MI) {
					if (&*MI == &UserMI)
						return defMI; // the register is not redefined between defMI and UserMI
					if (MI->definesRegister(reg, TRI))
						defMI = &*MI; // store last def
				}
				// this def was after useMi,
				// continue iterating defs because there may be some before useMI
			}
		}
		// there was no def of this regs in this block before UseMI
		return nullptr;
	}
}

// check if operandReg is defined by sext/zext in a form of HWTFPGA_MERGE_VALUES, HWTFPGA_EXTRACT
bool MatchMulHLOperand_matchReg(MachineRegisterInfo &MRI, const TargetRegisterInfo *TRI, MachineInstr &MI,
		Register operandReg, MatchMulHLOperand &opMatch) {
	auto *defMI = tryGetDominatingDef(MRI, TRI, MI, operandReg);
	if (!defMI || defMI->getOpcode() != HwtFpga::HWTFPGA_MERGE_VALUES)
		return false;
	opMatch.def = defMI;
	opMatch.width = hwtHls::MERGE_VALUES_getResultWidth(*defMI);
	if (opMatch.width % 2 != 0)
		return false; // can not be extended to double width
	bool hiBitsAreMsb = true;
	bool hiBitsAre0 = true;
	bool hiBitsAre1 = true;
	size_t offset = 0;
	size_t prefixBeginIndex = opMatch.width / 2;
	std::optional<Register> knownMsbReg;
	// [todo] reverse iteration, first detect prefix then collect ramaining parts to support any prefix len
	for (const auto& [partVal, _partWidth] : hwtHls::MERGE_VALUES_iter_valuesWidthPairs(
			*defMI)) {
		size_t partWidth = _partWidth.getImm();
		// iterating lower bits first
		if (offset < prefixBeginIndex) {
			// collect parts of half width operands
			size_t bitsUntilPrefixBegin = prefixBeginIndex - offset;
			if (bitsUntilPrefixBegin <= partWidth) {
				if (partVal.isReg()) {
					Register r = partVal.getReg();
					opMatch.opParts.push_back(
							hwtHls::CImmOrRegOrUndefWithWidth(partWidth, r));
					if (bitsUntilPrefixBegin == partWidth)
						hiBitsAre1 = false; // can not have 1 prefix because msb bit is reg (it could still have msb prefix (sext) or 0 prefix (zext))
				} else if (partVal.isCImm()) {
					auto *c = partVal.getCImm();
					opMatch.opParts.push_back(
							hwtHls::CImmOrRegOrUndefWithWidth(c));
					if (bitsUntilPrefixBegin == partWidth) {
						APInt cVal = c->getValue();
						auto msbBit = cVal.extractBitsAsZExtValue(1,
								cVal.getBitWidth() - 1);
						hiBitsAre0 = msbBit == 0;
						hiBitsAre1 = msbBit == 1;
						hiBitsAreMsb = false;
					}
				} else {
					llvm_unreachable(
							"HwtFpgaCombinerHelper::MatchMulHLOperand_matchReg expects HWTFPGA_MUL HWTFPGA_MERGE_VALUES operands to be reg/cimm");
				}

			} else {
				// the boundary part does not have to exactly end in half, but it still can be the case with all 1 or 0
				if (partVal.isCImm()) {
					const ConstantInt *c = partVal.getCImm();
					APInt cVal = c->getValue();
					APInt cValLow = cVal.extractBits(bitsUntilPrefixBegin, 0);
					APInt cValHigh = cVal.extractBits(
							partWidth - bitsUntilPrefixBegin,
							bitsUntilPrefixBegin);
					if (cValHigh.isAllOnes()) {
						auto msbBit = cVal.extractBitsAsZExtValue(1,
								bitsUntilPrefixBegin - 1);
						if (!msbBit) {
							return false; // can not be sext
						}
						hiBitsAreMsb = false;
						hiBitsAre0 = false;
						hiBitsAre1 = true;
					} else if (cValHigh.isZero()) {
						hiBitsAreMsb = false;
						hiBitsAre0 = true;
						hiBitsAre1 = false;
					}
				} else {
					// if this is a reg it is assumed that each bit is unique and thus
					// msb bit of top bits of operand can not be replaceted in it
					return false;
				}
			}

		} else {
			// resolve if high bits of operand are all 1, 0 or msb
			if (partVal.isReg()) {
				if (!hiBitsAreMsb)
					return false;
				// this can be only sext with copy of msb of operand
				Register r = partVal.getReg();
				if (knownMsbReg.has_value()) {
					if (r != knownMsbReg.value())
						return false; // there is something else not just MSB in prefix which should be sext
				} else {
					assert(
							!opMatch.opParts.empty()
									&& "should not be empty as this should be in second half");
					const auto &topPart = opMatch.opParts.back();
					if (!topPart.isReg())
						return false; // can not be sext by msb if operand is not reg

					auto *rDefMI = tryGetDominatingDef(MRI, TRI, *defMI, r);
					if (!rDefMI
							|| rDefMI->getOpcode() != HwtFpga::HWTFPGA_EXTRACT)
						return false;

					auto rDefMISrc = rDefMI->getOperand(1);
					auto extractOpts = hwtHls::HWTFPGA_EXTRACTOptions::get(
							*rDefMI);
					if (!rDefMISrc.isReg()) {
						// :note: const HWTFPGA_EXTRACT should be optimized out
						return false; // can not be sext by msb if the prefix bit is not a reg and msb is
					}
					if (extractOpts.dstWidth != 1)
						return false; // msb is just 1 bit

					// it may still be that case that this is msb of operand, but the operand itself may be a slice
					assert(opMatch.opParts.back().isReg());
					auto *opTopBitsDefMI = tryGetDominatingDef(MRI, TRI, *defMI,
							opMatch.opParts.back().reg);
					if (!opTopBitsDefMI
							|| opTopBitsDefMI->getOpcode()
									!= HwtFpga::HWTFPGA_EXTRACT)
						return false;
					auto opTopBitsDefMISrc = opTopBitsDefMI->getOperand(1);
					auto topTopBitsExtractOpts =
							hwtHls::HWTFPGA_EXTRACTOptions::get(
									*opTopBitsDefMI);
					if (!opTopBitsDefMISrc.isReg()) {
						// :note: const HWTFPGA_EXTRACT should be optimized out
						// can not be sext by msb if the msb bit is not a reg and prefix bit is
						return false;
					}
					if (opTopBitsDefMISrc.getReg()
							!= opTopBitsDefMISrc.getReg())
						return false; // prefix bit must be msb of operand, opTopBitsDefMISrc top bit
					if (topTopBitsExtractOpts.offset
							+ topTopBitsExtractOpts.dstWidth - 1
							!= extractOpts.offset)
						return false; // prefix bit must be msb of topTopBits from operand
					knownMsbReg = r;
				}

				hiBitsAre0 = false;
				hiBitsAre1 = false;
			} else if (partVal.isCImm()) {
				APInt c = partVal.getCImm()->getValue();
				hiBitsAreMsb = false;
				hiBitsAre0 &= c.isZero();
				hiBitsAre1 &= c.isAllOnes();
			} else {
				llvm_unreachable(
						"HwtFpgaCombinerHelper::matchMulHL expects HWTFPGA_MUL HWTFPGA_MERGE_VALUES operands to be reg/cimm");
			}

			if (!hiBitsAreMsb && !hiBitsAre0 && !hiBitsAre1)
				return false;
		}
		offset += partWidth;
	}
	assert(hiBitsAreMsb || hiBitsAre0 || hiBitsAre1);
	opMatch.isSigned = hiBitsAreMsb || hiBitsAre1;
	return true;
}

bool HwtFpgaCombinerHelper::matchMulHL(llvm::MachineInstr &MI,
		MatchMulHL &matchinfo) {
	matchinfo.clear();
	for (unsigned i = 0; i < 2; i++) {
		// check if operand is sext/zext to double width
		const auto &op = MI.getOperand(1 + i);
		MatchMulHLOperand &opMatch = matchinfo.ops[i];
		if (op.isCImm()) {
			auto *c = op.getCImm();
			opMatch.width = c->getBitWidth();
			if (opMatch.width % 2 != 0)
				return false; // can not be extended to double width
			auto hiBits = c->getValue().extractBits(opMatch.width / 2,
					opMatch.width / 2);
			opMatch.isSigned = hiBits.isAllOnes();
			if (!opMatch.isSigned && !hiBits.isZero())
				return false; // the constant is not zero/sign extended to double width

		} else if (op.isReg()) {
			if (!MatchMulHLOperand_matchReg(MRI, TRI, MI, op.getReg(), opMatch))
				return false;
		} else {
			llvm_unreachable(
					"HwtFpgaCombinerHelper::matchMulHL expects HWTFPGA_MUL operands to be reg/cimm");
		}
	}
	size_t lhsWidth = 0;
	size_t rhsWidth = 0;
	for (unsigned i = 0; i < 2; i++) {
		MatchMulHLOperand &opMatch = matchinfo.ops[i];
		for (auto &v : opMatch.opParts) {
			switch (i) {
			case 0:
				lhsWidth += v.width;
				break;
			case 1:
				rhsWidth += v.width;
				break;
			default:
				llvm_unreachable(
						"HwtFpgaCombinerHelper::matchMulHL expects HWTFPGA_MUL operands to just dst, src0, src1");
			}
		}
	}
	size_t resWidth = matchinfo.ops[0].width;
	if (lhsWidth == resWidth && rhsWidth == resWidth) {
		return false; // width of operands can not be reduced, thus this stays HWTFPGA_MUL
	}

	return true;
}

void HwtFpgaCombinerHelper::rewriteMulToMulHL(llvm::MachineInstr &MI,
		const MatchMulHL &matchinfo) {
	// prepare new operands
	std::array<hwtHls::CImmOrRegOrUndefWithWidth, 2> newOps = { 1ul, 1ul };
	for (unsigned i = 0; i < 2; i++) {
		const MatchMulHLOperand &opMatch = matchinfo.ops[i];
		assert(!opMatch.opParts.empty());
		if (opMatch.opParts.size() == 1) {
			newOps[i] = opMatch.opParts[0];
		} else {
			// need to create MERGE_VALUES before original def of the operand for new operand which has the sext/zext bits cut
			assert(opMatch.def);
			Builder.setInsertPt(*opMatch.def->getParent(),
					opMatch.def->getIterator());
			Register opDstReg = MRI.createVirtualRegister(
					&HwtFpga::anyregclsRegClass);
			size_t opDstRegWidth;
			hwtHls::buildHWTFPGA_MERGE_VALUES(Builder, &Observer, opDstReg,
					opMatch.opParts, &opDstRegWidth);
			MRI.setType(opDstReg, LLT::scalar(opDstRegWidth));
			newOps[i] = hwtHls::CImmOrRegOrUndefWithWidth(opDstRegWidth,
					opDstReg);
		}
	}
	Builder.setInsertPt(*MI.getParent(), MI.getIterator());
	MachineBasicBlock &MBB = *MI.getParent();
	MachineFunction &MF = *MBB.getParent();

	// $dst, $src0, $src1, $isSigned0, $width0, $isSigned1, $width1, $resultWidth
	MachineInstrBuilder MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MUL_HL);
	Observer.changingInstr(*MIB.getInstr());

	copyOperand(MIB, MRI, MF, MI.getOperand(0));
	newOps[0].addAsUse(Builder, MIB);
	newOps[1].addAsUse(Builder, MIB);
	// $isSigned0, $width0, $isSigned1, $width1, $resultWidth
	for (unsigned i = 0; i < 2; i++) {
		const MatchMulHLOperand &opMatch = matchinfo.ops[i];
		MIB.addImm(opMatch.isSigned);
		MIB.addImm(newOps[i].width);
	}
	MIB.addImm(matchinfo.ops[0].width);

	Observer.changedInstr(*MIB.getInstr());
	MI.eraseFromParent();
}

}
