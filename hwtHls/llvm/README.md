* main list of passes specified in llvmCompilationBundle.cpp
* main list of machine passes specified in targets/hwtFpgaTargetPassConfig.cpp
* Doing optimizations on IR level is preffered, but some things like register allocation, predication, scheduling
  are practically undoable on IR level and thus there are also MIR transformations and LLVM target machine backend for fpga defined in llvm/tartets/. 
* machine instruction combiners are using LLVM GISel (Global Instruction Selection) framework and are
  specified in llvm/targets/HwtFpgaCombine.td which is using llvm/targets/GISel