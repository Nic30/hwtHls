#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtilsInstrFns.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <llvm/CodeGen/GlobalISel/MIPatternMatch.h>

using namespace llvm;
using namespace llvm::MIPatternMatch;

namespace hwtHls {

size_t MERGE_VALUES_getResultWidth(llvm::MachineInstr &MI) {
	uint64_t totalWidth = 0;
	for (auto &W : hwtHls::MERGE_VALUES_iter_widths(MI)) {
		totalWidth += W.getImm();
	}
	return totalWidth;
}

size_t MERGE_VALUES_getSrcOperandCount(const llvm::MachineInstr &MI) {
	return  (MI.getNumExplicitOperands() - 1) / 2;
}

llvm::iterator_range<llvm::MachineOperand*> MERGE_VALUES_iter_values(
		llvm::MachineInstr &MI) {
	size_t sizeOpBeginIndex = 1 + (MI.getNumExplicitOperands() - 1) / 2;
	return make_range(MI.operands_begin() + 1,
			MI.operands_begin() + sizeOpBeginIndex);
}

llvm::iterator_range<llvm::MachineOperand*> MERGE_VALUES_iter_widths(
		llvm::MachineInstr &MI) {
	size_t OpNum = MI.getNumExplicitOperands();
	size_t sizeOpBeginIndex = 1 + (OpNum - 1) / 2;
	return make_range<MachineOperand*>(MI.operands_begin() + sizeOpBeginIndex,
			MI.operands_begin() + OpNum);
}

detail::zippy<detail::zip_first, llvm::iterator_range<llvm::MachineOperand*>,
		llvm::iterator_range<llvm::MachineOperand*>> MERGE_VALUES_iter_valuesWidthPairs(
		llvm::MachineInstr &MI) {
	return llvm::zip_equal(MERGE_VALUES_iter_values(MI),
			MERGE_VALUES_iter_widths(MI));

}

Register buildMsbGet(MachineIRBuilder &Builder, GISelChangeObserver &Observer,
		CImmOrReg src, unsigned bitWidth, std::optional<Register> dst) {
	auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
	auto &newMI = *MIB.getInstr();
	auto &MRI = newMI.getMF()->getRegInfo();
	Observer.changingInstr(newMI);
	Register msbReg;
	if (dst.has_value()) {
		msbReg = dst.value();
	} else {
		msbReg = Builder.getMRI()->createVirtualRegister(
				&HwtFpga::anyregclsRegClass);
		MRI.setType(msbReg, LLT::scalar(1));
	}
	MIB.addDef(msbReg);
	src.addAsUse(MIB); // $src
	MIB.addImm(bitWidth); // $srcWidth
	MIB.addImm(bitWidth - 1); // $offset
	MIB.addImm(1); // $dstWidth
	assert(MIB->getNumExplicitOperands() == 5);

	Observer.changedInstr(newMI);

	return msbReg;
}

HWTFPGA_EXTRACTOptions HWTFPGA_EXTRACTOptions::get(llvm::MachineInstr & MI) {
	// $dst, $src, $srcWidth, $offset, $dstWidth
	assert(MI.getNumExplicitOperands() == 5);
	HWTFPGA_EXTRACTOptions  res;
	res.srcWidth = MI.getOperand(2).getImm();
	res.offset = MI.getOperand(3).getImm();
	res.dstWidth = MI.getOperand(4).getImm();
	assert(res.srcWidth > 0);
	assert(res.dstWidth > 0);
	assert(res.offset + res.dstWidth <= res.srcWidth);
	return res;
}

bool HWTFPGA_EXTRACTOptions::isMsbGet() {
	return dstWidth == 1 && offset == srcWidth - 1;
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
		if (src.isUndef()) {
			return CImmOrRegOrUndefWithWidth(resWidth);
		} else {
			return buildHWTFPGA_EXTRACT(Builder, src.getReg(), srcWidth, offset,
					resWidth);
		}
	}
}
CImmOrRegOrUndefWithWidth buildHWTFPGA_EXTRACT(MachineIRBuilder &Builder,
		Register src, size_t srcWidth, size_t offset, size_t resWidth) {
	auto & MRI = *Builder.getMRI();
	auto _srcTy = MRI.getType(src);
	if (_srcTy.isValid()) {
		assert(_srcTy.getSizeInBits() == srcWidth);
	}

	assert(offset + resWidth <= srcWidth);

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
			size_t curOffset = 0;
			for (const auto &[V, W]: MERGE_VALUES_iter_valuesWidthPairs(DefMI)) {
				size_t vWidth = W.getImm();
				if (curOffset >= offset) {
					// v is whole in selected bits or suffix is cut
					ConcatMembers.push_back(
							buildHWTFPGA_EXTRACT(Builder, V, vWidth, 0,
									std::min(vWidth,
											offset + resWidth - curOffset)));
				} else if (curOffset + vWidth > offset) { // current end > result start
					// v is partly in selected bits and has prefix cut and suffix possibly as well
					size_t vOffset = 0;
					if (offset > curOffset) {
						vOffset = offset - curOffset;
					}
					size_t selectEnd = offset + resWidth;
					size_t remainingBitsToSelect = selectEnd - curOffset - 1;  /* selected by request */
					size_t bitsAvailableInV = vWidth - vOffset; /* available in value itself */
					size_t bitsToTake = std::min(remainingBitsToSelect, bitsAvailableInV);
					assert(bitsToTake <= resWidth);
					ConcatMembers.push_back(
							buildHWTFPGA_EXTRACT(Builder, V, vWidth,
									vOffset, bitsToTake));
				} else {
					// skip prefix bits
				}
				curOffset += vWidth;
				if (curOffset >= offset + resWidth) {
					assert(ConcatMembers.size());
					break;
				}
			}
			assert(ConcatMembers.size());
#ifndef NDEBUG
			size_t concatBitWidth = std::accumulate(ConcatMembers.begin(),
					ConcatMembers.end(), 0ull,
					[](size_t sum, const CImmOrRegOrUndefWithWidth &v0) {
						return sum + v0.width;
					});
			assert(concatBitWidth == resWidth);
#endif
			auto res = buildHWTFPGA_MERGE_VALUES(Builder, ConcatMembers);
			return res;
		}
		case HwtFpga::HWTFPGA_EXTRACT: {
			auto srcReg = DefMI.getOperand(1);
			auto subExtractOpts = HWTFPGA_EXTRACTOptions::get(DefMI);
			if (offset == 0 && subExtractOpts.dstWidth == resWidth) {
				// keep this HWTFPGA_EXTRACT in expression because we would create an identical instruction
				return CImmOrRegOrUndefWithWidth(resWidth, src);
			}
			Register res;
			// create HWTFPGA_EXTRACT which selects directly form src operand of this HWTFPGA_EXTRACT instruction
			hwtHls::MachineInsertPointGuard g(Builder, &DefMI);
			auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
			//if (Observer)
			//	Observer->changingInstr(*MIB.getInstr());
			res = MRI.cloneVirtualRegister(src);
			MRI.setType(res, LLT::scalar(resWidth));
			MIB.addDef(res);
			MIB.addUse(srcReg.getReg());
			assert(subExtractOpts.srcWidth >= offset + subExtractOpts.offset + resWidth);
			MIB.addImm(subExtractOpts.srcWidth);
			MIB.addImm(offset + subExtractOpts.offset);
			MIB.addImm(resWidth);
			assert(MIB->getNumExplicitOperands() == 5);

			//if (Observer)
			//	Observer->changedInstr(*MIB.getInstr());
			return {resWidth, res};
		}
		}
	}
	auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
	//if (Observer)
	//	Observer->changingInstr(*MIB.getInstr());

	Register res = MRI.createVirtualRegister(&HwtFpga::anyregclsRegClass);
	MRI.setType(res, LLT::scalar(resWidth));
	MIB.addDef(res);
	MIB.addUse(src);
	assert(srcWidth >= offset + resWidth);
	MIB.addImm(srcWidth);
	MIB.addImm(offset);
	MIB.addImm(resWidth);
	assert(MIB->getNumExplicitOperands() == 5);

	//if (Observer)
	//	Observer->changedInstr(*MIB.getInstr());
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

llvm::MachineInstrBuilder buildHWTFPGA_MERGE_VALUES(
		llvm::MachineIRBuilder &Builder, llvm::GISelChangeObserver *Observer, llvm::Register DstReg,
		const llvm::SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> &ConcatMembers, size_t* _width
		) {
#ifndef NDEBUG
	auto &MRI = *Builder.getMRI();
#endif
	size_t width = 0;
	for (auto &v : ConcatMembers) {
		width += v.width;
	}
	auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MERGE_VALUES);
	assert(Builder.getObserver() == Observer);
	if (Observer)
		Observer->changingInstr(*MIB.getInstr());
	MIB.addDef(DstReg);

	for (auto &v : ConcatMembers) {
#ifndef NDEBUG
		if (v.isReg()) {
			auto vTy = MRI.getType(v.reg);
			if (vTy.isValid()) {
				assert(vTy.getScalarSizeInBits() == v.width);
			}
		}
#endif
		v.addAsUse(Builder, MIB);
	}
	for (auto &v : ConcatMembers) {
		assert(v.width > 0);
		MIB.addImm(v.width);
	}
	// MRI.setType(DstReg, LLT::scalar(width)); // this would break CSEMap llvm-18
	// // using this at the begin of function also breaks CSEMap llvm-18
	// 	if (Observer)
    //  	Observer->changingAllUsesOfReg(MRI, DstReg);
    //  MRI.setType(DstReg, LLT::scalar(width));
    //  if (Observer)
    //  	Observer->finishedChangingAllUsesOfReg();

	if (Observer)
		Observer->changedInstr(*MIB.getInstr());
	if (_width)
		*_width = width;

	return MIB;
}

CImmOrRegOrUndefWithWidth buildHWTFPGA_MERGE_VALUES(
		llvm::MachineIRBuilder &Builder,
		llvm::SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> &ConcatMembers,
		GISelChangeObserver *Observer) {
	assert(
			ConcatMembers.size()
					&& "concatenation must always contain some bits");
	ConcatMembersReduce(ConcatMembers);
	if (ConcatMembers.size() == 1) {
		return ConcatMembers[0];
	} else {
		assert(ConcatMembers.size() > 1);
		Register res = Builder.getMRI()->createVirtualRegister(
				&HwtFpga::anyregclsRegClass);
		size_t width = 0;
		buildHWTFPGA_MERGE_VALUES(Builder, Observer, res, ConcatMembers,
				&width);

		return {width, res};
	}
}

llvm::MachineInstrBuilder buildHWTFPGA_EXTRACT(llvm::MachineIRBuilder &Builder,
		llvm::GISelChangeObserver *Observer, llvm::Register DstReg,
		const llvm::MachineOperand &SrcValMO, size_t srcWidth, size_t offset,
		size_t dstWidth) {
	auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
	if (Observer)
		Observer->changingInstr(*MIB.getInstr());

	MIB.addDef(DstReg);
	if (SrcValMO.isReg()) {
		if (SrcValMO.isDef()) {
			MIB.addUse(SrcValMO.getReg());
		} else {
			MIB.add(SrcValMO);
		}
	} else {
		assert(SrcValMO.isCImm());
		MIB.add(SrcValMO);
	}
	assert(srcWidth >= offset + dstWidth);
	MIB.addImm(srcWidth);
	MIB.addImm(offset);
	MIB.addImm(dstWidth);
	assert(MIB->getNumExplicitOperands() == 5);
	if (Observer)
		Observer->changedInstr(*MIB.getInstr());
	return MIB;
}

CImmOrRegOrUndefWithWidth buildHWTFPGA_EXTRACT(llvm::MachineIRBuilder &Builder,
		llvm::GISelChangeObserver *Observer, const llvm::MachineOperand &SrcValMO,
		size_t srcWidth, size_t offset, size_t dstWidth) {
	Register res = Builder.getMRI()->createVirtualRegister(
			&HwtFpga::anyregclsRegClass);
	buildHWTFPGA_EXTRACT(Builder, Observer, res, SrcValMO, srcWidth, offset,
			dstWidth);
	return CImmOrRegOrUndefWithWidth(dstWidth, res);
}


}
