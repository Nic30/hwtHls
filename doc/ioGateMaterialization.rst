In traditional HLS if the code reads/writes to/from a channel on multiple locations
the FSM is generated which enables each access.
For example in this code there will be at least two states which do control
what should be written into out_channel.

.. code-block::Python

    while 1:
        x = 10
        while x:
            out_channel.write(x)
            x -= 1
        out_channel.write(11)

However usage of a centralized FSM in dynamically scheduled pipelined circuit is inefficient because
it potentially blocks other branches which could otherwise be a subject to a speculation.
Instead the FSM must be private to each IO port and the rest of the code must run freely in the pipeline.

Speculative writes in general are very expensive in terms of resources because each speculative write
leads to all reads to be speculative and all requiring later confirmation resulting in exponencially
growing number of pipelines for max troughput.


For read operations there are 4 cases based on speculativity and variable access:
1. For a non speculative read which should be shared between branches we can transform the code
   to perform read in advance and schedule it on first read in any branch.

   .. code-block::Python

       if a:
          c  = b.read()
       else:
          c  = b.read() + 1

2. For a non speculative multiple read we should construct a a pipeline + FSM or just FSM where each read will be an independent interface
   connected to a stage of pipeline on based on its order in code and the inputs are enabled based on FSM of original code.
   The just FSM is sufficient if the latency of other operations is small enough and input is consumet at high enough rate.

   .. code-block::Python

       c  = b.read() + b.read()

3. For a speculative single point read we need to first read the data without consumming it and consume it once the branch is confirmed.

   .. code-block::Python

       if a:
          c  = b.read()

4. For a speculative multi point read we need to construct look ahead buffer which will load all data and copy it into speculative branches.
   The depth of buffer depends on max degree of speculation and is generaly specified in number of data words.
   The read data after speculatively read data is also speculative read even if the read itself is not speculative.
   This is because the current possition in data may be shifted due to some previous speculative read

   .. code-block::Python

       if a:
          c  = b.read()
       if d:
          c += b.read()




In the detail for output:
* discover the output channels
* move each write down (in the direction to successor) in basic blocks as possible
  * if all predecessor contains write to this channel, move the write into successor
* resolve latest write location and instanciate a buffers of size of minimal latency between that location and the latest location
* the data into this buffer should be put only if confirmed
* this data also needs to have some ordering information
  * we use will be composed of bits which will represent an iteration index of each loop
* the data with ordering information will be then merged into output channel
  * we always select the data [TODO] the expression how to evaluate the oldes index (least number of togled lsbs or msb toogled and biggest number of toogled lsbs?)
