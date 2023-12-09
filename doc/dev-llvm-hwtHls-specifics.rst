HwtHls specific in LLVM based code
==================================

HwtHls uses LLVM as stand alone library and does not modify it.
However specifics require some intrinsic functions () and the TargetMachine (HwtFpga)
can not use llvm PhysReg which complicates basically everything after CodeGenPrepare.


Specifics on IR level
* `hwtHls/llvm/targets/intrinsic`
* Custom compilation pipeline usually explicitly executed using LlvmCompilationBundle
  (no llvm-opt tool everything linked as a Python module and used from Python)
* Compilation pipeline focused on bit precise math, shifts with unbound offsets are avoided
  in the favor of select between BitConcats. This is important because BitRangeGet and BitConcat
  are free on target architecture and InstrSimplify would merge shifts and obfuscate offset computation
  making bit selection patterns practically unrecognizable.

 
Specifics on MIR level
* Nearly all instructions can have register or CImm as any operand.
  This is because constants usually does not need to be shared and we would like to minimize
  number of live registers between the instructions from (compiler) performance reasons.
* PhysRegs can not be used because llvm practically allows only for thousands of them.
  This is a critical issue. This discards all things dependent on PhysRegs and `MachineBasicBlock::liveins`.
  This means that only first half of backend until register allocation can be used. Everything after
  must be re-implemented.
* The hwtHls target machines do not provide assembly writer and other assembly/binary related things
  because output from compilation in LLVM is MIR which is then scheduled and shaped into hardware architecture in Python.
   