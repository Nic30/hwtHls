pyBytecode frontend
===================

Dictionary
----------

* proprocessor code - code which is executed and evaluated during preprocessing
* target code - the code templates nested in preprocesor code which can not be evaluated by preprocessor and must be to an output of the preprocessor
                     In the context of this library it means the code which will represent some hardware. 
* user code - proprocessor + target code 
* preprocessed code - user code after it passed trough the preprocessor
* python bytecode - A set of insructions for python interpret
* SSA - Static Single Assignment

This frontend allows to write a target code and and its preprocessing in a single piece of the code.

The pyBytecode frontend uses interpret of the python code to expand user code to a statically typed code with only HW compatible instructions.
The Python in this case works as a preprocessor of itself. The preprocessor and target code is indistinguishable by static analysis
and it distinguished runtime. Every variable or jump depending on some value of HdlType is treated as target code if not marked with PyBytecodeInPreproc.
Application code is gradually stacked during evaluation of the user code.
This preprocessor runs python bytecode and generates SSA from parts of it.

The evaluation of the byte code is straightforward but construction of optimal statically typed SSA is non trivial.
* If target code codition is used as a jump condition the proprocessor must generate code for every possible path
  because bouth branches must be translated to preprocessed code.
* Blocks from expanded loops, calls and exception handlers must have deterministic unique labels.
  * This requires foward analysis of potential loops.
  * The loop may or may not be expanded based on iteration scheme this iteration scheme is dynamically resolved during the preprocessing.
  * For loops in target code we can not expand this loop and jumps to a loop header must remain as they are.
  * For loops in preprocessor we must expand this loop and copy body bocks with unique label for every iteration.

* SSA construction algorithm requires to know when the block has every predecessor constructed.
  * New predecessors may appear during preprocessing.
  * The name of predecessor is a subject to unique labeling.
  * Preprocessor runs pseudoparallely on branches with target code condition. 


Main frontend class PyBytecodeToSsa:

* The traslation starts by collecting of CFG from Python bytecode of current function.
  * The block label is specified as a prefix and offset in bytecode.
  * The prefix is a tuple generated from loop iteration labels and function call labels.
  * The SSA basic blocks are constructed on jumps in instruction list.
    A single jump target may generate multiple basic blocks from reasons explained later (target code HW dependent branches).
* The execution context is stored in PyBytecodeFrame and contains mainly stack and original CFG for later copying.
* The context is used for evaluation of code in Python bytecode.
    * There are 2 types of variables/stack slots:
        * Preprocessor variable
            * Regular Python variable
        * Target variable
            * A variable which holds an instance of some hardware class
            * Operation with this type of variable can not be evaluated
              and instead it is copied to an output SSA.
* Because use of hardware value can appear in control flow instruction we must translate CFG if this happen as well.
    * This leads to a need of a stack and locals copy on each branch on target value.
    * If some bytecode block is visited with a different stack variant it must be duplicated in an output SSA.
      However it is required only if stack differs in preprocessor variable because the target code variables are handled in SSA.
      The parallel evaluation is also limited by a current loop body and function call.
* If jump condition can be evaluated during compilation it is translated as unconditional jump in SSA and
  not taken jumps from this block are marked as not generated (using :meth:`~.PyBytecodeToSsa._addNotGeneratedJump`).
* As a consequence there are two types of loops, hardware evaluated and preprocess loops.
    * The type of loop is resolved during evaluation. If some jump corresponding to break/continue (from loop/to loop header)
      appears, this loop must be converted to SSA as a loop.
    * If the loop is preprocessor loop it is converted to SSA as a chain of loop body iterations.
    * If the loop is target evaluated loop it is converted to SSA as a loop.
    * The loop is target evaluated loop if any branch break/continue branch in loop depends on target evaluated value.
    * Because final CFG differs on loop body boundaries for mentioned loop types it is required to resolve type
      of the loop before potential second iteration of body.
      Because code is evaluated in DFS manner and because stack is copied on each HW evaluated branch
      it is required to postpone the evaluation in parallel branches until the loop type is resolved.
      * This implies that in a single time there may be multiple evaluation contexts and in some block it is required to merge them.
      * The currently pending jumps from current loop body/function are stacked in current evaluation frame.

