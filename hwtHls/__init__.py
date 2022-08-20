"""
This module contains a classes for SSA form.
This SSA form is used as a main code representation in frontend and is converted to LLVM SSA IR later.
It exists mainly to simplify storing of custom instructions in SSA and to simplify branching analysis.
Custom instructions are often used in frontend and must be lowered before conversion to LLVM.
There are several differences between this SSA and LLVM SSA:

* This basic block has properties where it stores PHIs, body and branch. (LLVM have all instructions in a single list)

* This branch instructions is variadic.

* This block instructions are stored in python list and not in doubly linked list so remove and insert is costly.  
"""
