LLVM basics, code utilities
===========================

This documents is an introduction to LLVM ADTs and commonly used functions and classes which
are essential for readable and short C++ code which is using LLVM.

llvm/ADT/
--------
As the name suggests this inlcude dir contains files with definition of common ADTs like DenseSet, APInt etc.
* LLVM redefines STL (Standard Template Library) C++ types with more efficient one. This is the case for
  example for SmallVector which is a vector where some n first items can be stored without the need for
  a dynamic memory allocation.
* There are plenty of variants of containers like they are more or less self explanatory.
  In other frameworks ADTs may have different names for example UniqueVector vs OrderedSet.
* LLVM internally performs many string concatenations and it has significant performance implications.
  To optimize it there is a Twine and StringRef. StringRef is a string reference with pre-computed len and Twine
  is a string concatenation.
* Commonly used iterator utilites (STLExtras.h)
  * make_filter_range - creates filtered iterator from iterator and filter
  * make_early_inc_range - creates iterator which internally gets successor before the item is processed by user of this iterator
    this is usefull when removing item as the iterator is internally already on next item and delete of current item
    does not cause issue.
  * zip_* - creates iterator of tuples from list of iterators as zip() in python
  * there are many others like replace_if, concat, one_of


llvm/IR/
--------

Code in LLVM is represented by Module/Function/BasicBlock/Instruction instances (nested in this order).
Some objects may have metadata (MDNode instances) or Attribute(s) to provide additional specification.

IR is rarely build directly object by object, instead IRBuilder<> is usually used. IR can also be loaded from file using parseIR.
Another important classes are  User, Value, Use. Value is a base class for everything which can be used in expression,
User is something which is using some Values and Use is slot associating User and used Value

IR objects are using custom dynamic type resolution framework.
* isa<cls>() check if object is of a class
* dyn_cast<cls>() dynamic_cast<>() equivalent 

The process of binding Instruction or any definition to source code location is described there https://www.llvm.org/docs/SourceLevelDebugging.html
The source code location is not usually explicitly added to each instruction instead IRBuilder::SetCurrentDebugLocation is used.
* IRBuilder
  * InsertPointGuard automatically swaps and swaps back insertion point

* Dominator tree - data structures for CFG analysis
	* Node A dominates node B if the only way to reach B from the start node is through node A.
	* Join-point - place where PHINode should be placed for variable modified on multiple placeces.

MIR level (llvm/CodeGen)
------------------------
https://www.llvm.org/docs/MIRLangRef.html

This layer is responsible for translation of an universal LLVM IR to a target specific instructions
which are ten directly translated to binary (if compiling for CPU like arch).

MIR may appear in LLVM from several sources:
* it may be directly loaded createMIRParser + MIRParser::parseMachineFunctions
* it may produced from IRTranslator
* it may be constructed using CSEMIRBuilder/MachineIRBuilder

The main difference between IR is that in later compilation phases the MIR is not in SSA form and values
in registers are stored in physical registers with probably different type than original virtual register which
was created for Value in IR.

The MIR goes trough several phases https://www.llvm.org/docs/GlobalISel/index.html
The MIR begins with generic opcodes which are then specialized (Selected) to a target specific
variant of instruction.

* ReachingDefAnalysis

MLIR
----
https://github.com/llvm/llvm-project/tree/main/mlir/examples
https://github.com/vguerra/mlir-tutorial-cmake
https://github.com/j2kun/mlir-tutorial

