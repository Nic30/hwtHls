hwtHls library modules
======================

* llvm - binding to LLVM compiler framework, set ot analysis and transformations for HW and a custom LLVM target GenericFpga
* netlist - HLS netlist is internal repsentation (IR) used for final dataflow analysis and scheduling
* platform - Platform is a container of configuration for target, it specifies its properties and a compiler pipeline which translates input code to HW
* ssa - Static single-assignment form (SSA) is a common normal form used in compilers. In this library it is used for syntax agnostic code representation 
  and it is place where most of the optimizations do happen.

  
netlist and ssa module do contain sets of analysis, transformations and translation. The meaning is following:
* analysis - an algorithm which does not modify code and extract some information about it and this information is cachable and programatically accessible
* translation - an algorithm which does not modify the input code and generates a new repersentation of the code
* transformation - an algorithm which does modify the input code