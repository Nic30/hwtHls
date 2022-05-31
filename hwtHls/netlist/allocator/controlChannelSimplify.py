

class RtlAllocatorPassControlChannelSymplify():
    """
    * reduce parallel sync channels (if multiple channels lead from same source to same destion they are dudundat 1 is enough)
    * reduce hanshake always satisfier cycles
       * from same to same -> no sync required
       * a cycle with multiple IO which does not genereate additional transactions
          *
    """
