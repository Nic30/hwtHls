This folder contains original llvm files which were compiled in unmodifiable way.
The classes are modified only to be extensible, without affecting of the class functionality. 
On update of the LLVM you should copy paste the code from LLVM sources, split it to header file and cpp if required, wrap it under proper namespace
and add name prefix hwtHls- to cl::opt to prevent colision.