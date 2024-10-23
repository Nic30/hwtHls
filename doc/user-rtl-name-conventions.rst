
RTL name conventions
--------------------

* https://github.com/lowRISC/style-guides/blob/master/VerilogCodingStyle.md
* inverted signals have \_n suffix (do not use #)
* names of constants in uppercase snakecase


.. table:: Synchronization flag names
   :widths: auto

   ================= =============================== ======================= =========================================================================
    Name              Alternative name (avoid)        Typical direction       Description                                                             
   ================= =============================== ======================= =========================================================================
    en,enable                                         M->S                    slave is allowed to perform its function                                
    ack,acknowledge                                   S->M                    ack source is performing its function                                   
    rd,ready          dst_rd, rdy, dst_rdy, stall_n   S->M                    2-state handshake, receiver is able to receive currently incomming data 
    vld,valid         src_rd, src_rdy, en             M->S                    2-state handshake, transmiter is currently sending a valid data         
    req,request       done                                                    req source is requesting transaction credit                             
    gnt,grant         req, request                                            gnt source is returning transaction credit                              
    full/empty + en                                   full:S->M, empty:M->S   fifo sync, en enables transaction, must not be set if full/empty        
   ================= =============================== ======================= =========================================================================


RTL resource minimization guides
---------------------------------
* https://zipcpu.com/blog/2017/06/12/minimizing-luts.html