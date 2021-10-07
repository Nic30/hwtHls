
# http://www.ida.liu.se/~petel71/SysSyn/lect3.frm.pdf
# http://cse.yeditepe.edu.tr/~ayildiz/attachments/asap_alap.pdf
# https://www.google.cz/url?sa=t&rct=j&q=&esrc=s&source=web&cd=8&ved=0ahUKEwiDsJyEiP3WAhXHbBoKHaI9CU8QFghuMAc&url=http%3A%2F%2Fwww.gstitt.ece.ufl.edu%2Fcourses%2Ffall07%2Feel4930_5934%2Fhighlevelsynth_1.6.ppt&usg=AOvVaw2dG3O6VVw9LgQSaov7bIiT

"""
This module contains schedulers for circuit scheduling in HLS process.
The scheduling means resolving the stage of pipeline when the operation should happen.
The scheduler solves circuit scheduling which is specific type of job schedulig problem.
The goal is minimize overall circuit latency and picking best suiting implementation of components for specified abstract circuit operation.
Common requirement is also to satisfy resource constrain or to minimize usage of specific resource.

The operations scheduled by schedulers in this modle are different from typical job defined in base scheduling problem.

Differencies:

 * Scheduled operation can have multiple inputs and outputs (original scheduling job has only start and end).
 * Scheduling happens in continuous time. The time itself is divided into clock cycles.
   Some operations must be bounded to start or end of clock cycle, possibly with some offset.

    * That is the case for example for registers of RAMs where operation happens on edge of clock signal and
      input must arrieve at least some specified time before and the output appears after specified time after clock edge.)

    * Each of this time is specific for each input output.
  * Circuit offten contains cycles. Most of schedulers do work only for DAGs. In this module we cut of some ("backward") connections.
    The synchronization has to be handled explicitely and externally (data synchronization protocol, buffering, pipeline stalling etc.)
    :see: :mod:`hwtHls.hlsStreamProc.pipelineExtractor`.

"""