#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtilsInstrReducibleValuesInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtilsInstrFns.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>

using namespace llvm;

namespace hwtHls {

void MuxReducibleValuesInfo::_erraseMatchingRegBit(size_t resBitI) {
	regBitMask.clearBit(resBitI);
	auto _rDef = regVal.begin();
	while (_rDef != regVal.end()) {
		DefiningRegisterInfo &rDef = *_rDef;
		if (rDef.bitOffset <= resBitI
				&& resBitI < rDef.bitOffset + rDef.bitCnt) {
			// we found record which defines this bit
			if (rDef.bitOffset == resBitI && resBitI) {
				// cut of from start
				if (rDef.bitCnt == 1) {
					// cut of whole record
					regVal.erase(_rDef);
				} else {
					rDef.bitCnt--;
					rDef.bitOffset++;
					rDef.regOffset++;
				}
			} else if (resBitI == rDef.bitOffset + rDef.bitCnt - 1) {
				// cut off from end
				if (rDef.bitCnt == 1) {
					// cut of whole record
					regVal.erase(_rDef);
				} else {
					rDef.bitCnt--;
				}
			} else {
				// somewhere in the middle we must split record to 2
				DefiningRegisterInfo firstPart = rDef;
				DefiningRegisterInfo &secondPart = rDef;
				size_t firstPartWidth = rDef.bitOffset + rDef.bitCnt - resBitI
						- 1;
				assert(firstPartWidth < rDef.bitCnt);
				assert(firstPartWidth > 0);
				firstPart.bitCnt = firstPartWidth;
				regVal.insert(_rDef, firstPart); // insert before current rDef
				secondPart.bitCnt = rDef.bitCnt - 1 - firstPartWidth;
				assert(secondPart.bitCnt < rDef.bitCnt);
				assert(secondPart.bitCnt > 0);
				secondPart.bitOffset += firstPartWidth + 1;
				secondPart.regOffset += firstPartWidth + 1;
			}
			break; // found and updated, no additional work required
		}
		++_rDef;
	}
}

// get the earliest record from regVal starting on resBitI or after
std::list<DefiningRegisterInfo>::iterator MuxReducibleValuesInfo::_getRecordForRegisterBitOrAfter(
		size_t resBitI, std::list<DefiningRegisterInfo>::iterator begin) {
	auto _rDef = begin;
	while (_rDef != regVal.end()) {
		DefiningRegisterInfo &rDef = *_rDef;
		if (rDef.bitOffset >= resBitI) {
			return _rDef;
		}
		++_rDef;
	}
	return regVal.end();
}

void MuxReducibleValuesInfo::_defineBitAsRegBit(
		std::list<DefiningRegisterInfo>::iterator regValAfterThis,
		size_t resBitI, size_t bitI, Register reg, size_t regWidth) {
	assert(resBitI >= bitI);
	if (regValAfterThis != regVal.begin()) {
		auto _regValAfterThis = regValAfterThis;
		DefiningRegisterInfo &prevR = *(--_regValAfterThis);
		if (prevR.reg == reg
				&& prevR.bitOffset + prevR.regOffset == resBitI + 1) {
			// extend previous segment
			prevR.bitCnt++;
			valDefined.setBit(resBitI);
			regBitMask.setBit(resBitI);
			return;
		}
	}
	DefiningRegisterInfo r;
	r.bitCnt = 1;
	r.bitOffset = resBitI;
	r.reg = reg;
	r.regOffset = bitI;
	r.regWidth = regWidth;
	regVal.insert(regValAfterThis, r);
	valDefined.setBit(resBitI);
	regBitMask.setBit(resBitI);
}

// per each bit check that the bit is same or undef in each value operand of mux
void MuxReducibleValuesInfo::loadKnonwBitsFromValueOperand(
		const MachineOperand &MO, size_t offset, size_t MOWidth,
		MachineRegisterInfo &MRI, int recursionLimit) {
	assert(MOWidth > 0);
	assert(recursionLimit >= 0);
	if (MO.isCImm()) {
		// for each bit in constant check if it is same as current or redefine current if prev current was undefined
		auto *C = MO.getCImm();
		auto &V = C->getValue();
		auto W = C->getType()->getIntegerBitWidth();
		assert(MOWidth == W);

		for (size_t bitI = 0; bitI < W; ++bitI) {
			size_t resBitI = offset + bitI;
			if (valDefined[resBitI]) {
				if (constBitMask[resBitI]) {
					if (constVal[resBitI] == V[bitI]) {
						// if it is same, keep as it is
					} else {
						// this bit has different value thus we must mark it unresolved
						constBitMask.clearBit(resBitI);
						constVal.clearBit(resBitI);
					}
				} else if (regBitMask[resBitI]) {
					_erraseMatchingRegBit(resBitI);
				}
				// else bit is known to have different values
			} else {
				// redefine to a bit from constant
				valDefined.setBit(resBitI);
				constBitMask.setBit(resBitI);
				constVal.setBitVal(resBitI, V[bitI]);
			}
		}
	} else if (MO.isReg()) {
		auto *V1Def = MRI.getOneDef(MO.getReg());
		if (V1Def
				&& V1Def->getParent()->getOpcode()
						== HwtFpga::HWTFPGA_IMPLICIT_DEF) {
			return; // skip this because undef is a default state and it does not override other definitions
		} else if (V1Def && recursionLimit
				&& V1Def->getParent()->getOpcode()
						== HwtFpga::HWTFPGA_MERGE_VALUES) {
			// recursively search for each MERGE_VALUES operand
			auto &V1DefI = *V1Def->getParent();
			size_t curOffset = offset;
			for (const auto& [V1, W] : MERGE_VALUES_iter_valuesWidthPairs(
					V1DefI)) {
				size_t w = W.getImm();
				loadKnonwBitsFromValueOperand(V1, curOffset, w, MRI,
						recursionLimit - 1);
				curOffset += w;
			}
		} else {
			// mux operand value defined by some reg
			auto cur = _getRecordForRegisterBitOrAfter(offset, regVal.begin());

			for (size_t bitI = 0; bitI < MOWidth; ++bitI) {
				size_t resBitI = offset + bitI;
				if (valDefined[resBitI]) {
					if (constBitMask[resBitI]) {
						constBitMask.clearBit(resBitI);
						assert(!regBitMask[resBitI]);
					} else if (regBitMask[resBitI]) {
						if (cur == regVal.end()) {
							llvm_unreachable(
									"this can not happen as regBitMask[resBitI] was set thus there must be some value");
						} else {
							assert(
									cur->bitCnt > 0
											&& "records in regVal must have non zero width");
							if (cur->bitOffset + cur->bitCnt <= resBitI) {
								// end of currently checked element, must advance with search
								cur = _getRecordForRegisterBitOrAfter(resBitI,
										cur);
							}
							DefiningRegisterInfo &_cur = *cur;
							assert(
									resBitI < _cur.bitOffset + _cur.bitCnt
											&& "Current position in result must be smaller than end of currently probed member");
							size_t offInCur = resBitI - _cur.bitOffset;
							if (_cur.reg == MO.getReg()
									&& offInCur == _cur.regOffset
									&& offInCur < _cur.bitCnt) {
								// checking if on resBitI is a MO defining reg [resBitI - offset]
								// if it is currently defined as a same bit - keep everything as it is
							} else {
								// else clean defined value but keep bit in valDefined to mark that the bit is defined but the value
								// differs in each mux value
								if (_cur.bitCnt == 1) {
									// :attention: we will modify the regVal list which breaks "cur" iterator variable, which must be updated
									++cur;
								}
								_erraseMatchingRegBit(resBitI);
							}
						}
					}
				} else {
					// undef -> reg
					_defineBitAsRegBit(cur, resBitI, bitI, MO.getReg(),
							MOWidth);
				}
			}
		}
	} else {
		llvm_unreachable(
				"Operand should be only reg or CImm (for other operands this should not be called)");
	}
}

}
