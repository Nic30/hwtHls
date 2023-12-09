#include <hwtHls/llvm/targets/machineInstrUtils.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/TargetSubtargetInfo.h>
#include <llvm/CodeGen/TargetRegisterInfo.h>

using namespace llvm;

namespace hwtHls {
static const MachineFunction *getMFIfAvailable(const MachineOperand &MO) {
  if (const MachineInstr *MI = MO.getParent())
    if (const MachineBasicBlock *MBB = MI->getParent())
      if (const MachineFunction *MF = MBB->getParent())
        return MF;
  return nullptr;
}

bool MachineOperand_isIdenticalTo_ignoringFlags(const llvm::MachineOperand &This, const llvm::MachineOperand &Other) {
  if (This.getType() != Other.getType() ||
		  This.getTargetFlags() != Other.getTargetFlags())
    return false;

  switch (This.getType()) {
  case MachineOperand::MO_Register:
    return This.getReg() == Other.getReg() &&
           This.getSubReg() == Other.getSubReg();
  case MachineOperand::MO_Immediate:
    return This.getImm() == Other.getImm();
  case MachineOperand::MO_CImmediate:
    return This.getCImm() == Other.getCImm();
  case MachineOperand::MO_FPImmediate:
    return This.getFPImm() == Other.getFPImm();
  case MachineOperand::MO_MachineBasicBlock:
    return This.getMBB() == Other.getMBB();
  case MachineOperand::MO_FrameIndex:
    return This.getIndex() == Other.getIndex();
  case MachineOperand::MO_ConstantPoolIndex:
  case MachineOperand::MO_TargetIndex:
    return This.getIndex() == Other.getIndex() && This.getOffset() == Other.getOffset();
  case MachineOperand::MO_JumpTableIndex:
    return This.getIndex() == Other.getIndex();
  case MachineOperand::MO_GlobalAddress:
    return This.getGlobal() == Other.getGlobal() && This.getOffset() == Other.getOffset();
  case MachineOperand::MO_ExternalSymbol:
    return strcmp(This.getSymbolName(), Other.getSymbolName()) == 0 &&
    		This.getOffset() == Other.getOffset();
  case MachineOperand::MO_BlockAddress:
    return This.getBlockAddress() == Other.getBlockAddress() &&
           This.getOffset() == Other.getOffset();
  case MachineOperand::MO_RegisterMask:
  case MachineOperand::MO_RegisterLiveOut: {
    // Shallow compare of the two RegMasks
    const uint32_t *RegMask = This.getRegMask();
    const uint32_t *OtherRegMask = Other.getRegMask();
    if (RegMask == OtherRegMask)
      return true;

    if (const MachineFunction *MF = getMFIfAvailable(This)) {
      const TargetRegisterInfo *TRI = MF->getSubtarget().getRegisterInfo();
      unsigned RegMaskSize = MachineOperand::getRegMaskSize(TRI->getNumRegs());
      // Deep compare of the two RegMasks
      return std::equal(RegMask, RegMask + RegMaskSize, OtherRegMask);
    }
    // We don't know the size of the RegMask, so we can't deep compare the two
    // reg masks.
    return false;
  }
  case MachineOperand::MO_MCSymbol:
    return This.getMCSymbol() == Other.getMCSymbol();
  case MachineOperand::MO_DbgInstrRef:
    return This.getInstrRefInstrIndex() == Other.getInstrRefInstrIndex() &&
           This.getInstrRefOpIndex() == Other.getInstrRefOpIndex();
  case MachineOperand::MO_CFIIndex:
    return This.getCFIIndex() == Other.getCFIIndex();
  case MachineOperand::MO_Metadata:
    return This.getMetadata() == Other.getMetadata();
  case MachineOperand::MO_IntrinsicID:
    return This.getIntrinsicID() == Other.getIntrinsicID();
  case MachineOperand::MO_Predicate:
    return This.getPredicate() == Other.getPredicate();
  case MachineOperand::MO_ShuffleMask:
    return This.getShuffleMask() == Other.getShuffleMask();
  }
  llvm_unreachable("Invalid machine operand type");
}

}
