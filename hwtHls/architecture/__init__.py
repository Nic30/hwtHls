"""
This module contains classes for representation of hardware architecture.
Hardware architecture is form of view for :mod:`hwtHls.netlist` which aggregates its nodes to a larger chunks.
The architecture element is a scope for register allocation, control and data path implementation. 

There are several complicated things:
* The synchronization is allocated per clock cycle. The problem is that may nodes span more than 1 clock cycle (for example bram read, DSP48E1 block etc.)
  Often we can not simply cut nodes to pieces because of complex internal structure. Parts of node may be in a different arch element which implies that we may have
  to split node also vertically (to select some subset of inputs/outputs).

"""