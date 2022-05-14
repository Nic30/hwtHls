# Generic informations about LLVM target structure
https://releases.llvm.org/14.0.0/docs/WritingAnLLVMBackend.html

LLVM target is composed of several components
* LLVMTargetMachine
* TargetSubtargetInfo
* TargetTransformInfoImplBase

The objects needs to be registered before use, in this case it is done using
LLVMInitializeGenericFpgaTarget();
LLVMInitializeGenericFpgaTargetInfo();
LLVMInitializeGenericFpgaTargetMC();