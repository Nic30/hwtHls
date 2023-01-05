
# http://www.ida.liu.se/~petel71/SysSyn/lect3.frm.pdf
# http://cse.yeditepe.edu.tr/~ayildiz/attachments/asap_alap.pdf
# https://www.google.cz/url?sa=t&rct=j&q=&esrc=s&source=web&cd=8&ved=0ahUKEwiDsJyEiP3WAhXHbBoKHaI9CU8QFghuMAc&url=http%3A%2F%2Fwww.gstitt.ece.ufl.edu%2Fcourses%2Ffall07%2Feel4930_5934%2Fhighlevelsynth_1.6.ppt&usg=AOvVaw2dG3O6VVw9LgQSaov7bIiT

"""
This module contains schedulers for circuit scheduling in HLS process.
The scheduling means resolving the stage of pipeline when the operation should happen.
The scheduler solves circuit scheduling which is specific type of job schedulig problem.
The goal is minimize overall circuit latency and picking best suiting implementation of components for specified abstract circuit operation.
Common requirement is also to satisfy resource constrain or to minimize usage of specific resource.

The operations scheduled by schedulers in this module are different from typical job defined in base scheduling problem.

Differences:

 * Scheduled operation can have multiple inputs and outputs (original scheduling job has only start and end).
 * Scheduling happens in continuous time. The time itself is divided into clock cycles.
   Some operations must be bounded to start or end of clock cycle, possibly with some offset.

    * That is the case for example for registers of RAMs where operation happens on edge of clock signal and
      input must arrive at least some specified time before and the output appears after specified time after clock edge.)

    * Each of this time is specific for each input output.
  * Circuit often contains cycles. Most of schedulers do work only for DAGs. In this module we cut of some ("backward") connections.
    The synchronization has to be handled explicitly and externally (data synchronization protocol, buffering, pipeline stalling etc.)
    :see: :mod:`hwtHls.hlsStreamProc.pipelineExtractor`.


Purpose of hwtHls netlist modular scheduler
* The netlist for this scheduler is generated as optimal as possible, all loops are transformed
  to desired form as well as all instructions and control is optimized.
* The main goal is to resolve final scheduling for this netlist in order to map abstract operations
  to RTL.
* Because there are many unique features of nodes and user constraints the optimal scheduling algorithm does not exist.
  In addition scheduling part by part may be sub-optimal and trivial highly efficient algorithm may exist
  for some subgraphs.
* The user guided subgraph selection seems to be highly complex for user.

Considered problematic uses:
* Trivial to schedule but very large in size (CRCs, shifters)
   * This is problematic for any more advanced scheduling algorithm with increased complexity.
* Inter loop iteration dependencies. Pairs usually read-write where it is critical to minimize time between them.
   * The distance may get extended without need if ALAP/ASAP is used just because there was place
     next clock cycle. 
* Multi component scheduling graphs and cactus graphs.
    * Scheduling of circuit is a global problem. If the graph is cut to individually scheduled parts
      it is often required to reschedule whole component on implementation of inter-part connection or
      at least shift whole part schedule. This is likely to be highly sub-optimal and time consuming. 
    * However real circuits may have several independent circuits or several components connected
      with a channel where scheduling is locked to clock boundary. If such graph is split the task complexity
      is lowered.
* SCCs in input graph.
    * Cyclic data dependencies can be removed using backedge buffers or other technique.
      However the SCC can appear due to other reasons than data dependencies (timing restriction between groups of nodes).
* Resource constraints.
    * Typically specified for some IO/Functional Unit but rest can be unconstrained. 
* Nodes with latency tied to clock cycle boundaries.
    * E.g. BRAM port address must arrive some time before clock cycle boundary
      and provides read data in next clock cycle. 
* Non constant scheduling delay of nodes.
    * Nodes with internal structure like MUX tree do map into LUTs where exact latency
      depends on how many LUTs can fit into current clock cycle budget.
    * Nodes which can be mapped to multiple target components may have highly unpredictable
      timing characteristic.
    * This also involves nodes with internal structure composed of sub-nodes.
* Fan-in cones of nodes without any output, Fan-out cones of nodes without any input.
    * If there is just a single pair of node without any input and node without any output the scheduling is trivial.
    * However if there are multiple such a nodes the order in which they are scheduled significantly affects the result.
     Greedy scheduling algorithms like ASAP/ALAP do require some boundary times to place nodes without any
     input/output however the initial placement may be sub-optimal because whole code is able to shift
     which could lead to a better result.
"""
