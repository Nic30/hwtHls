//===- EarlyMachineCopyPropagation.cpp - Same as original MachineCopyPropagation.cpp but works on VReg level ---------===//
//
#include "EarlyMachineCopyPropagation.h"
#include <llvm/ADT/DenseMap.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallSet.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/Statistic.h>
#include <llvm/ADT/iterator_range.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/CodeGen/MachineOperand.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/TargetInstrInfo.h>
#include <llvm/CodeGen/TargetRegisterInfo.h>
#include <llvm/CodeGen/TargetSubtargetInfo.h>
#include <llvm/InitializePasses.h>
#include <llvm/Support/Debug.h>
#include <llvm/Support/DebugCounter.h>
#include <llvm/Support/raw_ostream.h>
#include <cassert>
#include <iterator>

using namespace llvm;

#define DEBUG_TYPE "earlymachine-cp"

STATISTIC(NumDeletes, "Number of dead copies deleted");
STATISTIC(NumCopyForwards, "Number of copy uses forwarded");
STATISTIC(NumCopyBackwardPropagated, "Number of copy defs backward propagated");
DEBUG_COUNTER(FwdCounter, "machine-cp-fwd",
              "Controls which register COPYs are forwarded");

namespace {

static bool TRI_isSubRegister(const TargetRegisterInfo &TRI, Register r0, Register r1) {
	return r0 == r1 || (r0.isPhysical() && r1.isPhysical() && TRI.isSubRegister(r0, r1));
}

class CopyTracker {
  struct CopyInfo {
    MachineInstr *MI;
    SmallVector<Register, 4> DefRegs;
    bool Avail;
  };

  DenseMap<Register, CopyInfo> Copies;
  bool isSubRegisterEq(const TargetRegisterInfo &TRI, Register r0, Register r1) {
  	return TRI_isSubRegister(TRI, r0, r1);
  }

public:
  /// Mark all of the given registers and their subregisters as unavailable for
  /// copying.
  void markRegsUnavailable(ArrayRef<Register> Regs,
                           const TargetRegisterInfo &TRI) {
    for (Register Reg : Regs) {
      // Source of copy is no longer available for propagation.
        auto CI = Copies.find(Reg);
        if (CI != Copies.end())
          CI->second.Avail = false;
      }
  }

  /// Remove register from copy maps.
  void invalidateRegister(Register Reg, const TargetRegisterInfo &TRI) {
    // Since Reg might be a subreg of some registers, only invalidate Reg is not
    // enough. We have to find the COPY defines Reg or registers defined by Reg
    // and invalidate all of them.
    SmallSet<Register, 8> RegsToInvalidate;
    RegsToInvalidate.insert(Reg);
      auto I = Copies.find(Reg);
      if (I != Copies.end()) {
        if (MachineInstr *MI = I->second.MI) {
          RegsToInvalidate.insert(MI->getOperand(0).getReg());
          RegsToInvalidate.insert(MI->getOperand(1).getReg());
        }
        RegsToInvalidate.insert(I->second.DefRegs.begin(),
                                I->second.DefRegs.end());
      }
    for (Register InvalidReg : RegsToInvalidate)
        Copies.erase(InvalidReg);
  }

  /// Clobber a single register, removing it from the tracker's copy maps.
  void clobberRegister(Register Reg, const TargetRegisterInfo &TRI) {
      auto I = Copies.find(Reg);
      if (I != Copies.end()) {
        // When we clobber the source of a copy, we need to clobber everything
        // it defined.
        markRegsUnavailable(I->second.DefRegs, TRI);
        // When we clobber the destination of a copy, we need to clobber the
        // whole register it defined.
        if (MachineInstr *MI = I->second.MI)
          markRegsUnavailable({MI->getOperand(0).getReg()}, TRI);
        // Now we can erase the copy.
        Copies.erase(I);
      }
  }

  /// Add this copy's registers into the tracker's copy maps.
  void trackCopy(MachineInstr *MI, const TargetRegisterInfo &TRI) {
    assert(MI->isCopy() && "Tracking non-copy?");

    Register Def = MI->getOperand(0).getReg();
    Register Src = MI->getOperand(1).getReg();

    // Remember Def is defined by the copy.
    Copies[Def] = {MI, {}, true};

    // Remember source that's copied to Def. Once it's clobbered, then
    // it's no longer available for copy propagation.
    auto I = Copies.insert({Src, {nullptr, {}, false}});
    auto &Copy = I.first->second;
    if (!is_contained(Copy.DefRegs, Def))
      Copy.DefRegs.push_back(Def);
  }

  bool hasAnyCopies() {
    return !Copies.empty();
  }

  MachineInstr *findCopyForUnit(Register RegUnit,
                                const TargetRegisterInfo &TRI,
                                bool MustBeAvailable = false) {
    auto CI = Copies.find(RegUnit);
    if (CI == Copies.end())
      return nullptr;
    if (MustBeAvailable && !CI->second.Avail)
      return nullptr;
    return CI->second.MI;
  }

  MachineInstr *findCopyDefViaUnit(Register RegUnit,
                                   const TargetRegisterInfo &TRI) {
    auto CI = Copies.find(RegUnit);
    if (CI == Copies.end())
      return nullptr;
    if (CI->second.DefRegs.size() != 1)
      return nullptr;
    return findCopyForUnit(CI->second.DefRegs[0], TRI, true);
  }

  MachineInstr *findAvailBackwardCopy(MachineInstr &I, Register Reg,
                                      const TargetRegisterInfo &TRI) {
    MachineInstr *AvailCopy = findCopyDefViaUnit(Reg, TRI);
    if (!AvailCopy ||
        !isSubRegisterEq(TRI, AvailCopy->getOperand(1).getReg(), Reg))
      return nullptr;

    for (const MachineInstr &MI :
         make_range(AvailCopy->getReverseIterator(), I.getReverseIterator()))
      for (const MachineOperand &MO : MI.operands())
        if (MO.isRegMask())
          llvm_unreachable("Not implemented");

    return AvailCopy;
  }

  MachineInstr *findAvailCopy(MachineInstr &DestCopy, Register Reg,
                              const TargetRegisterInfo &TRI) {
    // We check the first RegUnit here, since we'll only be interested in the
    // copy if it copies the entire register anyway.
    MachineInstr *AvailCopy =
        findCopyForUnit(Reg, TRI, /*MustBeAvailable=*/true);
    if (!AvailCopy ||
        !isSubRegisterEq(TRI, AvailCopy->getOperand(0).getReg(), Reg))
      return nullptr;

    // Check that the available copy isn't clobbered by any regmasks between
    // itself and the destination.
    for (const MachineInstr &MI :
         make_range(AvailCopy->getIterator(), DestCopy.getIterator()))
      for (const MachineOperand &MO : MI.operands())
        if (MO.isRegMask())
            llvm_unreachable("Not implemented");

    return AvailCopy;
  }

  void clear() {
    Copies.clear();
  }
};

class EarlyMachineCopyPropagation : public MachineFunctionPass {
  const TargetRegisterInfo *TRI;
  const TargetInstrInfo *TII;
  const MachineRegisterInfo *MRI;

public:
  static char ID; // Pass identification, replacement for typeid

  EarlyMachineCopyPropagation() : MachineFunctionPass(ID) {
    initializeEarlyMachineCopyPropagationPass(*PassRegistry::getPassRegistry());
  }

  void getAnalysisUsage(AnalysisUsage &AU) const override {
    AU.setPreservesCFG();
    MachineFunctionPass::getAnalysisUsage(AU);
  }

  bool runOnMachineFunction(MachineFunction &MF) override;

  MachineFunctionProperties getRequiredProperties() const override {
    return MachineFunctionProperties();
  }

private:
  typedef enum { DebugUse = false, RegularUse = true } DebugType;

  void ReadRegister(Register Reg, MachineInstr &Reader, DebugType DT);
  void ForwardCopyPropagateBlock(MachineBasicBlock &MBB);
  void BackwardCopyPropagateBlock(MachineBasicBlock &MBB);
  bool eraseIfRedundant(MachineInstr &Copy, Register Src, Register Def);
  void forwardUses(MachineInstr &MI);
  void propagateDefs(MachineInstr &MI);
  bool isForwardableRegClassCopy(const MachineInstr &Copy,
                                 const MachineInstr &UseI, unsigned UseIdx);
  bool isBackwardPropagatableRegClassCopy(const MachineInstr &Copy,
                                          const MachineInstr &UseI,
                                          unsigned UseIdx);
  bool hasImplicitOverlap(const MachineInstr &MI, const MachineOperand &Use);
  bool hasOverlappingMultipleDef(const MachineInstr &MI,
                                 const MachineOperand &MODef, Register Def);

  /// Candidates for deletion.
  SmallSetVector<MachineInstr *, 8> MaybeDeadCopies;

  /// Multimap tracking debug users in current BB
  DenseMap<MachineInstr *, SmallSet<MachineInstr *, 2>> CopyDbgUsers;

  CopyTracker Tracker;

  bool Changed;
};

} // end anonymous namespace

char EarlyMachineCopyPropagation::ID = 0;

char &hwtHls::EarlyMachineCopyPropagationID = EarlyMachineCopyPropagation::ID;

INITIALIZE_PASS(EarlyMachineCopyPropagation, DEBUG_TYPE,
                "Early Machine Copy Propagation Pass", false, false)

void EarlyMachineCopyPropagation::ReadRegister(Register Reg, MachineInstr &Reader,
                                          DebugType DT) {
  // If 'Reg' is defined by a copy, the copy is no longer a candidate
  // for elimination. If a copy is "read" by a debug user, record the user
  // for propagation.
    if (MachineInstr *Copy = Tracker.findCopyForUnit(Reg, *TRI)) {
      if (DT == RegularUse) {
        LLVM_DEBUG(dbgs() << "EarlyMCP: Copy is used - not dead: "; Copy->dump());
        MaybeDeadCopies.remove(Copy);
      } else {
        CopyDbgUsers[Copy].insert(&Reader);
      }
    }
}

/// Return true if \p PreviousCopy did copy register \p Src to register \p Def.
/// This fact may have been obscured by sub register usage or may not be true at
/// all even though Src and Def are subregisters of the registers used in
/// PreviousCopy. e.g.
/// isNopCopy("ecx = COPY eax", AX, CX) == true
/// isNopCopy("ecx = COPY eax", AH, CL) == false
static bool isNopCopy(const MachineInstr &PreviousCopy, Register Src,
                      Register Def, const TargetRegisterInfo *TRI) {
  Register PreviousSrc = PreviousCopy.getOperand(1).getReg();
  Register PreviousDef = PreviousCopy.getOperand(0).getReg();
  if (Src == PreviousSrc && Def == PreviousDef)
    return true;
  if (!TRI_isSubRegister(*TRI, PreviousSrc, Src))
    return false;
  if (PreviousSrc.isPhysical() && Src.isPhysical() && Def.isPhysical()) {
	  unsigned SubIdx = TRI->getSubRegIndex(PreviousSrc, Src);
	  return SubIdx == TRI->getSubRegIndex(PreviousDef, Def);
  } else {
	  return true;
  }
}

/// Remove instruction \p Copy if there exists a previous copy that copies the
/// register \p Src to the register \p Def; This may happen indirectly by
/// copying the super registers.
bool EarlyMachineCopyPropagation::eraseIfRedundant(MachineInstr &Copy,
                                              Register Src, Register Def) {
  // Search for an existing copy.
  MachineInstr *PrevCopy = Tracker.findAvailCopy(Copy, Def, *TRI);
  if (!PrevCopy)
    return false;

  // Check that the existing copy uses the correct sub registers.
  if (PrevCopy->getOperand(0).isDead())
    return false;
  if (!isNopCopy(*PrevCopy, Src, Def, TRI))
    return false;

  LLVM_DEBUG(dbgs() << "EarlyMCP: copy is a NOP, removing: "; Copy.dump());

  // Copy was redundantly redefining either Src or Def. Remove earlier kill
  // flags between Copy and PrevCopy because the value will be reused now.
  assert(Copy.isCopy());
  Register CopyDef = Copy.getOperand(0).getReg();
  assert(CopyDef == Src || CopyDef == Def);
  for (MachineInstr &MI :
       make_range(PrevCopy->getIterator(), Copy.getIterator()))
    MI.clearRegisterKills(CopyDef, TRI);

  Copy.eraseFromParent();
  Changed = true;
  ++NumDeletes;
  return true;
}

bool EarlyMachineCopyPropagation::isBackwardPropagatableRegClassCopy(
    const MachineInstr &Copy, const MachineInstr &UseI, unsigned UseIdx) {
  Register Def = Copy.getOperand(0).getReg();

  if (const TargetRegisterClass *URC =
          UseI.getRegClassConstraint(UseIdx, TII, TRI))
    return URC->contains(Def);

  // We don't process further if UseI is a COPY, since forward copy propagation
  // should handle that.
  return false;
}

/// Decide whether we should forward the source of \param Copy to its use in
/// \param UseI based on the physical register class constraints of the opcode
/// and avoiding introducing more cross-class COPYs.
bool EarlyMachineCopyPropagation::isForwardableRegClassCopy(const MachineInstr &Copy,
                                                       const MachineInstr &UseI,
                                                       unsigned UseIdx) {

  Register CopySrcReg = Copy.getOperand(1).getReg();

  // If the new register meets the opcode register constraints, then allow
  // forwarding.
  if (const TargetRegisterClass *URC =
          UseI.getRegClassConstraint(UseIdx, TII, TRI))
    return URC->contains(CopySrcReg);

  if (!UseI.isCopy())
    return false;

  const TargetRegisterClass *CopySrcRC =
      TRI->getMinimalPhysRegClass(CopySrcReg);
  const TargetRegisterClass *UseDstRC =
      TRI->getMinimalPhysRegClass(UseI.getOperand(0).getReg());
  const TargetRegisterClass *CrossCopyRC = TRI->getCrossCopyRegClass(CopySrcRC);

  // If cross copy register class is not the same as copy source register class
  // then it is not possible to copy the register directly and requires a cross
  // register class copy. Fowarding this copy without checking register class of
  // UseDst may create additional cross register copies when expanding the copy
  // instruction in later passes.
  if (CopySrcRC != CrossCopyRC) {
    const TargetRegisterClass *CopyDstRC =
        TRI->getMinimalPhysRegClass(Copy.getOperand(0).getReg());

    // Check if UseDstRC matches the necessary register class to copy from
    // CopySrc's register class. If so then forwarding the copy will not
    // introduce any cross-class copys. Else if CopyDstRC matches then keep the
    // copy and do not forward. If neither UseDstRC or CopyDstRC matches then
    // we may need a cross register copy later but we do not worry about it
    // here.
    if (UseDstRC != CrossCopyRC && CopyDstRC == CrossCopyRC)
      return false;
  }

  /// COPYs don't have register class constraints, so if the user instruction
  /// is a COPY, we just try to avoid introducing additional cross-class
  /// COPYs.  For example:
  ///
  ///   RegClassA = COPY RegClassB  // Copy parameter
  ///   ...
  ///   RegClassB = COPY RegClassA  // UseI parameter
  ///
  /// which after forwarding becomes
  ///
  ///   RegClassA = COPY RegClassB
  ///   ...
  ///   RegClassB = COPY RegClassB
  ///
  /// so we have reduced the number of cross-class COPYs and potentially
  /// introduced a nop COPY that can be removed.
  const TargetRegisterClass *SuperRC = UseDstRC;
  for (TargetRegisterClass::sc_iterator SuperRCI = UseDstRC->getSuperClasses();
       SuperRC; SuperRC = *SuperRCI++)
    if (SuperRC->contains(CopySrcReg))
      return true;

  return false;
}

/// Check that \p MI does not have implicit uses that overlap with it's \p Use
/// operand (the register being replaced), since these can sometimes be
/// implicitly tied to other operands.  For example, on AMDGPU:
///
/// V_MOVRELS_B32_e32 %VGPR2, %M0<imp-use>, %EXEC<imp-use>, %VGPR2_VGPR3_VGPR4_VGPR5<imp-use>
///
/// the %VGPR2 is implicitly tied to the larger reg operand, but we have no
/// way of knowing we need to update the latter when updating the former.
bool EarlyMachineCopyPropagation::hasImplicitOverlap(const MachineInstr &MI,
                                                const MachineOperand &Use) {
  for (const MachineOperand &MIUse : MI.uses())
    if (&MIUse != &Use && MIUse.isReg() && MIUse.isImplicit() &&
        MIUse.isUse() && TRI->regsOverlap(Use.getReg(), MIUse.getReg()))
      return true;

  return false;
}

/// For an MI that has multiple definitions, check whether \p MI has
/// a definition that overlaps with another of its definitions.
/// For example, on ARM: umull   r9, r9, lr, r0
/// The umull instruction is unpredictable unless RdHi and RdLo are different.
bool EarlyMachineCopyPropagation::hasOverlappingMultipleDef(
    const MachineInstr &MI, const MachineOperand &MODef, Register Def) {
  for (const MachineOperand &MIDef : MI.defs()) {
    if ((&MIDef != &MODef) && MIDef.isReg() &&
        TRI->regsOverlap(Def, MIDef.getReg()))
      return true;
  }

  return false;
}

/// Look for available copies whose destination register is used by \p MI and
/// replace the use in \p MI with the copy's source register.
void EarlyMachineCopyPropagation::forwardUses(MachineInstr &MI) {
  if (!Tracker.hasAnyCopies())
    return;

  // Look for non-tied explicit vreg uses that have an active COPY
  // instruction that defines the physical register allocated to them.
  // Replace the vreg with the source of the active COPY.
  for (unsigned OpIdx = 0, OpEnd = MI.getNumOperands(); OpIdx < OpEnd;
       ++OpIdx) {
    MachineOperand &MOUse = MI.getOperand(OpIdx);
    // Don't forward into undef use operands since doing so can cause problems
    // with the machine verifier, since it doesn't treat undef reads as reads,
    // so we can end up with a live range that ends on an undef read, leading to
    // an error that the live range doesn't end on a read of the live range
    // register.
    if (!MOUse.isReg() || MOUse.isTied() || MOUse.isUndef() || MOUse.isDef() ||
        MOUse.isImplicit())
      continue;

    if (!MOUse.getReg())
      continue;

    MachineInstr *Copy =
        Tracker.findAvailCopy(MI, MOUse.getReg(), *TRI);
    if (!Copy)
      continue;

    Register CopyDstReg = Copy->getOperand(0).getReg();
    const MachineOperand &CopySrc = Copy->getOperand(1);
    Register CopySrcReg = CopySrc.getReg();

    // FIXME: Don't handle partial uses of wider COPYs yet.
    if (MOUse.getReg() != CopyDstReg) {
      LLVM_DEBUG(
          dbgs() << "EarlyMCP: FIXME! Not forwarding COPY to sub-register use:\n  "
                 << MI);
      continue;
    }

    if (!isForwardableRegClassCopy(*Copy, MI, OpIdx))
      continue;

    if (hasImplicitOverlap(MI, MOUse))
      continue;

    // Check that the instruction is not a copy that partially overwrites the
    // original copy source that we are about to use. The tracker mechanism
    // cannot cope with that.
    if (MI.isCopy() && MI.modifiesRegister(CopySrcReg, TRI) &&
        !MI.definesRegister(CopySrcReg)) {
      LLVM_DEBUG(dbgs() << "EarlyMCP: Copy source overlap with dest in " << MI);
      continue;
    }

    if (!DebugCounter::shouldExecute(FwdCounter)) {
      LLVM_DEBUG(dbgs() << "EarlyMCP: Skipping forwarding due to debug counter:\n  "
                        << MI);
      continue;
    }

    LLVM_DEBUG(dbgs() << "EarlyMCP: Replacing " << printReg(MOUse.getReg(), TRI)
                      << "\n     with " << printReg(CopySrcReg, TRI)
                      << "\n     in " << MI << "     from " << *Copy);

    MOUse.setReg(CopySrcReg);
    MOUse.setIsUndef(CopySrc.isUndef());

    LLVM_DEBUG(dbgs() << "EarlyMCP: After replacement: " << MI << "\n");

    // Clear kill markers that may have been invalidated.
    for (MachineInstr &KMI :
         make_range(Copy->getIterator(), std::next(MI.getIterator())))
      KMI.clearRegisterKills(CopySrcReg, TRI);

    ++NumCopyForwards;
    Changed = true;
  }
}

void EarlyMachineCopyPropagation::ForwardCopyPropagateBlock(MachineBasicBlock &MBB) {
  LLVM_DEBUG(dbgs() << "EarlyMCP: ForwardCopyPropagateBlock " << MBB.getName()
                    << "\n");

  for (MachineInstr &MI : llvm::make_early_inc_range(MBB)) {
    // Analyze copies (which don't overlap themselves).
    if (MI.isCopy() && !TRI->regsOverlap(MI.getOperand(0).getReg(),
                                         MI.getOperand(1).getReg())) {
      Register Def = MI.getOperand(0).getReg();
      Register Src = MI.getOperand(1).getReg();

      // The two copies cancel out and the source of the first copy
      // hasn't been overridden, eliminate the second one. e.g.
      //  %ecx = COPY %eax
      //  ... nothing clobbered eax.
      //  %eax = COPY %ecx
      // =>
      //  %ecx = COPY %eax
      //
      // or
      //
      //  %ecx = COPY %eax
      //  ... nothing clobbered eax.
      //  %ecx = COPY %eax
      // =>
      //  %ecx = COPY %eax
      if (eraseIfRedundant(MI, Def, Src) || eraseIfRedundant(MI, Src, Def))
        continue;

      forwardUses(MI);

      // Src may have been changed by forwardUses()
      Src = MI.getOperand(1).getReg();

      // If Src is defined by a previous copy, the previous copy cannot be
      // eliminated.
      ReadRegister(Src, MI, RegularUse);
      for (const MachineOperand &MO : MI.implicit_operands()) {
        if (!MO.isReg() || !MO.readsReg())
          continue;
        Register Reg = MO.getReg();
        if (!Reg)
          continue;
        ReadRegister(Reg, MI, RegularUse);
      }

      LLVM_DEBUG(dbgs() << "EarlyMCP: Copy is a deletion candidate: "; MI.dump());

      // Copy is now a candidate for deletion.
      MaybeDeadCopies.insert(&MI);

      // If 'Def' is previously source of another copy, then this earlier copy's
      // source is no longer available. e.g.
      // %xmm9 = copy %xmm2
      // ...
      // %xmm2 = copy %xmm0
      // ...
      // %xmm2 = copy %xmm9
      Tracker.clobberRegister(Def, *TRI);
      for (const MachineOperand &MO : MI.implicit_operands()) {
        if (!MO.isReg() || !MO.isDef())
          continue;
        Register Reg = MO.getReg();
        if (!Reg)
          continue;
        Tracker.clobberRegister(Reg, *TRI);
      }

      Tracker.trackCopy(&MI, *TRI);

      continue;
    }

    // Clobber any earlyclobber regs first.
    for (const MachineOperand &MO : MI.operands())
      if (MO.isReg() && MO.isEarlyClobber()) {
        Register Reg = MO.getReg();
        // If we have a tied earlyclobber, that means it is also read by this
        // instruction, so we need to make sure we don't remove it as dead
        // later.
        if (MO.isTied())
          ReadRegister(Reg, MI, RegularUse);
        Tracker.clobberRegister(Reg, *TRI);
      }

    forwardUses(MI);

    // Not a copy.
    SmallVector<Register, 2> Defs;
    const MachineOperand *RegMask = nullptr;
    for (const MachineOperand &MO : MI.operands()) {
      if (MO.isRegMask())
        RegMask = &MO;
      if (!MO.isReg())
        continue;
      Register Reg = MO.getReg();
      if (!Reg)
        continue;

      if (MO.isDef() && !MO.isEarlyClobber()) {
        Defs.push_back(Reg);
        continue;
      } else if (MO.readsReg())
        ReadRegister(Reg, MI, MO.isDebug() ? DebugUse : RegularUse);
    }

    // The instruction has a register mask operand which means that it clobbers
    // a large set of registers.  Treat clobbered registers the same way as
    // defined registers.
    if (RegMask) {
      // Erase any MaybeDeadCopies whose destination register is clobbered.
      for (SmallSetVector<MachineInstr *, 8>::iterator DI =
               MaybeDeadCopies.begin();
           DI != MaybeDeadCopies.end();) {
        MachineInstr *MaybeDead = *DI;
        Register Reg = MaybeDead->getOperand(0).getReg();

        if (!RegMask->clobbersPhysReg(Reg)) {
          ++DI;
          continue;
        }

        LLVM_DEBUG(dbgs() << "EarlyMCP: Removing copy due to regmask clobbering: ";
                   MaybeDead->dump());

        // Make sure we invalidate any entries in the copy maps before erasing
        // the instruction.
        Tracker.clobberRegister(Reg, *TRI);

        // erase() will return the next valid iterator pointing to the next
        // element after the erased one.
        DI = MaybeDeadCopies.erase(DI);
        MaybeDead->eraseFromParent();
        Changed = true;
        ++NumDeletes;
      }
    }

    // Any previous copy definition or reading the Defs is no longer available.
    for (Register Reg : Defs)
      Tracker.clobberRegister(Reg, *TRI);
  }

  // If MBB doesn't have successors, delete the copies whose defs are not used.
  // If MBB does have successors, then conservative assume the defs are live-out
  // since we don't want to trust live-in lists.
  if (MBB.succ_empty()) {
    for (MachineInstr *MaybeDead : MaybeDeadCopies) {
      LLVM_DEBUG(dbgs() << "EarlyMCP: Removing copy due to no live-out succ: ";
                 MaybeDead->dump());

      // Update matching debug values, if any.
      assert(MaybeDead->isCopy());
      Register SrcReg = MaybeDead->getOperand(1).getReg();
      Register DestReg = MaybeDead->getOperand(0).getReg();
      SmallVector<MachineInstr *> MaybeDeadDbgUsers(
          CopyDbgUsers[MaybeDead].begin(), CopyDbgUsers[MaybeDead].end());
      MRI->updateDbgUsersToReg(DestReg, SrcReg,
                               MaybeDeadDbgUsers);

      MaybeDead->eraseFromParent();
      Changed = true;
      ++NumDeletes;
    }
  }

  MaybeDeadCopies.clear();
  CopyDbgUsers.clear();
  Tracker.clear();
}

static bool isBackwardPropagatableCopy(MachineInstr &MI,
                                       const MachineRegisterInfo &MRI) {
  assert(MI.isCopy() && "MI is expected to be a COPY");
  Register Def = MI.getOperand(0).getReg();
  Register Src = MI.getOperand(1).getReg();

  if (!Def || !Src)
    return false;

  return MI.getOperand(1).isKill();
}

void EarlyMachineCopyPropagation::propagateDefs(MachineInstr &MI) {
  if (!Tracker.hasAnyCopies())
    return;

  for (unsigned OpIdx = 0, OpEnd = MI.getNumOperands(); OpIdx != OpEnd;
       ++OpIdx) {
    MachineOperand &MODef = MI.getOperand(OpIdx);

    if (!MODef.isReg() || MODef.isUse())
      continue;

    // Ignore non-trivial cases.
    if (MODef.isTied() || MODef.isUndef() || MODef.isImplicit())
      continue;

    if (!MODef.getReg())
      continue;


    MachineInstr *Copy =
        Tracker.findAvailBackwardCopy(MI, MODef.getReg(), *TRI);
    if (!Copy)
      continue;

    Register Def = Copy->getOperand(0).getReg();
    Register Src = Copy->getOperand(1).getReg();

    if (MODef.getReg() != Src)
      continue;

    if (!isBackwardPropagatableRegClassCopy(*Copy, MI, OpIdx))
      continue;

    if (hasImplicitOverlap(MI, MODef))
      continue;

    if (hasOverlappingMultipleDef(MI, MODef, Def))
      continue;

    LLVM_DEBUG(dbgs() << "EarlyMCP: Replacing " << printReg(MODef.getReg(), TRI)
                      << "\n     with " << printReg(Def, TRI) << "\n     in "
                      << MI << "     from " << *Copy);

    MODef.setReg(Def);

    LLVM_DEBUG(dbgs() << "EarlyMCP: After replacement: " << MI << "\n");
    MaybeDeadCopies.insert(Copy);
    Changed = true;
    ++NumCopyBackwardPropagated;
  }
}

void EarlyMachineCopyPropagation::BackwardCopyPropagateBlock(
    MachineBasicBlock &MBB) {
  LLVM_DEBUG(dbgs() << "EarlyMCP: BackwardCopyPropagateBlock " << MBB.getName()
                    << "\n");

  for (MachineInstr &MI : llvm::make_early_inc_range(llvm::reverse(MBB))) {
    // Ignore non-trivial COPYs.
    if (MI.isCopy() && MI.getNumOperands() == 2 &&
        !TRI->regsOverlap(MI.getOperand(0).getReg(),
                          MI.getOperand(1).getReg())) {

      Register Def = MI.getOperand(0).getReg();
      Register Src = MI.getOperand(1).getReg();

      // Unlike forward cp, we don't invoke propagateDefs here,
      // just let forward cp do COPY-to-COPY propagation.
      if (isBackwardPropagatableCopy(MI, *MRI)) {
        Tracker.invalidateRegister(Src, *TRI);
        Tracker.invalidateRegister(Def, *TRI);
        Tracker.trackCopy(&MI, *TRI);
        continue;
      }
    }

    // Invalidate any earlyclobber regs first.
    for (const MachineOperand &MO : MI.operands())
      if (MO.isReg() && MO.isEarlyClobber()) {
        Register Reg = MO.getReg();
        if (!Reg)
          continue;
        Tracker.invalidateRegister(Reg, *TRI);
      }

    propagateDefs(MI);
    for (const MachineOperand &MO : MI.operands()) {
      if (!MO.isReg())
        continue;

      if (!MO.getReg())
        continue;

      if (MO.isDef())
        Tracker.invalidateRegister(MO.getReg(), *TRI);

      if (MO.readsReg()) {
        if (MO.isDebug()) {
          //  Check if the register in the debug instruction is utilized
          // in a copy instruction, so we can update the debug info if the
          // register is changed.
            if (auto *Copy = Tracker.findCopyDefViaUnit(MO.getReg(), *TRI)) {
              CopyDbgUsers[Copy].insert(&MI);
            }
        } else {
          Tracker.invalidateRegister(MO.getReg(), *TRI);
        }
      }
    }
  }

  for (auto *Copy : MaybeDeadCopies) {

    Register Src = Copy->getOperand(1).getReg();
    Register Def = Copy->getOperand(0).getReg();
    SmallVector<MachineInstr *> MaybeDeadDbgUsers(CopyDbgUsers[Copy].begin(),
                                                  CopyDbgUsers[Copy].end());

    MRI->updateDbgUsersToReg(Src, Def, MaybeDeadDbgUsers);
    Copy->eraseFromParent();
    ++NumDeletes;
  }

  MaybeDeadCopies.clear();
  CopyDbgUsers.clear();
  Tracker.clear();
}

bool EarlyMachineCopyPropagation::runOnMachineFunction(MachineFunction &MF) {
  if (skipFunction(MF.getFunction()))
    return false;

  Changed = false;

  TRI = MF.getSubtarget().getRegisterInfo();
  TII = MF.getSubtarget().getInstrInfo();
  MRI = &MF.getRegInfo();

  for (MachineBasicBlock &MBB : MF) {
    BackwardCopyPropagateBlock(MBB);
    ForwardCopyPropagateBlock(MBB);
  }

  return Changed;
}
