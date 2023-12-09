#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>
#include <hwtHls/llvm/bitMath.h>

namespace llvm {


bool HwtFpgaCombinerHelper::matchMuxForConstPropagation(llvm::MachineInstr &MI,
		hwtHls::MuxReducibleValuesInfo &matchInfo) {
	if (MI.getNumExplicitOperands() < 1 + 3) {
		// avoid copy propagation case because it is handled elsewhere
		return false;
	}
	size_t width = hwtHls::hwtFpgaMuxFindValueWidth(MI, MRI);
	if (width == 0)
		return false; // can not resolve width, can not probe possible MERGE_VALUES, must exit
	matchInfo = hwtHls::MuxReducibleValuesInfo(width);

	auto OpIt = MI.operands_begin() + 1; // skip dst
	while (OpIt != MI.operands_end()) {
		const auto &V = *OpIt;
		matchInfo.loadKnonwBitsFromValueOperand(V, 0, width, MRI, 1);
		if (matchInfo.valDefined.isAllOnes() && matchInfo.constBitMask.isZero()
				&& matchInfo.regBitMask.isZero())
			return false; // all value bits known to be defined differently, no point in search for other operands

		++OpIt; // move to condition
		if (OpIt != MI.operands_end()) {
			++OpIt; // move to next value
		}
	}
	return true;
}

[[nodiscard]] Register HwtFpgaCombinerHelper::_rewriteMuxConstPropagationExpandReducedBits(
		llvm::MachineInstr &NewMI, hwtHls::MuxReducibleValuesInfo &matchInfo,
		const std::vector<std::pair<bool, unsigned>> &usedBitsVec) {
	SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> ResConcatMembers;
	size_t off = 0;
	size_t inNewMIoff = 0; // offset for bit select from reduced result produced by NewMI
	size_t newMiResWidth = 0;
	for (auto usedBits : usedBitsVec) {
		if (usedBits.first)
			newMiResWidth += usedBits.second;
	}
	Register newMiRes = NewMI.getOperand(0).getReg();

	std::list<hwtHls::DefiningRegisterInfo>::iterator regRecPos =
			matchInfo.regVal.begin();
	for (auto usedBits : usedBitsVec) {
		if (usedBits.first) {
			// select from NewMI result
			ResConcatMembers.push_back(
					hwtHls::buildHWTFPGA_EXTRACT(Builder, newMiRes,
							newMiResWidth, inNewMIoff, usedBits.second));
			inNewMIoff += usedBits.second;
		} else {
			// extract bits from known values for operands
			size_t len = usedBits.second;
			size_t _off = off;
			while (_off != off + len) {
				// the 1s segment in keepMask may actually be longer than in constBitMask or regBitMask
				// and it may be composed from multiple segments from these two sources or from original value
				// here we iterate trough these segments
				if (!matchInfo.valDefined[_off]) {
					// known to be undef
					size_t undefStartOff = _off;
					while (_off <  off + len && !matchInfo.valDefined[_off])
						_off++;
					ResConcatMembers.push_back(
							hwtHls::CImmOrRegOrUndefWithWidth(
									_off - undefStartOff));
				} else if (matchInfo.constBitMask[_off]) {
					// known to be constant
					size_t constStartOff = _off;
					while (_off <  off + len && matchInfo.constBitMask[_off])
						_off++;
					size_t constWidth = _off - constStartOff;
					auto *Ty = IntegerType::get(
							Builder.getMF().getFunction().getContext(),
							constWidth);
					ConstantInt *C = dyn_cast<ConstantInt>(
							ConstantInt::get(Ty,
									matchInfo.constVal.extractBits(constWidth,
											constStartOff)));
					ResConcatMembers.push_back(
							hwtHls::CImmOrRegOrUndefWithWidth(C));

				} else if (matchInfo.regBitMask[_off]) {
					// known to have value of some reg
					// :note: regRec are non overlapping
					regRecPos = matchInfo._getRecordForRegisterBitOrAfter(_off,
							regRecPos);
					hwtHls::DefiningRegisterInfo &_regRecPos = *regRecPos;
					assert(
							_regRecPos.bitOffset == _off
									&& "Must start exactly on this position because we do not split 1s sequence there");
					if (_regRecPos.regOffset == 0
							&& _regRecPos.bitCnt == _regRecPos.regWidth) {
						// no HWTFPGA_EXTRACT required because whole value of reg is used as it is
						ResConcatMembers.push_back(
								hwtHls::CImmOrRegOrUndefWithWidth(
										_regRecPos.bitCnt, _regRecPos.reg));
					} else {
						// need to construct HWTFPGA_EXTRACT
						Builder.setInstrAndDebugLoc(NewMI);
						auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
						Register dst = MRI.createVirtualRegister(
								&HwtFpga::anyregclsRegClass);
						MIB.addDef(dst);
						MIB.addUse(_regRecPos.reg);
						MIB.addImm(_regRecPos.regOffset);
						MIB.addImm(_regRecPos.bitCnt);
						ResConcatMembers.push_back(
								hwtHls::CImmOrRegOrUndefWithWidth(
										_regRecPos.bitCnt, dst));
					}
					_off += _regRecPos.bitCnt;
				}
			}
		}
		off += usedBits.second;
	}
	auto res = hwtHls::buildHWTFPGA_MERGE_VALUES(Builder, ResConcatMembers);
	assert(!res.isUndef && res.c == nullptr && res.reg != 0);
	return res.reg;
}

bool HwtFpgaCombinerHelper::rewriteMuxConstPropagation(llvm::MachineInstr &MI,
		hwtHls::MuxReducibleValuesInfo &matchInfo) {
	Builder.setInstrAndDebugLoc(MI);
	// catch trivial cases where output value is completely known
	if (matchInfo.constBitMask.isAllOnes()) {
		auto &Ctx = Builder.getMF().getFunction().getContext();
		ConstantInt *CI = ConstantInt::get(Ctx, matchInfo.constVal);
		Builder.setInstr(MI);
		MachineInstrBuilder MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MUX);
		MIB.addDef(MI.getOperand(0).getReg()).addCImm(CI);
		MI.eraseFromParent();
		return true;
	} else if (matchInfo.regBitMask.isAllOnes()) {
		llvm_unreachable("[todo]");
	}
	// construct operands if required (build MERGE_VALUES from parts which do have matchInfo.valDefined set and constBitMask and regBitMask unset)
	auto keepMask = matchInfo.valDefined & ~matchInfo.constBitMask
			& ~matchInfo.regBitMask; // 1 in bit means that the value can not be reduced and must be kept in MUX instruction
	bool wasCompletlyReplaced = keepMask.isZero();
	auto usedBitsVec = hwtHls::iter1and0sequences(keepMask, 0,
			keepMask.getBitWidth());

	SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> newMuxOperands;
	auto OpIt = MI.operands_begin() + 1; // skip dst
	while (OpIt != MI.operands_end()) {
		const MachineOperand &V = *OpIt;
		SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> OperandValConcatMembers;
		size_t off = 0;
		for (auto usedBits : usedBitsVec) {
			if (usedBits.first) {
				// extract non reduced bits from operand
				hwtHls::CImmOrRegOrUndefWithWidth m =
						hwtHls::buildHWTFPGA_EXTRACT(Builder, V,
								keepMask.getBitWidth(), off, usedBits.second);
				OperandValConcatMembers.push_back(m);
			}
			off += usedBits.second;
		}
		newMuxOperands.push_back(
				buildHWTFPGA_MERGE_VALUES(Builder, OperandValConcatMembers));
		if (wasCompletlyReplaced) {
			auto replacement = newMuxOperands.back();
			auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MUX);
			MIB.addDef(MI.getOperand(0).getReg());
			replacement.addAsUse(Builder, MIB);
			MI.eraseFromParent();
			return true;
		}

		++OpIt;
		if (OpIt != MI.operands_end()) {
			if (OpIt->isReg()) {
				newMuxOperands.push_back(
						hwtHls::CImmOrRegOrUndefWithWidth(1, OpIt->getReg()));
			} else {
				OpIt->isCImm();
				newMuxOperands.push_back(
						hwtHls::CImmOrRegOrUndefWithWidth(OpIt->getCImm()));
			}
			++OpIt; // skip condition to get to next value
		}
	}

	// construct new reduced mux
	bool bitwidthWasReduced = !keepMask.isAllOnes();
	assert(!wasCompletlyReplaced);
	Builder.setInstrAndDebugLoc(MI);
	MachineInstrBuilder MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MUX);
	if (bitwidthWasReduced) {
		// create tmp register
		Register dst = MRI.createVirtualRegister(&HwtFpga::anyregclsRegClass);
		MIB.addDef(dst);
	} else {
		// use original dst directly
		MIB.addDef(MI.getOperand(0).getReg());
	}
	for (auto &o : newMuxOperands) {
		o.addAsUse(Builder, MIB);
	}

	if (bitwidthWasReduced) {
		// construct final value by merging new mux value with reduced parts
		auto res = _rewriteMuxConstPropagationExpandReducedBits(*MIB.getInstr(), matchInfo,
				usedBitsVec);
		MRI.replaceRegWith(MI.getOperand(0).getReg(), res);
	}
	MI.eraseFromParent();
	return true;
}

}
