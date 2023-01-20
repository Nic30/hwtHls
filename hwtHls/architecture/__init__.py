"""
This module contains classes for representation of hardware architecture.
Hardware architecture is form of view for :mod:`hwtHls.netlist` which aggregates its nodes to a larger chunks (ArchElement)
and specifies synchronization and data exchange channels between these elements.
The architecture element is a scope for register allocation, control and data path implementation. 


There are several complicated things:
* The synchronization is allocated per clock cycle. The problem is that node may span more than 1 clock cycle (for example bram read, DSP48E1 block etc.)
  Often we can not simply cut nodes to pieces because of complex internal structure. Parts of node may be in a different arch element which implies that we may have
  to split node also vertically (to select some subset of inputs/outputs).
* For some ArchElements it is impossible to determine latency between IO channels.
  This implies that it is impossible to determine the ideal size for data buffers which are connected in parallel with this element.
  This may result in degraded performance or deadlock.


Circuit synchronization partitioning problem:

* In order to convert netlist to a netlist a CFG and IO/shared resource access colissions must be fully resolved.
  This implies that the clusters of nodes where this sort of constrain applies must be identified and proper control implementation must be selected.
  This also involes a discovery of an association between controll structures and data nodes in original netlist.
* This cluster of nodes with is a base unit of architecture implementation is reffered as an IO cluster.

* For this purpose there are several objects:
  * HlsNetNodeIoClusterCore - A netlist node which is used during optimization of the netlist to keep information
      about every IO which needs to be taken in account when optimizing IO access conditions.
  * HlsNetlistAnalysisPassSyncDomains - A pass which discovers the parts of IO cluster which must happen atomically and
      which are subject to some kind of combinatioanal loop later in architecture generation.
  * HlsNetlistAnalysisPassSyncReach - A pass which discoveres nodes in the body of the IO cluster. Produces BetweenSyncNodeIsland.

* An information form previously mentioned objects is then used to construct :class:`hwtHls.architecture.archElement.ArchElement` instances.
"""
