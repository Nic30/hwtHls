

class RtlAllocatorPassControlChannelSymplify():
    """
    * reduce parallel sync channels (if multiple channels lead from same source to same destination they are redundant 1 is enough)
    * reduce handshake always satisfier cycles
       * from same to same -> no sync required
       * a cycle with multiple IO which does not generate additional transactions
          *
    """
