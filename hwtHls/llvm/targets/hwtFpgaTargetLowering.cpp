#include <hwtHls/llvm/targets/hwtFpgaTargetLowering.h>

#include <hwtHls/llvm/targets/hwtFpgaRegisterInfo.h>
#include <hwtHls/llvm/bitMath.h>

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
