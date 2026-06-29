HwtHls specific in LLVM based code
==================================

HwtHls uses LLVM as stand alone library and does not modify it.
However specifics require some intrinsic functions (`hwtHls/llvm/targets/intrinsic`)
and the TargetMachine (HwtFpga) can not use llvm PhysReg which complicates
basically everything after CodeGenPrepare.


Specifics on IR level
* It is not possible to add more intrinsic functions to already compiled LLVM.
	* hwtHls intrinsics (`hwtHls/llvm/targets/intrinsic`) are thus normal functions
	  and there is a method to match them and create them instead.
* Custom compilation pipeline usually explicitly executed using LlvmCompilationBundle
  (instead of llvm-opt tool there is utils/hwtHls-opt.py but it is intended only for compatibility
   and hwtHls.llvm.llvmIr module which directly links to llvm on C++ level should be used instead)

 
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
   