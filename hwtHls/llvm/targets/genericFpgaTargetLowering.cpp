#include "genericFpgaTargetLowering.h"
#include "genericFpgaRegisterInfo.h"

namespace llvm {

GenericFpgaTargetLowering::GenericFpgaTargetLowering(
		const llvm::TargetMachine &TM,
		const llvm::GenericFpgaTargetSubtarget &STI) :
		TargetLowering(TM), Subtarget(STI) {
	// Set up the register classes.
	// addRegisterClass(MVT::i1, &llvm::GenericFpga::AnyRegClsRegClass);
	//for (unsigned t = MVT::FIRST_INTEGER_VALUETYPE;
	//		t < MVT::LAST_INTEGER_VALUETYPE; t++) {
	//	addRegisterClass(static_cast<MVT::SimpleValueType>(t), &llvm::GenericFpga::AnyRegClsRegClass);
	//}
	addRegisterClass(MVT::i128, &llvm::GenericFpga::AnyRegClsRegClass);

	//addRegisterClass(MVT::iAny, &llvm::GenericFpga::AnyRegClsRegClass);
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

const llvm::TargetRegisterClass* GenericFpgaTargetLowering::getRegClassFor(
		llvm::MVT VT, bool isDivergent) const {
	// here is just a single register class and the type is not important there
	return &llvm::GenericFpga::AnyRegClsRegClass;
}

unsigned GenericFpgaTargetLowering::getNumRegisters(llvm::LLVMContext &Context,
		llvm::EVT VT, llvm::Optional<llvm::MVT> RegisterVT) const {
	return 4096;
}
llvm::MVT GenericFpgaTargetLowering::getRegisterTypeForCallingConv(
		llvm::LLVMContext &Context, llvm::CallingConv::ID CC,
		llvm::EVT VT) const {
	return llvm::MVT::i1;
}

unsigned GenericFpgaTargetLowering::getNumRegistersForCallingConv(
		llvm::LLVMContext &Context, llvm::CallingConv::ID CC,
		llvm::EVT VT) const {
	return 1;
}

// :note: based on `AVRTargetLowering::LowerFormalArguments`
SDValue GenericFpgaTargetLowering::LowerFormalArguments(SDValue Chain,
		CallingConv::ID CallConv, bool isVarArg,
		const SmallVectorImpl<ISD::InputArg> &Ins, const SDLoc &dl,
		SelectionDAG &DAG, SmallVectorImpl<SDValue> &InVals) const {
	MachineFunction &MF = DAG.getMachineFunction();
	//MachineFrameInfo &MFI = MF.getFrameInfo();
	auto DL = DAG.getDataLayout();

	unsigned i = 1;
	for (const ISD::InputArg &A : Ins) {
		// Arguments stored on registers.
		const TargetRegisterClass *RC = &llvm::GenericFpga::AnyRegClsRegClass;
		unsigned Reg = MF.addLiveIn(MCRegister(i), RC);
		SDValue ArgValue = DAG.getCopyFromReg(Chain, dl, Reg, A.ArgVT);
		InVals.push_back(ArgValue);
		i++;
	}

	return Chain;
}

}
