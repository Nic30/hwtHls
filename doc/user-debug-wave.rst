Debugging with wave dumps
=========================

Wave dump files (LXT, LXT2, VZT, FST, GHW and many others) are produced by many tools in hardware development. Wave dump file contains
the value changes for defined signals through the time. It is useful for analysis of circuit behavior on Register Transfer Level and there are tools which
can also analyze protocols and provide view on protocol data level.

There are many tools for this purpose to name few:
* `GTKWave <https://gtkwave.sourceforge.net/>`_ is a relatively basic but complete and scriptable wave viewer.
* `PulseView <https://www.sigrok.org/wiki/PulseView>`_ is primarly used for osciloscopes and logical analysers but can also load VCD files.
  It contains many protocol decoders, but it current version (0.4.2) can not load files with bit vectors. 
* `PicoScope <https://www.picotech.com/downloads/linux/>` 
  
There are also extensions to traditional IDEs and also many online viewers.
* `vscode-extension-digitalcircuitanalysis <https://github.com/Nic30/vscode-extension-digitalcircuitanalysis>`_
