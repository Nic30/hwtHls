#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>

using namespace llvm;

namespace hwtHls {

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
	this->c = c;
	reg = 0;
}

void CImmOrReg::addAsUse(MachineInstrBuilder &MIB) const {
	if (c)
		MIB.addCImm(c);
	else {
		MIB.addUse(reg);
	}
}

CImmOrRegOrUndefWithWidth::CImmOrRegOrUndefWithWidth(const ConstantInt *_c) :
		width(_c->getType()->getIntegerBitWidth()), isUndef(false), c(_c), reg(
				0) {
	assert(c != nullptr);
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

void CImmOrRegOrUndefWithWidth::addAsUse(MachineIRBuilder &Builder,
		MachineInstrBuilder &MIB) const {
	if (isUndef) {
		Register res = Builder.getMRI()->createVirtualRegister(
				&HwtFpga::anyregclsRegClass);
		auto *newI = MIB.getInstr();
		{
			hwtHls::MachineInsertPointGuard g(Builder, newI);
			Builder.buildInstr(HwtFpga::IMPLICIT_DEF, { res }, { });
		}
	} else if (c) {
		MIB.addCImm(c);
	} else {
		MIB.addUse(reg);
	}
}

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
				}
				rDef.bitCnt--;
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
void MuxReducibleValuesInfo::processValueOperand(const MachineOperand &MO,
		size_t offset, size_t MOWidth, MachineRegisterInfo &MRI,
		int recursionLimit) {
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
		if (V1Def && V1Def->getParent()->getOpcode() == HwtFpga::IMPLICIT_DEF) {
			return; // skip this because undef is a default state and it does not override other definitions
		} else if (V1Def && recursionLimit
				&& V1Def->getParent()->getOpcode()
						== HwtFpga::HWTFPGA_MERGE_VALUES) {
			// recursively search for each MERGE_VALUES operand
			auto &V1DefI = *V1Def->getParent();
			auto widths = MERGE_VALUES_iter_widths(V1DefI);
			auto values = MERGE_VALUES_iter_values(V1DefI);
			auto wIt = widths.begin();
			size_t curOffset = offset;
			for (auto V1 : values) {
				size_t w = wIt->getImm();
				processValueOperand(V1, curOffset, w, MRI, recursionLimit - 1);
				curOffset += w;
				++wIt;
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
							DefiningRegisterInfo &_cur = *cur;
							assert(_cur.bitCnt > 0);
							if (_cur.bitOffset + _cur.bitCnt <= resBitI) {
								// end of currently checked element, must advance with search
								cur = _getRecordForRegisterBitOrAfter(resBitI,
										cur);
							}
							assert(resBitI < _cur.bitOffset + _cur.bitCnt);
							size_t offInCur = resBitI - _cur.bitOffset;
							if (_cur.reg == MO.getReg()
									&& offInCur == _cur.regOffset
									&& offInCur < _cur.bitCnt) {
								// checking if on resBitI is a MO defining reg [resBitI - offset]
								// if it is currently defined as a same bit - keep everything as it is
								errs() << "reg matches:"
										<< _cur.reg.virtRegIndex() << "\n";
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

llvm::iterator_range<llvm::MachineOperand*> MERGE_VALUES_iter_values(
		llvm::MachineInstr &MI) {
	size_t sizeOpBeginIndex = 1 + (MI.getNumOperands() - 1) / 2;
	return make_range(MI.operands_begin() + 1,
			MI.operands_begin() + sizeOpBeginIndex);
}

llvm::iterator_range<llvm::MachineOperand*> MERGE_VALUES_iter_widths(
		llvm::MachineInstr &MI) {
	size_t sizeOpBeginIndex = 1 + (MI.getNumOperands() - 1) / 2;
	return make_range<MachineOperand*>(MI.operands_begin() + sizeOpBeginIndex,
			MI.operands_end());
}

Register buildMsbGet(MachineIRBuilder &Builder, GISelChangeObserver &Observer,
		CImmOrReg x, unsigned bitWidth, std::optional<Register> dst) {
	auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
	auto &newMI = *MIB.getInstr();

	Observer.changingInstr(newMI);
	Register msbReg;
	if (dst.has_value()) {
		msbReg = dst.value();
	} else {
		msbReg = Builder.getMRI()->createVirtualRegister(
				&HwtFpga::anyregclsRegClass);
	}
	MIB.addDef(msbReg);
	x.addAsUse(MIB); // src
	MIB.addImm(bitWidth - 1); // offset
	MIB.addImm(1); // dst width
	Observer.changedInstr(newMI);

	return msbReg;
}

CImmOrRegOrUndefWithWidth buildHWTFPGA_EXTRACT(MachineIRBuilder &Builder,
		const MachineOperand &src, size_t srcWidth, size_t offset,
		size_t resWidth) {
	if (src.isCImm()) {
		auto v = (src.getCImm()->getValue().lshr(offset)).trunc(resWidth);
		auto Ty = IntegerType::get(Builder.getMF().getFunction().getContext(),
				resWidth);
		return CImmOrRegOrUndefWithWidth(
				dyn_cast<ConstantInt>(ConstantInt::get(Ty, v)));
	} else {
		assert(src.isReg());
		return buildHWTFPGA_EXTRACT(Builder, src.getReg(), srcWidth, offset,
				resWidth);
	}
}
CImmOrRegOrUndefWithWidth buildHWTFPGA_EXTRACT(MachineIRBuilder &Builder,
		Register src, size_t srcWidth, size_t offset, size_t resWidth) {
	auto &MRI = *Builder.getMRI();
	assert(srcWidth == 0 || srcWidth >= resWidth);
	if (srcWidth == resWidth) {
		assert(offset == 0);
		return {resWidth, src};
	} else if (MachineOperand *defMO = MRI.getOneDef(src)) {
		// problem there is that even if the register has a single definition
		// the additional instruction captures the current value and we can not simply
		// use original register because it may be updated until we use it in result of this function
		// from this reason we have to create a copy which may be reduced later

		auto &DefMI = *defMO->getParent();
		switch (DefMI.getOpcode()) {
		case HwtFpga::HWTFPGA_MERGE_VALUES: {
			SmallVector<CImmOrRegOrUndefWithWidth> ConcatMembers;
			auto values = MERGE_VALUES_iter_values(DefMI);
			auto widths = MERGE_VALUES_iter_widths(DefMI);
			size_t curOffset = 0;
			auto vIt = values.begin();
			for (auto &w : widths) {
				size_t vWidth = w.getImm();
				if (curOffset >= offset) {
					// v is whole in selected bits or suffix is cut
					ConcatMembers.push_back(
							buildHWTFPGA_EXTRACT(Builder, *vIt, srcWidth, 0,
									std::min(vWidth,
											offset + resWidth - curOffset)));
				} else if (curOffset + vWidth > offset) { // current end > result start
					// v is partly in selected bits and has prefix cut and suffix possibly as well
					size_t vOffset = offset - curOffset;
					assert(vOffset < vWidth);
					size_t bitsToTake = std::min(vWidth - vOffset, /* available in value itself */
					offset + resWidth - curOffset /* selected by request */);
					ConcatMembers.push_back(
							buildHWTFPGA_EXTRACT(Builder, *vIt, srcWidth,
									vOffset, bitsToTake));
				} else {
					// skip prefix bits
				}
				curOffset += vWidth;
				if (curOffset >= offset + resWidth) {
					assert(ConcatMembers.size());
					break;
				}
				++vIt;
			}
			assert(ConcatMembers.size());
			assert(
					std::accumulate(ConcatMembers.begin(), ConcatMembers.end(),
							0ull,
							[](size_t sum,
									const CImmOrRegOrUndefWithWidth &v0) {
								return sum + v0.width;
							}) == resWidth);
			auto res = buildHWTFPGA_MERGE_VALUES(Builder, ConcatMembers);
			return res;
		}
		case HwtFpga::HWTFPGA_EXTRACT: {
			auto srcReg = DefMI.getOperand(1);
			auto extractOffset = (size_t) DefMI.getOperand(2).getImm();
			auto extractWidth = (size_t) DefMI.getOperand(3).getImm();
			if (offset == 0 && extractWidth == resWidth) {
				return CImmOrRegOrUndefWithWidth(resWidth, src);
			}
			Register res;
			{
				hwtHls::MachineInsertPointGuard g(Builder, &DefMI);
				auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
				res = MRI.cloneVirtualRegister(src);
				MIB.addDef(res);
				MIB.addUse(srcReg.getReg());
				MIB.addImm(extractOffset + offset);
				MIB.addImm(resWidth);
			}

			return {resWidth, res};
		}
		}
	}
	auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
	Register res = MRI.createVirtualRegister(&HwtFpga::anyregclsRegClass);
	MIB.addDef(res);
	MIB.addUse(src);
	MIB.addImm(offset);
	MIB.addImm(resWidth);
	return {resWidth, res};
}

// lower first
APInt APInt_concat(const APInt &v0, const APInt &v1) {
	auto newWidth = v0.getBitWidth() + v1.getBitWidth();
	return v0.zext(newWidth) | (v1.zext(newWidth) << v0.getBitWidth());
}

// lower first
ConstantInt* ConstantInt_concat(const ConstantInt &v0, const ConstantInt &v1) {
	auto newWidth = v0.getType()->getIntegerBitWidth()
			+ v1.getType()->getIntegerBitWidth();
	auto newTy = IntegerType::get(v0.getContext(), newWidth);
	return dyn_cast<ConstantInt>(
			ConstantInt::get(newTy, APInt_concat(v0.getValue(), v1.getValue())));
}

/*
 * Merge consequent undefs, constants
 * */
void ConcatMembersReduce(
		llvm::SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> &ConcatMembers) {
	assert(
			ConcatMembers.size()
					&& "concatenation must always contain some bits");
	auto compactedIt = ConcatMembers.begin(); // position of last item in result

	for (auto &v : ConcatMembers) {
		if (&v == &*compactedIt) {
			continue; // skip first
		}
		if (compactedIt->isUndef && v.isUndef) {
			compactedIt->width += v.width;
			v.width = 0;
			continue;
		} else if (compactedIt->c && v.c) {
			// lower first
			compactedIt->c = ConstantInt_concat(*compactedIt->c, *v.c);
			compactedIt->width += v.width;
			v.width = 0;
			continue;
		}
		compactedIt++; // increment iterator for last updated item because compaction failed
		// skip move if we would move to same item
		if (&v != &*compactedIt) {
			*compactedIt = v;
		}
	}
	size_t reducedItemCnt = 0;
	if (compactedIt != ConcatMembers.end())
		++compactedIt; // to get after last used item
	while (compactedIt != ConcatMembers.end()) {
		++compactedIt;
		++reducedItemCnt;
	}
	assert(
			reducedItemCnt < ConcatMembers.size()
					&& "At least a single item must remain");
	//ConcatMembers.resize(ConcatMembers.size() - reducedItemCnt);
	for (size_t i = 0; i < reducedItemCnt; i++) {
		ConcatMembers.pop_back();
	}
}

CImmOrRegOrUndefWithWidth buildHWTFPGA_MERGE_VALUES(
		llvm::MachineIRBuilder &Builder,
		llvm::SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> &ConcatMembers) {
	assert(
			ConcatMembers.size()
					&& "concatenation must always contain some bits");
	ConcatMembersReduce(ConcatMembers);
	if (ConcatMembers.size() == 1) {
		return ConcatMembers[0];
	} else {
		assert(ConcatMembers.size() > 1);
		size_t width = 0;
		Register res = Builder.getMRI()->createVirtualRegister(
				&HwtFpga::anyregclsRegClass);
		auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MERGE_VALUES);
		MIB.addDef(res);
		for (auto &v : ConcatMembers) {
			v.addAsUse(Builder, MIB);
			width += v.width;
		}
		for (auto &v : ConcatMembers) {
			MIB.addImm(v.width);
		}
		return {width, res};
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

}
