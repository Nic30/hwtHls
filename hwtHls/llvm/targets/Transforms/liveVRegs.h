#pragma once

#include <llvm/ADT/SparseSet.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/TargetRegisterInfo.h>
#include <llvm/MC/MCRegister.h>
#include <llvm/MC/MCRegisterInfo.h>

#include <cassert>
#include <utility>

#include <hwtHls/llvm/targets/Analysis/VRegLiveins.h>

namespace llvm {
class MachineInstr;
class MachineFunction;
class MachineOperand;
class MachineRegisterInfo;
class raw_ostream;
}

namespace hwtHls {

// An equivalent of llvm::LiveVRegs used to track liveness for virtual registers

/// A set of virtual registers with utility functions to track liveness
/// when walking backward/forward through a basic block.
class LiveVRegs {
  const llvm::TargetRegisterInfo *TRI = nullptr;
  const HwtHlsVRegLiveins * VRegLiveins = nullptr;
  using RegisterSet = std::set<llvm::Register>;
  RegisterSet LiveRegs;

public:
  /// Constructs an unitialized set. init() needs to be called to initialize it.
  LiveVRegs() = default;

  /// Constructs and initializes an empty set.
  LiveVRegs(const llvm::TargetRegisterInfo &TRI) : TRI(&TRI) {
    //LiveRegs.setUniverse(TRI.getNumRegs());
  }

  LiveVRegs(const LiveVRegs&) = delete;
  LiveVRegs &operator=(const LiveVRegs&) = delete;

  /// (re-)initializes and clears the set.
  void init(const llvm::TargetRegisterInfo &TRI, HwtHlsVRegLiveins & VRegLiveins) {
    this->TRI = &TRI;
    this->VRegLiveins = &VRegLiveins;
    LiveRegs.clear();
    //LiveRegs.setUniverse(TRI.getNumRegs());
  }

  /// Clears the set.
  void clear() { LiveRegs.clear(); }

  /// Returns true if the set is empty.
  bool empty() const { return LiveRegs.empty(); }

  /// Adds a virtual register and all its sub-registers to the set.
  void addReg(llvm::Register Reg) {
    assert(TRI && "LiveVRegs is not initialized.");
    LiveRegs.insert(Reg);
  }

  /// Removes a virtual register, all its sub-registers, and all its
  /// super-registers from the set.
  void removeReg(llvm::Register Reg) {
    assert(TRI && "LiveVRegs is not initialized.");
    LiveRegs.erase(Reg);
  }

  /// Removes virtual registers clobbered by the regmask operand \p MO.
  void removeRegsInMask(const llvm::MachineOperand &MO,
		  llvm::SmallVectorImpl<std::pair<llvm::Register, const llvm::MachineOperand*>> *Clobbers =
        nullptr);

  /// Returns true if register \p Reg is contained in the set. This also
  /// works if only the super register of \p Reg has been defined, because
  /// addReg() always adds all sub-registers to the set as well.
  /// Note: Returns false if just some sub registers are live, use available()
  /// when searching a free register.
  bool contains(llvm::Register Reg) const { return LiveRegs.count(Reg); }

  /// Returns true if register \p Reg and no aliasing register is in the set.
  bool available(const llvm::MachineRegisterInfo &MRI, llvm::Register Reg) const;

  /// Remove defined registers and regmask kills from the set.
  void removeDefs(const llvm::MachineInstr &MI);

  /// Add uses to the set.
  void addUses(const llvm::MachineInstr &MI);

  /// Simulates liveness when stepping backwards over an instruction(bundle).
  /// Remove Defs, add uses. This is the recommended way of calculating
  /// liveness.
  void stepBackward(const llvm::MachineInstr &MI);

  /// Simulates liveness when stepping forward over an instruction(bundle).
  /// Remove killed-uses, add defs. This is the not recommended way, because it
  /// depends on accurate kill flags. If possible use stepBackward() instead of
  /// this function. The clobbers set will be the list of registers either
  /// defined or clobbered by a regmask.  The operand will identify whether this
  /// is a regmask or register operand.
  void stepForward(const llvm::MachineInstr &MI,
		  llvm::SmallVectorImpl<std::pair<llvm::Register, const llvm::MachineOperand*>> &Clobbers);

  /// Adds all live-in registers of basic block \p MBB.
  /// Live in registers are the registers in the blocks live-in list and the
  /// pristine registers.
  void addLiveIns(const llvm::MachineBasicBlock &MBB);

  /// Adds all live-in registers of basic block \p MBB but skips pristine
  /// registers.
  void addLiveInsNoPristines(const llvm::MachineBasicBlock &MBB);

  /// Adds all live-out registers of basic block \p MBB.
  /// Live out registers are the union of the live-in registers of the successor
  /// blocks and pristine registers. Live out registers of the end block are the
  /// callee saved registers.
  /// If a register is not added by this method, it is guaranteed to not be
  /// live out from MBB, although a sub-register may be. This is true
  /// both before and after regalloc.
  void addLiveOuts(const llvm::MachineBasicBlock &MBB);

  /// Adds all live-out registers of basic block \p MBB but skips pristine
  /// registers.
  void addLiveOutsNoPristines(const llvm::MachineBasicBlock &MBB);

  using const_iterator = RegisterSet::const_iterator;

  const_iterator begin() const { return LiveRegs.begin(); }
  const_iterator end() const { return LiveRegs.end(); }

  /// Prints the currently live registers to \p OS.
  void print(llvm::raw_ostream &OS) const;

  /// Dumps the currently live registers to the debug output.
  void dump() const;

private:
  /// Adds live-in registers from basic block \p MBB, taking associated
  /// lane masks into consideration.
  void addBlockLiveIns(const llvm::MachineBasicBlock &MBB);

  /// Adds pristine registers. Pristine registers are callee saved registers
  /// that are unused in the function.
  void addPristines(const llvm::MachineFunction &MF);
};

inline llvm::raw_ostream &operator<<(llvm::raw_ostream &OS, const LiveVRegs& LR) {
  LR.print(OS);
  return OS;
}


void recomputeVRegLivenessFlags(HwtHlsVRegLiveins & VRegLiveins, llvm::MachineBasicBlock &MBB);


}
