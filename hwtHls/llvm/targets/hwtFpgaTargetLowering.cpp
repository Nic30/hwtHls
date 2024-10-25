#include <hwtHls/llvm/targets/hwtFpgaTargetLowering.h>

#include <hwtHls/llvm/targets/hwtFpgaRegisterInfo.h>
#include <hwtHls/llvm/bitMath.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/Support/KnownBits.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>

namespace llvm {

HwtFpgaTargetLowering::HwtFpgaTargetLowering(const llvm::TargetMachine &TM,
		const llvm::HwtFpgaTargetSubtarget &STI) :
		TargetLowering(TM), Subtarget(STI) {
	// Set up the register classes.
	// addRegisterClass(MVT::i1, &llvm::HwtFpga::anyregclsRegClass);
	//for (unsigned t = MVT::FIRST_INTEGER_VALUETYPE;
	//		t < MVT::LAST_INTEGER_VALUETYPE; t++) {
	//	addRegisterClass(static_cast<MVT::SimpleValueType>(t), &llvm::HwtFpga::anyregclsRegClass);
	//}
	addRegisterClass(MVT::i128, &llvm::HwtFpga::anyregclsRegClass);

	//addRegisterClass(MVT::iAny, &llvm::HwtFpga::anyregclsRegClass);
	// MVT::iAny

	// Compute derived properties from the register classes.
	computeRegisterProperties(Subtarget.getRegisterInfo());

	// :note: def of legal instruction is in LegalizerInfo
	//setOperationAction(G_SELECT, MVT::Any, Legal);

	setBooleanContents(UndefinedBooleanContent);
	setJumpIsExpensive(true);
	setBooleanVectorContents(UndefinedBooleanContent);
	setSchedulingPreference(Sched::RegPressure);
	setStackPointerRegisterToSaveRestore(0);
	setSupportsUnalignedAtomics(true);
	setHasExtractBitsInsn(true);
	setHasMultipleConditionRegisters(true);
}

void computeKnownBitsImpl(GISelKnownBits &Analysis, const MachineOperand &MO,
		KnownBits &Known, const APInt &DemandedElts, unsigned Depth = 0) {
	if (MO.isReg()) {
		assert(MO.isUse());
		Analysis.computeKnownBitsImpl(MO.getReg(), Known, DemandedElts, Depth);
	} else {
		assert(MO.isCImm());
		Known = KnownBits::makeConstant(MO.getCImm()->getValue());
	}
}

class GISelKnownBitsWithExposedMaxDepth: public GISelKnownBits {
public:
	  unsigned getMaxDepth() const { return GISelKnownBits::getMaxDepth(); }
};

// based on GISelKnownBits::computeKnownBitsImpl
void HwtFpgaTargetLowering::computeKnownBitsForTargetInstr(
		GISelKnownBits &Analysis, Register R, KnownBits &Known,
		const APInt &DemandedElts, const MachineRegisterInfo &MRI,
		unsigned Depth) const {
	MachineInstr &MI = *MRI.getVRegDef(R);
	unsigned Opcode = MI.getOpcode();
	LLT DstTy = MRI.getType(R);

	if (!DstTy.isValid()) {
		Known.resetAll();
		return;
	}

	unsigned BitWidth = DstTy.getScalarSizeInBits();
	Known = KnownBits(BitWidth); // Don't know anything

	if (Depth >= reinterpret_cast<GISelKnownBitsWithExposedMaxDepth&>(Analysis).getMaxDepth())
		return;

	if (!DemandedElts)
		return;

	auto Known2 = KnownBits(BitWidth);
	switch (Opcode) {
	//case HwtFpga::HWTFPGA_FCMP:
	case HwtFpga::HWTFPGA_ICMP: {
		if (DstTy.isVector())
			break;
		if (getBooleanContents(DstTy.isVector(), false //Opcode == TargetOpcode::G_FCMP
				) == TargetLowering::ZeroOrOneBooleanContent && BitWidth > 1)
			Known.Zero.setBitsFrom(1);
		auto pred = MI.getOperand(1).getPredicate();
		using Predicate = ICmpInst::Predicate;
		auto operatorFn = KnownBits::eq;
		switch (pred) {
	    //case Predicate::FCMP_FALSE: ///< 0 0 0 0    Always false (always folded)
	    //case Predicate::FCMP_OEQ:  ///< 0 0 0 1    True if ordered and equal
	    //case Predicate::FCMP_OGT:  ///< 0 0 1 0    True if ordered and greater than
	    //case Predicate::FCMP_OGE:  ///< 0 0 1 1    True if ordered and greater than or equal
	    //case Predicate::FCMP_OLT:  ///< 0 1 0 0    True if ordered and less than
	    //case Predicate::FCMP_OLE:  ///< 0 1 0 1    True if ordered and less than or equal
	    //case Predicate::FCMP_ONE:  ///< 0 1 1 0    True if ordered and operands are unequal
	    //case Predicate::FCMP_ORD:  ///< 0 1 1 1    True if ordered (no nans)
	    //case Predicate::FCMP_UNO:  ///< 1 0 0 0    True if unordered: isnan(X) | isnan(Y)
	    //case Predicate::FCMP_UEQ:  ///< 1 0 0 1    True if unordered or equal
	    //case Predicate::FCMP_UGT:  ///< 1 0 1 0    True if unordered or greater than
	    //case Predicate::FCMP_UGE:  ///< 1 0 1 1    True if unordered, greater than, or equal
	    //case Predicate::FCMP_ULT:  ///< 1 1 0 0    True if unordered or less than
	    //case Predicate::FCMP_ULE:  ///< 1 1 0 1    True if unordered, less than, or equal
	    //case Predicate::FCMP_UNE:  ///< 1 1 1 0    True if unordered or not equal
	    //case Predicate::FCMP_TRUE: ///< 1 1 1 1    Always true (always folded)
		case Predicate::ICMP_EQ:  ///< equal
			operatorFn = KnownBits::eq;
			break;
		case Predicate::ICMP_NE:  ///< not equal
			operatorFn = KnownBits::ne;
			break;
		case Predicate::ICMP_UGT: ///< unsigned greater than
			operatorFn = KnownBits::ugt;
			break;
		case Predicate::ICMP_UGE: ///< unsigned greater or equal
			operatorFn = KnownBits::uge;
			break;
		case Predicate::ICMP_ULT: ///< unsigned less than
			operatorFn = KnownBits::ult;
			break;
		case Predicate::ICMP_ULE: ///< unsigned less or equal
			operatorFn = KnownBits::ule;
			break;
		case Predicate::ICMP_SGT: ///< signed greater than
			operatorFn = KnownBits::sgt;
			break;
		case Predicate::ICMP_SGE: ///< signed greater or equal
			operatorFn = KnownBits::sge;
			break;
		case Predicate::ICMP_SLT: ///< signed less than
			operatorFn = KnownBits::slt;
			break;
		case Predicate::ICMP_SLE: ///< signed less or equal
			operatorFn = KnownBits::sle;
			break;
		default:
			return;
		}
		const auto& _LHS = MI.getOperand(2);
		const auto& _RHS = MI.getOperand(3);
		KnownBits LHS, RHS;
		computeKnownBitsImpl(Analysis, _LHS, LHS, DemandedElts,
						Depth + 1);
		computeKnownBitsImpl(Analysis, _RHS, RHS, DemandedElts,
						Depth + 1);
		auto _Known =operatorFn(LHS, RHS);
		if (_Known.has_value()) {
			auto res = APInt(1, _Known.value());
			Known = KnownBits::makeConstant(res);
		}
		break;
	}
	case HwtFpga::HWTFPGA_SUB: {
		computeKnownBitsImpl(Analysis, MI.getOperand(1), Known, DemandedElts,
				Depth + 1);
		computeKnownBitsImpl(Analysis, MI.getOperand(2), Known2, DemandedElts,
				Depth + 1);
		Known = KnownBits::computeForAddSub(/*Add*/false, /*NSW*/false, Known,
				Known2);
		break;
	}
	case HwtFpga::HWTFPGA_XOR: {
		computeKnownBitsImpl(Analysis, MI.getOperand(2), Known, DemandedElts,
				Depth + 1);
		computeKnownBitsImpl(Analysis, MI.getOperand(1), Known2, DemandedElts,
				Depth + 1);

		Known ^= Known2;
		break;
	}
	case HwtFpga::HWTFPGA_ADD: {
		computeKnownBitsImpl(Analysis, MI.getOperand(1), Known, DemandedElts,
				Depth + 1);
		computeKnownBitsImpl(Analysis, MI.getOperand(2), Known2, DemandedElts,
				Depth + 1);
		Known = KnownBits::computeForAddSub(/*Add*/true, /*NSW*/false, Known,
				Known2);
		break;
	}
	case HwtFpga::HWTFPGA_AND: {
		// If either the LHS or the RHS are Zero, the result is zero.
		computeKnownBitsImpl(Analysis, MI.getOperand(2), Known, DemandedElts,
				Depth + 1);
		computeKnownBitsImpl(Analysis, MI.getOperand(1), Known2, DemandedElts,
				Depth + 1);

		Known &= Known2;
		break;
	}
	case HwtFpga::HWTFPGA_OR: {
		// If either the LHS or the RHS are Zero, the result is zero.
		computeKnownBitsImpl(Analysis, MI.getOperand(2), Known, DemandedElts,
				Depth + 1);
		computeKnownBitsImpl(Analysis, MI.getOperand(1), Known2, DemandedElts,
				Depth + 1);

		Known |= Known2;
		break;
	}
	case HwtFpga::HWTFPGA_MUL: {
		computeKnownBitsImpl(Analysis, MI.getOperand(2), Known, DemandedElts,
				Depth + 1);
		computeKnownBitsImpl(Analysis, MI.getOperand(1), Known2, DemandedElts,
				Depth + 1);
		Known = KnownBits::mul(Known, Known2);
		break;
	}
	case HwtFpga::HWTFPGA_MUX: {
		for (size_t SrcValI = 1; SrcValI < MI.getNumExplicitOperands(); SrcValI += 2) {
			auto SrcMO = MI.getOperand(SrcValI);
			if (SrcValI == 1) {
				// Test src1 first, since we canonicalize simpler expressions to the RHS.
				computeKnownBitsImpl(Analysis, SrcMO, Known, DemandedElts, Depth);
				// If we don't know any bits, early out.
				if (Known.isUnknown())
					return;
			} else {
				KnownBits Known2;
				computeKnownBitsImpl(Analysis, SrcMO, Known2, DemandedElts, Depth);

				// Only known if known in both the LHS and RHS.
				Known = Known.intersectWith(Known2);

				if (Known.isUnknown())
					return;
			}
		}
		break;
	}
	case HwtFpga::HWTFPGA_CLOAD: {
		const MachineMemOperand *MMO = *MI.memoperands_begin();
		if (const MDNode *Ranges = MMO->getRanges()) {
			computeKnownBitsFromRangeMetadata(*Ranges, Known);
		}

		break;
	}
	case HwtFpga::HWTFPGA_ASHR: {
		KnownBits LHSKnown, RHSKnown;
		computeKnownBitsImpl(Analysis, MI.getOperand(1), LHSKnown, DemandedElts,
				Depth + 1);
		computeKnownBitsImpl(Analysis, MI.getOperand(2), RHSKnown, DemandedElts,
				Depth + 1);
		Known = KnownBits::ashr(LHSKnown, RHSKnown);
		break;
	}
	case HwtFpga::HWTFPGA_LSHR: {
		KnownBits LHSKnown, RHSKnown;
		computeKnownBitsImpl(Analysis, MI.getOperand(1), LHSKnown, DemandedElts,
				Depth + 1);
		computeKnownBitsImpl(Analysis, MI.getOperand(2), RHSKnown, DemandedElts,
				Depth + 1);
		Known = KnownBits::lshr(LHSKnown, RHSKnown);
		break;
	}
	case HwtFpga::HWTFPGA_SHL: {
		KnownBits LHSKnown, RHSKnown;
		computeKnownBitsImpl(Analysis, MI.getOperand(1), LHSKnown, DemandedElts,
				Depth + 1);
		computeKnownBitsImpl(Analysis, MI.getOperand(2), RHSKnown, DemandedElts,
				Depth + 1);
		Known = KnownBits::shl(LHSKnown, RHSKnown);
		break;
	}
	case HwtFpga::HWTFPGA_MERGE_VALUES: {
		size_t offset = 0;
		for (const auto& [SrcMO, WidthMO] : hwtHls::MERGE_VALUES_iter_valuesWidthPairs(
				MI)) {
			KnownBits SrcOpKnown;
			computeKnownBitsImpl(Analysis, SrcMO, SrcOpKnown, DemandedElts,
					Depth + 1);
			Known.insertBits(SrcOpKnown, offset);
			offset += WidthMO.getImm();
		}
		break;
	}
	case HwtFpga::HWTFPGA_EXTRACT: {
		// dst, src, offset, width
		KnownBits SrcOpKnown;
		computeKnownBitsImpl(Analysis, MI.getOperand(1), SrcOpKnown,
				DemandedElts, Depth + 1);
		assert(BitWidth == MI.getOperand(3).getImm());
		Known = SrcOpKnown.extractBits(BitWidth, MI.getOperand(2).getImm());
		break;
	}
	case HwtFpga::HWTFPGA_CTPOP: {
		computeKnownBitsImpl(Analysis, MI.getOperand(1), Known2, DemandedElts,
				Depth + 1);
		// We can bound the space the count needs.  Also, bits known to be zero can't
		// contribute to the population.
		unsigned BitsPossiblySet = Known2.countMaxPopulation();
		unsigned LowBits = llvm::bit_width(BitsPossiblySet);
		Known.Zero.setBitsFrom(LowBits);
		// TODO: we could bound Known.One using the lower bound on the number of
		// bits which might be set provided by popcnt KnownOne2.
		break;
	}

	}

	assert(!Known.hasConflict() && "Bits known to be one AND zero?");
}

//MVT HwtFpgaTargetLowering::getPreferredSwitchConditionType(LLVMContext &Context,
//		EVT ConditionVT) const {
//	// :attention: we choose at least 1b wider because otherwise IRTranslator is not able to
//	// translate it to PHI because there are negative values because switch condition is
//	// interpreted as signed integer
//	assert(ConditionVT.isScalarInteger());
//	auto newWidth = hwtHls::upperPow2(ConditionVT.getSizeInBits() + 1);
//	return MVT::getIntegerVT(newWidth);
//}

const llvm::TargetRegisterClass* HwtFpgaTargetLowering::getRegClassFor(
		llvm::MVT VT, bool isDivergent) const {
	// here is just a single register class and the type is not important there
	return &llvm::HwtFpga::anyregclsRegClass;
}

unsigned HwtFpgaTargetLowering::getNumRegisters(llvm::LLVMContext &Context,
		llvm::EVT VT, std::optional<llvm::MVT> RegisterVT) const {
	return 4096;
}
llvm::MVT HwtFpgaTargetLowering::getRegisterTypeForCallingConv(
		llvm::LLVMContext &Context, llvm::CallingConv::ID CC,
		llvm::EVT VT) const {
	return llvm::MVT::i1;
}

unsigned HwtFpgaTargetLowering::getNumRegistersForCallingConv(
		llvm::LLVMContext &Context, llvm::CallingConv::ID CC,
		llvm::EVT VT) const {
	return 1;
}

// :note: based on `AVRTargetLowering::LowerFormalArguments`
SDValue HwtFpgaTargetLowering::LowerFormalArguments(SDValue Chain,
		CallingConv::ID CallConv, bool isVarArg,
		const SmallVectorImpl<ISD::InputArg> &Ins, const SDLoc &dl,
		SelectionDAG &DAG, SmallVectorImpl<SDValue> &InVals) const {
	MachineFunction &MF = DAG.getMachineFunction();
	//MachineFrameInfo &MFI = MF.getFrameInfo();
	auto DL = DAG.getDataLayout();

	unsigned i = 1;
	for (const ISD::InputArg &A : Ins) {
		// Arguments stored on registers.
		const TargetRegisterClass *RC = &llvm::HwtFpga::anyregclsRegClass;
		unsigned Reg = MF.addLiveIn(MCRegister(i), RC);
		SDValue ArgValue = DAG.getCopyFromReg(Chain, dl, Reg, A.ArgVT);
		InVals.push_back(ArgValue);
		i++;
	}

	return Chain;
}

}
