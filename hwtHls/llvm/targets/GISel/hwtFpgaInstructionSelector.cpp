#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelector.h>

#include <llvm/CodeGen/GlobalISel/GIMatchTableExecutorImpl.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/MC/MCContext.h>
#include <llvm/Support/Debug.h>

#include <hwtHls/llvm/targets/hwtFpgaTargetPassConfig.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaIoUtils.h>
#include <hwtHls/llvm/targets/bitMathUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#define DEBUG_TYPE "genericfpga-isel"

using namespace llvm;
using namespace hwtHls::HwtFpgaInstructionSelector;

#define GET_GLOBALISEL_PREDICATE_BITSET
#include "HwtFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_PREDICATE_BITSET

class HwtFpgaTargetInstructionSelector: public InstructionSelector {
public:
	HwtFpgaTargetInstructionSelector(const HwtFpgaTargetMachine &TM,
			const HwtFpgaTargetSubtarget &STI,
			const HwtFpgaRegisterBankInfo &RBI);

	bool select(MachineInstr &I) override;
	static const char* getName() {
		return DEBUG_TYPE;
	}

private:
	bool finalizeReplacementOfInstruction(MachineInstrBuilder &MIB,
			MachineInstr &I);
	bool selectImpl(MachineInstr &I, CodeGenCoverage &CoverageInfo) const;
	bool select_G_SHL(MachineRegisterInfo &MRI, MachineIRBuilder &MIRB,
			MachineInstr &I);
	bool select_G_SHR(MachineRegisterInfo &MRI, MachineIRBuilder &MIRB,
			MachineInstr &I, bool isArithmetic);
	bool select_G_SEXT(MachineRegisterInfo &MRI, MachineIRBuilder &MIRB,
			MachineInstr &I);
	bool select_G_ZEXT(MachineRegisterInfo &MRI, MachineIRBuilder &MIRB,
			MachineInstr &I);
	bool select_G_TRUNC(MachineRegisterInfo &MRI, MachineIRBuilder &MIRB,
			MachineInstr &I);
	MachineOperand rewrite_G_PTR_ADD_exprToIndexADD(MachineFunction &MF, MachineRegisterInfo &MRI,
			MachineIRBuilder &MIRB, Register baseAddrDefiningReg, size_t indexWidth,
			TypeSize itemSize, MachineInstr &addrDefMI,
			std::map<Register, Register> &replacements);
	bool select_G_LOAD_or_G_STORE(MachineFunction &MF, MachineRegisterInfo &MRI,
			MachineIRBuilder &MIRB, MachineInstr &MI);
	std::optional<Register> _getSelectedMsb(MachineIRBuilder &MIRB,
			MachineRegisterInfo &MRI, MachineOperand inputMo);

	const HwtFpgaTargetSubtarget &STI;
	const llvm::HwtFpgaInstrInfo &TII;
	const HwtFpgaRegisterInfo &TRI;
	const HwtFpgaRegisterBankInfo &RBI;

	// FIXME: This is necessary because DAGISel uses "Subtarget->" and GlobalISel
	// uses "STI." in the code generated by TableGen. We need to unify the name of
	// Subtarget variable.
	const HwtFpgaTargetSubtarget *Subtarget = &STI;

#define GET_GLOBALISEL_PREDICATES_DECL
#include "HwtFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_PREDICATES_DECL

#define GET_GLOBALISEL_TEMPORARIES_DECL
#include "HwtFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_TEMPORARIES_DECL
};

#define GET_GLOBALISEL_IMPL
#include "HwtFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_IMPL

HwtFpgaTargetInstructionSelector::HwtFpgaTargetInstructionSelector(
		const HwtFpgaTargetMachine &TM, const HwtFpgaTargetSubtarget &STI,
		const HwtFpgaRegisterBankInfo &RBI)
: InstructionSelector(), STI(STI), TII(*dynamic_cast<const HwtFpgaInstrInfo*>(STI.getInstrInfo())),
TRI(*dynamic_cast<const HwtFpgaRegisterInfo*>(STI.getRegisterInfo())), RBI(RBI),

#define GET_GLOBALISEL_PREDICATES_INIT
#include "HwtFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_PREDICATES_INIT
#define GET_GLOBALISEL_TEMPORARIES_INIT
#include "HwtFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_TEMPORARIES_INIT
{
}

bool constrainInstRegOperands(MachineInstr &I, const TargetInstrInfo &TII,
		const TargetRegisterInfo &TRI, const RegisterBankInfo &RBI) {
	MachineBasicBlock &MBB = *I.getParent();
	MachineFunction &MF = *MBB.getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();

	for (unsigned OpI = 0, OpE = I.getNumExplicitOperands(); OpI != OpE;
			++OpI) {
		MachineOperand &MO = I.getOperand(OpI);

		// There's nothing to be done on non-register operands.
		if (!MO.isReg())
			continue;

		LLVM_DEBUG(dbgs() << "Converting operand: " << MO << '\n');
		assert(MO.isReg() && "Unsupported non-reg operand");

		Register Reg = MO.getReg();
		// Physical registers don't need to be constrained.
		if (Register::isPhysicalRegister(Reg))
			continue;

		// Register operands with a value of 0 (e.g. predicate operands) don't need
		// to be constrained.
		if (Reg == 0)
			continue;

		// If the operand is a vreg, we should constrain its regclass, and only
		// insert COPYs if that's impossible.
		// constrainOperandRegClass does that for us.
		constrainOperandRegClass(MF, TRI, MRI, TII, RBI, I, I.getDesc(), MO,
				OpI);

		// Tie uses to defs as indicated in MCInstrDesc if this hasn't already been
		// done.
		if (MO.isUse()) {
			int DefIdx = I.getDesc().getOperandConstraint(OpI, MCOI::TIED_TO);
			if (DefIdx != -1 && !I.isRegTiedToUseOperand(DefIdx))
				I.tieOperands(DefIdx, OpI);
		}
	}
	return true;
}

bool HwtFpgaTargetInstructionSelector::finalizeReplacementOfInstruction(
		MachineInstrBuilder &MIB, MachineInstr &I) {
	if (!constrainInstRegOperands(*MIB.getInstr(), TII, TRI, RBI))
		return false;
	I.eraseFromParent();
	return true;
}

bool HwtFpgaTargetInstructionSelector::select(MachineInstr &I) {
	/*
	 * After selection process finish each VReg has to have some TargetRegisterClass assigned.
	 * */
	assert(I.getParent() && "Instruction should be in a basic block!");
	assert(
			I.getParent()->getParent()
					&& "Instruction should be in a function!");

	MachineBasicBlock &MBB = *I.getParent();
	MachineFunction &MF = *MBB.getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();
	auto Opc = I.getOpcode();

	if (!isPreISelGenericOpcode(Opc)) {
		// Certain non-generic instructions also need some special handling.
		return true;
	}

	if (selectImpl(I, *CoverageInfo)) {
		return true;
	}

	const TargetRegisterClass &RC = HwtFpga::anyregclsRegClass;

	MachineIRBuilder Builder(I);
	//llvm::errs() << "HwtFpgaTargetInstructionSelector::select: "
	//		<< TII.getName(Opc) << "\n";
	using namespace TargetOpcode;
	switch (Opc) {
	case G_PHI: {
		// PHI value args must be registers otherwise OptimizePHIs will fail.
		//MachineIRBuilder Builder(I);
		//auto MIB = Builder.buildInstr(PHI);
		//MIB.getInstr()->setDesc(TII.get(PHI));
		//I.setDesc(TII.get(PHI));
		//
		//Register DstReg = I.getOperand(0).getReg();
		//
		//selectInstrArgs(I, MIB, true);
		//if (!RBI.constrainGenericRegister(DstReg, RC, MRI)) {
		//	break;
		//}
		//if (!constrainInstRegOperands(*MIB.getInstr(), TII, TRI, RBI))
		//	return false;
		//I.eraseFromParent();
		I.setDesc(TII.get(PHI));

		Register DstReg = I.getOperand(0).getReg();
		if (!RBI.constrainGenericRegister(DstReg, RC, MRI)) {
			break;
		}
		if (!constrainInstRegOperands(I, TII, TRI, RBI))
			return false;
		return true;
	}
	case G_GLOBAL_VALUE:
	case G_CONSTANT: {
		auto MIB = Builder.buildInstr(Opc);
		selectInstrArgs(I, MIB, true);
		auto o0 = MIB.getInstr()->getOperand(0).getReg();
		LLT Ty;
		if (Opc == G_CONSTANT) {
			Ty = LLT::scalar(I.getOperand(1).getCImm()->getBitWidth());
		} else {
			assert(Opc == G_GLOBAL_VALUE);
			auto ptrT = I.getOperand(1).getGlobal()->getType();
			Type * elmT;
			size_t SizeInBits;
			std::tie(elmT, SizeInBits) = hwtHls::getGlobalValueElementTypeAndAddressWidth(I);
			Ty = LLT::pointer(ptrT->getAddressSpace(), SizeInBits);
		}
		MRI.setType(o0, Ty);
		return finalizeReplacementOfInstruction(MIB, I);
	}
	case G_LOAD:
	case G_STORE:
		return select_G_LOAD_or_G_STORE(MF, MRI, Builder, I);
	case G_ADD:
	case G_AND:
	case G_BR:
	case G_BRCOND:
	case G_EXTRACT:
	case G_ICMP:
	case G_IMPLICIT_DEF:
	case G_INDEXED_LOAD:
	case G_INDEXED_STORE:
	case G_MERGE_VALUES:
	case G_PTR_ADD:
	case G_MUL:
	case G_UREM:
	case G_UDIV:
	case G_SREM:
	case G_SDIV:
	case G_OR:
	case G_SELECT:
	case G_SUB:
	case G_XOR:
	case G_ABS:
	case G_SMIN:
	case G_SMAX:
	case G_UMAX:
	case G_UMIN:
	case G_CTLZ_ZERO_UNDEF:
	case G_CTTZ_ZERO_UNDEF:
	case G_CTLZ:
	case G_CTTZ:
	case G_CTPOP:
	case G_FREEZE:
	case G_SHL:
	case G_LSHR:
	case G_ASHR: {
		// try special cases
		switch (Opc) {
		case G_SHL:
			if (select_G_SHL(MRI, Builder, I))
				return true;
			break;
		case G_LSHR:
			if (select_G_SHR(MRI, Builder, I, false))
				return true;
			break;
		case G_ASHR:
			if (select_G_SHR(MRI, Builder, I, true))
				return true;
			break;
		default:
			break;
		}

		auto _Opc = Opc;
		switch (Opc) {
		case G_EXTRACT:
			_Opc = HwtFpga::HWTFPGA_EXTRACT;
			break;
		case G_MERGE_VALUES:
			_Opc = HwtFpga::HWTFPGA_MERGE_VALUES;
			break;
		case G_IMPLICIT_DEF:
			_Opc = HwtFpga::HWTFPGA_IMPLICIT_DEF;
			break;
		case G_CTLZ_ZERO_UNDEF:
			_Opc = HwtFpga::HWTFPGA_CTLZ_ZERO_UNDEF;
			break;
		case G_CTTZ_ZERO_UNDEF:
			_Opc = HwtFpga::HWTFPGA_CTTZ_ZERO_UNDEF;
			break;
		case G_CTLZ:
			_Opc = HwtFpga::HWTFPGA_CTLZ;
			break;
		case G_CTTZ:
			_Opc = HwtFpga::HWTFPGA_CTTZ;
			break;
		case G_CTPOP:
			_Opc = HwtFpga::HWTFPGA_CTPOP;
			break;
		case G_FREEZE:
			_Opc = HwtFpga::COPY;
			break;
		case G_SHL:
			_Opc = HwtFpga::HWTFPGA_SHL;
			break;
		case G_LSHR:
			_Opc = HwtFpga::HWTFPGA_LSHR;
			break;
		case G_ASHR:
			_Opc = HwtFpga::HWTFPGA_ASHR;
			break;
		}
		auto MIB = Builder.buildInstr(_Opc);
		selectInstrArgs(I, MIB, Opc != G_BRCOND && Opc != G_BR);

		// add extra type spec operands if required
		if (Opc == G_EXTRACT) {
			// dst, src, offset, dstWidth, (dst, src and offset already added)
			auto dst = I.getOperand(0).getReg();
			MIB.addImm(MRI.getType(dst).getSizeInBits()); // add dstWidth
			//MRI.setType(VReg, Ty)
		} else if (Opc == G_MERGE_VALUES) {
			// dst, src{N}, width{N}, (dst, srcs were already added)
			for (unsigned i = 1; i < I.getNumOperands(); i++) {
				MIB.addImm(
						MRI.getType(I.getOperand(i).getReg()).getSizeInBits()); // add dstWidth
			}
		} else if (Opc == G_IMPLICIT_DEF) {
			auto dst = I.getOperand(0).getReg();
			MIB.addImm(MRI.getType(dst).getSizeInBits()); // add dstWidth
		}

		return finalizeReplacementOfInstruction(MIB, I);
	}
	case G_SEXT:
		return select_G_SEXT(MRI, Builder, I);
	case G_ZEXT:
		return select_G_ZEXT(MRI, Builder, I);
	case G_TRUNC:
		return select_G_TRUNC(MRI, Builder, I);
	default:
		return false; // some unknown operands (on error it will be printed immediately by caller)
	}

	return false; // all is selected because this is just a dummy selector
}

MachineOperand HwtFpgaTargetInstructionSelector::rewrite_G_PTR_ADD_exprToIndexADD(MachineFunction &MF, MachineRegisterInfo &MRI,
		MachineIRBuilder &MIRB, Register baseAddrDefiningReg, size_t indexWidth,
		TypeSize itemSize, MachineInstr &addrDefMI,
		std::map<Register, Register> &replacements) {
	// :note: replacements must be updated before calling this function in recurse

	// set to insert before addrDefMI
	auto existing = replacements.find(addrDefMI.getOperand(0).getReg());
	if (existing != replacements.end())
		return  MachineOperand::CreateReg(existing->second, false);

	switch (addrDefMI.getOpcode()) {
	case TargetOpcode::G_PTR_ADD: {
		// %1:_(p0) = G_PTR_ADD %0:_(p0), %1:_(s32)
		if (isPow2(itemSize)) {
			// use HWTFPGA_EXTRACT to slice off lower bits to convert from address to index
			assert(indexWidth > 0 && "G_PTR_ADD should not be used for memories which are just 1 scalar");
			// dst, src, offset, dstWidth
			assert(addrDefMI.getParent());
			MIRB.setInsertPt(*addrDefMI.getParent(), addrDefMI.getIterator());
			MachineInstrBuilder indexMIB = MIRB.buildInstr(
					HwtFpga::HWTFPGA_EXTRACT);
			Register indexReg = MRI.createGenericVirtualRegister(
					LLT::scalar(indexWidth));
			indexMIB.addDef(indexReg);
			//indexMIB.addUse(addrDefMI.getOperand(2).isReg());  // G_PTR_ADD right operand to index src operand
			//assert(addrDefMI.getOperand(2).isReg());
			//assert(!MRI.getType(addrDefMI.getOperand(2).getReg()).isPointer());
			auto srcMO = addrDefMI.getOperand(2);
			//auto srcDef = MRI.getUniqueVRegDef(srcMO.getReg());
			//assert(srcDef);
			//auto srcMOSelected = rewrite_G_PTR_ADD_exprToIndexADD(MF, MRI, MIRB, baseAddrDefiningReg, indexWidth, itemSize, *srcDef, replacements);
			selectInstrArg(MF, indexMIB, MRI, srcMO);
			indexMIB.addImm(log2ceil(itemSize)); // offset
			indexMIB.addImm(indexWidth); // dstWidth

			auto &IndexSliceMI = *indexMIB.getInstr();
			assert(constrainInstRegOperands(IndexSliceMI, TII, TRI, RBI));

			auto p0Op = addrDefMI.getOperand(1).getReg();
			if (p0Op != baseAddrDefiningReg) {
				// this is not just base + n format, HWTFPGA_ADD must be constructed
				replacements[indexReg] = indexReg;
				replacements[addrDefMI.getOperand(0).getReg()] = indexReg;
				auto p0Def = MRI.getUniqueVRegDef(p0Op);
				assert(p0Def);
				auto p0OpSelected = rewrite_G_PTR_ADD_exprToIndexADD(MF, MRI,
						MIRB, baseAddrDefiningReg, indexWidth, itemSize, *p0Def,
						replacements);
				Register indexAddedReg = MRI.createGenericVirtualRegister(
						LLT::scalar(indexWidth));
				MIRB.setInsertPt(*IndexSliceMI.getParent(), ++IndexSliceMI.getIterator());
				auto indexAddMIB = MIRB.buildInstr(HwtFpga::HWTFPGA_ADD, { indexAddedReg }, {
						 });
				auto _indexReg = MachineOperand::CreateReg(indexReg, false);
				selectInstrArg(MF, indexAddMIB, MRI, _indexReg);
				selectInstrArg(MF, indexAddMIB, MRI, p0OpSelected);
				assert(constrainInstRegOperands(*indexAddMIB.getInstr(), TII, TRI, RBI));

				indexReg = indexAddedReg;
			} else {
				replacements[indexReg] = indexReg;
				replacements[addrDefMI.getOperand(0).getReg()] = indexReg;
			}
			return MachineOperand::CreateReg(indexReg, false);
		} else {
			llvm_unreachable(
					"NotImplemented, extract the multiplier from the index");
		}
		break;
	}
	case TargetOpcode::PHI:
	case TargetOpcode::G_PHI: {
		// construct new phi just for index part
		assert(addrDefMI.getParent());
		MIRB.setInsertPt(*addrDefMI.getParent(), addrDefMI.getIterator());
		auto indexPhiMIB = MIRB.buildInstr(TargetOpcode::PHI);
		Register indexReg = MRI.createGenericVirtualRegister(
				LLT::scalar(indexWidth));
		replacements[indexReg] = indexReg;
		replacements[addrDefMI.getOperand(0).getReg()] = indexReg;
		indexPhiMIB.addDef(indexReg);
		for (size_t i = 1; i < addrDefMI.getNumExplicitOperands(); i += 2) {
			const MachineOperand& ValMO = addrDefMI.getOperand(i);
			const MachineOperand& MbMO = addrDefMI.getOperand(i+1);
			auto valDef = MRI.getUniqueVRegDef(ValMO.getReg());
			assert(valDef);
			auto ValMOSelected = rewrite_G_PTR_ADD_exprToIndexADD(MF, MRI,
									MIRB, baseAddrDefiningReg, indexWidth, itemSize, *valDef,
									replacements);
			if (!ValMOSelected.isReg()) {
				MIRB.setInsertPt(*MF.begin(), MF.begin()->terminators().begin());
				if (ValMOSelected.isImm()) {
					 // convert phi operand from imm to reg format (because lowering (PHIElimination and others) of phi requires it)
					Register indexReg = MRI.createGenericVirtualRegister(
							LLT::scalar(indexWidth));
					auto cImmMIB = MIRB.buildConstant(indexReg, APInt(indexWidth, ValMOSelected.getImm()));
					assert(constrainInstRegOperands(*cImmMIB.getInstr(), TII, TRI, RBI));
					ValMOSelected =  MachineOperand::CreateReg(indexReg, false);
				} else {
					errs() << addrDefMI << "\n";
					errs() << ValMOSelected << "\n";
					llvm_unreachable("Unknown type of operator for phi for index");
				}
			}
			indexPhiMIB.addUse(ValMOSelected.getReg());
			indexPhiMIB.add(MbMO);
			//selectInstrArg(MF, indexPhiMIB, MRI, ValMOSelected);
			//MachineOperand _MbMO  = MbMO;
			//selectInstrArg(MF, indexPhiMIB, MRI, _MbMO);
		}
		assert(constrainInstRegOperands(*indexPhiMIB.getInstr(), TII, TRI, RBI));

		return MachineOperand::CreateReg(indexReg, false);
	}
	case TargetOpcode::G_CONSTANT: {
		Register indexReg = MRI.createGenericVirtualRegister(
				LLT::scalar(indexWidth));
		auto v = addrDefMI.getOperand(1).getCImm()->getValue();
		if (isPow2(itemSize)) {
			size_t offset = log2ceil(itemSize);
			v = v.extractBits(indexWidth, offset);
		} else {
			llvm_unreachable(
					"NotImplemented, extract the multiplier from the index");
		}
		auto cImmMIB = MIRB.buildConstant(indexReg, v);
		assert(constrainInstRegOperands(*cImmMIB.getInstr(), TII, TRI, RBI));
		return MachineOperand::CreateReg(indexReg, false);
	}
	case TargetOpcode::G_GLOBAL_VALUE:
	case HwtFpga::HWTFPGA_GLOBAL_VALUE:
	case HwtFpga::HWTFPGA_ARG_GET: {
		if (addrDefMI.getOperand(0).getReg() != baseAddrDefiningReg) {
			auto& F = MIRB.getMF();
			F.dump();
			assert(addrDefMI.getOperand(0).getReg() == baseAddrDefiningReg); // there should be only one
		}
		return MachineOperand::CreateImm(0);
	}
	default:
		errs() << "Address operand defined by: " << addrDefMI << "\n";
		llvm_unreachable(
				"Unknown instruction specifying address for load or store");
	}
}

bool HwtFpgaTargetInstructionSelector::select_G_LOAD_or_G_STORE(
		MachineFunction &MF, MachineRegisterInfo &MRI, MachineIRBuilder &MIRB,
		MachineInstr &MI) {

	auto Opc = MI.getOpcode();
	unsigned NewOpc;
	switch (Opc) {
	case TargetOpcode::G_LOAD:
		NewOpc = HwtFpga::HWTFPGA_CLOAD;
		break;
	case TargetOpcode::G_STORE:
		NewOpc = HwtFpga::HWTFPGA_CSTORE;
		break;
	default:
		llvm_unreachable(nullptr);
	}
	//for (auto MO: I.memoperands()) {
	//	MO->getAAInfo()
	//}
	// resolve addr, index
	MachineOperand &addrMO = MI.getOperand(1);
	assert(
			addrMO.isReg()
					&& "Must be the register because we do not have global address space and we can not just dereference address constant.");
	assert(
			MRI.hasOneDef(addrMO.getReg())
					&& "Otherwise not implemented, it is required to rewrite address mux to multiple store/load instructions.");
	// val/dst, addr, index, cond
	auto MIB = MIRB.buildInstr(NewOpc);
	selectInstrArg(MF, MIB, MRI, MI.getOperand(0)); // val/dst - copy as it is

	MachineInstr *addrDef = MRI.getOneDef(addrMO.getReg())->getParent();
	Type * elmT;
	size_t indexWidth;
	MachineInstr* ioDefiningInstr;
	std::tie(elmT, indexWidth, ioDefiningInstr) = hwtHls::getLoadOrStoreElementType(MRI, MI);
	const DataLayout &DL = MF.getFunction().getParent()->getDataLayout();
	TypeSize itemSize = elmT ? DL.getTypeAllocSize(elmT) : MRI.getType(MI.getOperand(0).getReg()).getSizeInBytes();

	std::map<Register, Register> replacements;
	MachineOperand indexMO = rewrite_G_PTR_ADD_exprToIndexADD(MF, MRI, MIRB, ioDefiningInstr->getOperand(0).getReg(), indexWidth, itemSize, *addrDef, replacements);
	MIB.addUse(ioDefiningInstr->getOperand(0).getReg()); // base addr
	selectInstrArg(MF, MIB, MRI, indexMO); // index
	auto dst = MI.getOperand(0).getReg();
	MIB.addImm(MRI.getType(dst).getSizeInBits()); // add dstWidth/val width
	MIB.addImm(1); // cond
	MIB.cloneMemRefs(MI); // copy part behind :: in "G_LOAD %0:anyregcls :: (volatile load (s4) from %ir.dataIn)"

	return finalizeReplacementOfInstruction(MIB, MI);
}

bool HwtFpgaTargetInstructionSelector::select_G_SHL(
		MachineRegisterInfo &MRI, MachineIRBuilder &MIRB, MachineInstr &I) {
	auto &Context = MF->getFunction().getContext();
	auto &lhs = I.getOperand(1);
	auto &rhs = I.getOperand(2);
	ConstantInt *lhsConst = machineOperandTryGetConst(Context, MRI, lhs);
	ConstantInt *rhsConst = machineOperandTryGetConst(Context, MRI, rhs);
	if (lhsConst && rhsConst) {
		// if lhs and rhs are constants we resolve immediately
		APInt v = lhsConst->getValue();
		MachineInstrBuilder MIB = MIRB.buildConstant(I.getOperand(0).getReg(),
				v << rhsConst->getValue());
		return finalizeReplacementOfInstruction(MIB, I);

	} else if (rhsConst) {
		// if rhs is constant we convert this to a concatenation with zeros on right (lower) side
		MachineInstrBuilder MIB0 = MIRB.buildInstr(
				HwtFpga::HWTFPGA_EXTRACT);
		unsigned paddingWidth = rhsConst->getZExtValue();
		APInt padding(paddingWidth, 0);
		auto *paddingCI = ConstantInt::get(Context, padding);
		unsigned dstWidth =
				MRI.getType(I.getOperand(0).getReg()).getSizeInBits();
		// dst, src, offset, dstWidth
		Register upperBits = MRI.createGenericVirtualRegister(
				LLT::scalar(dstWidth - paddingWidth));
		MIB0.addDef(upperBits);
		selectInstrArg(*MF, MIB0, MRI, I.getOperand(1));
		// lhs
		MIB0.addImm(0);
		MIB0.addImm(dstWidth - paddingWidth);
		if (!constrainInstRegOperands(*MIB0.getInstr(), TII, TRI, RBI))
			return false;

		MachineInstrBuilder MIB = MIRB.buildInstr(
				HwtFpga::HWTFPGA_MERGE_VALUES);
		MIB.add(I.getOperand(0)); // dst
		MIB.addCImm(paddingCI);
		MIB.addReg(upperBits); // lhs
		MIB.addImm(paddingWidth);
		MIB.addImm(dstWidth - paddingWidth);
		return finalizeReplacementOfInstruction(MIB, I);

	} else if (lhsConst) {
		// if lhs is constant we generate mux for all possible constant values of the shift
		return false;
	} else {
		// if lhs and rhs are not constants we have to create mux for every possible value
		return false;
	}
}

bool HwtFpgaTargetInstructionSelector::select_G_TRUNC(
		MachineRegisterInfo &MRI, MachineIRBuilder &MIRB, MachineInstr &I) {
	auto &Context = MF->getFunction().getContext();
	auto &vOp = I.getOperand(1);
	ConstantInt *vConst = machineOperandTryGetConst(Context, MRI, vOp);
	unsigned dstWidth = MRI.getType(I.getOperand(0).getReg()).getSizeInBits();
	if (vConst) {
		// directly resolve to constant
		APInt v = vConst->getValue().trunc(dstWidth);
		MachineInstrBuilder MIB = MIRB.buildConstant(I.getOperand(0).getReg(), v);
		return finalizeReplacementOfInstruction(MIB, I);
	} else {
		// select as bit slice
		MachineInstrBuilder MIB0 = MIRB.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
		MIB0.addDef(I.getOperand(0).getReg());
		selectInstrArg(*MF, MIB0, MRI, vOp);
		MIB0.addImm(0);
		MIB0.addImm(dstWidth);
		return finalizeReplacementOfInstruction(MIB0, I);
	}

}
bool HwtFpgaTargetInstructionSelector::select_G_SHR(
		MachineRegisterInfo &MRI, MachineIRBuilder &MIRB, MachineInstr &I,
		bool isArithmetic) {
	auto &Context = MF->getFunction().getContext();
	auto &lhs = I.getOperand(1);
	auto &rhs = I.getOperand(2);
	ConstantInt *lhsConst = machineOperandTryGetConst(Context, MRI, lhs);
	ConstantInt *rhsConst = machineOperandTryGetConst(Context, MRI, rhs);
	if (lhsConst && rhsConst) {
		// if lhs and rhs are constants we resolve immediately
		APInt v = lhsConst->getValue();
		v = isArithmetic ?
				v.ashr(rhsConst->getValue()) : v.lshr(rhsConst->getValue());
		MachineInstrBuilder MIB = MIRB.buildConstant(I.getOperand(0).getReg(),
				v);
		return finalizeReplacementOfInstruction(MIB, I);

	} else if (rhsConst) {
		// if rhs is constant we convert this to a concatenation with zeros or MSBs on left (upper) side

		unsigned prefixWidth = rhsConst->getZExtValue();
		assert(prefixWidth > 0);

		hwtHls::CImmOrReg prefix(nullptr);
		if (isArithmetic) {
			auto msb = _getSelectedMsb(MIRB, MRI, lhs);
			if (!msb.has_value())
				return false;
			prefix.reg = msb.value();
		} else {
			APInt padding(prefixWidth, 0);
			prefix.c = ConstantInt::get(Context, padding);
		}

		unsigned srcWidth = MRI.getType(lhs.getReg()).getSizeInBits();
		// select upper bits of original lhs based on shift amount
		MachineInstrBuilder MIB0 = MIRB.buildInstr(
				HwtFpga::HWTFPGA_EXTRACT);
		Register lshSlice = MRI.createGenericVirtualRegister(LLT::scalar(1));
		MIB0.addDef(lshSlice);
		selectInstrArg(*MF, MIB0, MRI, lhs);
		MIB0.addImm(prefixWidth);
		unsigned lshSliceWidth = srcWidth - prefixWidth;
		MIB0.addImm(lshSliceWidth);

		MachineInstrBuilder MIB = MIRB.buildInstr(
				HwtFpga::HWTFPGA_MERGE_VALUES);
		MIB.add(I.getOperand(0)); // dst
		MIB.addUse(lshSlice);
		if (isArithmetic) {
			for (unsigned i = 0; i < prefixWidth; i++) {
				MIB.addReg(prefix.reg);
			}
			MIB.addImm(lshSliceWidth);
			for (unsigned i = 0; i < prefixWidth; i++) {
				MIB.addImm(1);
			}
		} else {
			prefix.addAsUse(MIB);
			MIB.addImm(lshSliceWidth);
			MIB.addImm(prefixWidth);
		}
		return finalizeReplacementOfInstruction(MIB, I);

	} else if (lhsConst) {
		// if lhs is constant we generate mux for all possible constant values of the shift
		return false;
		//assert(false && "NotImplemented");
	} else {
		// if lhs and rhs are not constants we have to create mux for every possible value
		return false;
		//assert(false && "NotImplemented");
	}
}

std::optional<Register> HwtFpgaTargetInstructionSelector::_getSelectedMsb(
		MachineIRBuilder &MIRB, MachineRegisterInfo &MRI,
		MachineOperand inputMo) {
	unsigned srcWidth = MRI.getType(inputMo.getReg()).getSizeInBits();
	MachineInstrBuilder msbMIB = MIRB.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
	// dst, src, offset, dstWidth
	Register msb = MRI.createGenericVirtualRegister(LLT::scalar(1));
	msbMIB.addDef(msb);
	selectInstrArg(*MF, msbMIB, MRI, inputMo);
	// lhs
	msbMIB.addImm(srcWidth - 1);
	msbMIB.addImm(1);
	if (!constrainInstRegOperands(*msbMIB.getInstr(), TII, TRI, RBI))
		return {};
	return msb;
}

/*
 * Convert G_SEXT to concatenation of msb bits and original src.
 * */
bool HwtFpgaTargetInstructionSelector::select_G_SEXT(
		MachineRegisterInfo &MRI, MachineIRBuilder &MIRB, MachineInstr &I) {
	auto &Op0 = I.getOperand(0);
	unsigned dstWidth = MRI.getType(Op0.getReg()).getSizeInBits();
	unsigned srcWidth = MRI.getType(I.getOperand(1).getReg()).getSizeInBits();
	// add leading 0s
	unsigned prefixWidth = dstWidth - srcWidth;

	std::optional<Register> msb = _getSelectedMsb(MIRB, MRI, I.getOperand(1));
	if (!msb.has_value())
		return false;
	MachineInstrBuilder MIB = MIRB.buildInstr(
			HwtFpga::HWTFPGA_MERGE_VALUES);
	MIB.addDef(Op0.getReg(), Op0.getTargetFlags());
	selectInstrArg(*MF, MIB, MRI, I.getOperand(1));
	for (unsigned i = 0; i < prefixWidth; i++) {
		MIB.addReg(msb.value());
	}
	MIB.addImm(srcWidth);
	for (unsigned i = 0; i < prefixWidth; i++) {
		MIB.addImm(1);
	}
	return finalizeReplacementOfInstruction(MIB, I);
}
/*
 * Convert G_ZEXT to concatenation of zeros and original src.
 * */
bool HwtFpgaTargetInstructionSelector::select_G_ZEXT(
		MachineRegisterInfo &MRI, MachineIRBuilder &MIRB, MachineInstr &I) {
	MachineInstrBuilder MIB = MIRB.buildInstr(
			HwtFpga::HWTFPGA_MERGE_VALUES);
	auto &Op0 = I.getOperand(0);
	MIB.addDef(Op0.getReg(), Op0.getTargetFlags());
	unsigned dstWidth = MRI.getType(Op0.getReg()).getSizeInBits();
	unsigned srcWidth = MRI.getType(I.getOperand(1).getReg()).getSizeInBits();
	// add leading 0s
	auto &C = MF->getFunction().getContext();
	unsigned PrefixWidth = dstWidth - srcWidth;
	APInt _Prefix(PrefixWidth, 0);
	auto *Prefix = ConstantInt::get(C, _Prefix);
	selectInstrArg(*MF, MIB, MRI, I.getOperand(1));
	MIB.addCImm(Prefix);
	MIB.addImm(srcWidth);
	MIB.addImm(PrefixWidth);
	return finalizeReplacementOfInstruction(MIB, I);
}

namespace llvm {
InstructionSelector*
createHwtFpgaInstructionSelector(const HwtFpgaTargetMachine &TM,
		HwtFpgaTargetSubtarget &Subtarget,
		HwtFpgaRegisterBankInfo &RBI) {
	return new HwtFpgaTargetInstructionSelector(TM, Subtarget, RBI);
}
} // end namespace llvm
