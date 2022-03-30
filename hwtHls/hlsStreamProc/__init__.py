# -*- coding: utf-8 -*-
"""


What is in this module?
=======================

:mod:`hwtHls.frameMachine` is not a complete HLS engine because it ignores the specific of target platform and it has not a generic use.
It is designed to translate operation on streams and other handshake like interfaces.

It's main benefits are:
* The user does not need to care about exact latency of the data arrival or dispatch.
  It performs the buffer instantiation, deadlock analysis and automatic buffer instantiation.
* The frames can be treated just as a content of variable.
* The circuit is automatically pipelined and the statements and loops are merged and unrolled to maximize throughput for specified data width.

Goal:
* Write algorithm in latency insensitive manner and ignore specifics of data packing in bus words.
  The manual instantiation of parsers/deparsers and latency compensation registers and manual synchronization
  of IO channels is avoided. This makes the code more easy to read, error proof and much shorter.


Dictionary:
* SSA - Static Single Assignment
* LLVM BB - Basic Block, a sequence of instruction without any branching or labels to jump into other than start
* LLVM PHI instruction - named after φ function used in the theory of SSA, based on previous BB selects the value of the variable


Problems:
* The SSA form is widely used in compilers and also in HLS compilers, however the most of transformations
  in HLS compilers are reconstructing the informations which we already have in our input.

Possible flow:
* Translate packet level code to word level code.
    * The problem is how to detect the relations between the operations on same input/output
      and how to discover the actual arrival/dispatch time for each fragment of read data
      and what latency the operations have so we need to buffer them or not.

* Translate word level code to SSA.

* Extract statically schedulable segments, schedule and instantiate them.
* Instanciate dynamic scheduling nodes and buffers.
    * L. Josipovic, A. Guerrieri and P. Ienne, "Synthesizing General-Purpose Code Into Dynamically Scheduled Circuits,"
      in IEEE Circuits and Systems Magazine, vol. 21, no. 2, pp. 97-118, Secondquarter 2021, doi: 10.1109/MCAS.2021.3071631.



Mapping of generic code to hardware architectures without harcoding of architectures in synthetizer
===================================================================================================

Translation of linear code to a hw pipeline in nearly a simple task, but arbitrary user code has rarely this format.
It typically contains a loops with multi-cycle body, which must be modified and even after it the data and control flow
must be speculated and everything needs to be pipelined to achieve sufficient performance.
The hardware naturally supports the paralelism and thus speculation and non-constant length operation could be potentially
support easily. However the support logic for speculation and data conflict solving can grow incredibly complex and costly.
There are many unique architectures which are optimal for some very specific case, all together are complex enough to consume
more time than available not mentioning that some of them are probably unknown or never used in real app.

This leaves us in the situation where we can not afford to have a single architecture because its cost would make it impractical
and we can not also use optimal architectures because it is not doable in realistic time even for the most common cases.
Because of this we focus on finding of hyper-parameters and independently applicable transformations.
The basic idea formulated bellow is based on tagging and speculation on demand decoration of partially scheduled circuit to increase its performance.
All steps like pipelining, loop transformations should be already performed before this pass.


* Tagging is applied before each brach condition
    * tagging can be avoided if:
        * there is no speculation (which takes multiple clock cycles)
            * there is no speculation if:
                * branching can be evaluated immediately
                * branching should be blocking
                * the code does not contain branching at all


* Branch node broadcast to successors its branching result for specified tag
  (on tagging in-gates the tag is translated for segment until tagging out-gate of that in-gate)
* Tag record is tuple (id, confirmed)
   * tag id can be avoided if:
        * the latency of branches is the same and data dropping happens only on tagging out-gate
        * branches of constant approximately same length can be efficiently transformed to this format by writing to output
          variables at the end and padding of clock difference.
   * otherwise It is important that each tag combination is unique in system
        * can be achieved using fifo counters for in/out gate (in writer, out out-of-order reader)
        * in the case of parent tag gets dropped the message is also broadcasted to a tagging in-gate of children
          there it is translated to a child tag which was used and this tag cancel must be broadcasted
        * (also to child tagging-out gate, together with original tag which should be forwarded behind tagging out-gate)
        * This also means that each node can check only tag confirm broadcasts from its parent and does need to check broadcasts
          from parents of parent.
        * This also means that each boadcasted message travels until it meets its own tagging out-gate and
          the message received at tagging in-gate must be send unchanged from tagging out-gate.
        * The message should not re-enter same gate multiple times as it was already processed.
          That means that if the in-gate was origin its own out-gate should not output broadcast message and
          the broadcasting can only drill down in branches.
          Attention this works only for a irreducible graphs.
          (For example does not work for codes which are jumping in the middle of code, but such a codes can not be produced
           using structural programming. https://compilers.iecc.com/comparch/article/94-01-106 )
   * tag confirmation can be avoided if:
       * the evaluation of branch condition can be done in same clock cycle as distribution of taged data
   * the data may have multiple tag records, where each corresponds to a tag for specific predecessor branching node
      the tagging out-gate pops the lastly assigned

* Data flows into cycle based on availability, where data from previous iteration do have higher priority
* Upon receive of speculation result from branch node each node which does have data with this tag marks its it confirmed or drops it
  based on branch message
* IO node based on inputs from branch nodes switches to sub-fsm for specified branch and starts pulling the data


Elements of HlsStreamProc circuits
=================================

* operation pipeline
    * multiple inputs/outputs
    * each input/output has assigned some clock cycle when it consumes/produces the data
    * all inputs must be consumed, all outputs must be produced
    * operation may be cancelable (may have a hidden input which marks outputs as invalidated, optionally a transaction id can be specified
      if the operation may process multiple transaction at once)

* speculation - precompute some data in advance without knowing that it should be computed or not, then apply once it is known
    * useful when:
        * condition of the branch takes too long to evaluate
        * in lopps
            * if dependencies have known value (or there is limited number of possible values)
              but it is not known if current iteration is last or not
* tagging - allows for running of operations out of order
    * useful for:
        * operations of unequal latency in parallel, then reorder the results to match input order
`
"""
