from io import StringIO
import os

from hwt.synthesizer.unit import Unit
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.analysis.dumpPipelines import SsaPassDumpPipelines
from hwtHls.ssa.transformation.extractPartDrivers.extractPartDriversPass import SsaPassExtractPartDrivers
from hwtHls.ssa.transformation.runFn import SsaPassRunFn
from hwtHls.ssa.transformation.runLlvmOpt import SsaPassRunLlvmOpt
from hwtHls.ssa.translation.fromLlvm import SsaPassFromLlvm
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm
from hwtLib.examples.base_serialization_TC import BaseSerializationTC


class TestFinishedSuccessfuly(BaseException):

    @classmethod
    def raise_(cls, *args):
        raise cls(*args)


class BaseSsaTC(BaseSerializationTC):
    """
    :attention: you need to specify __FILE__ = __file__ on each subclass to resolve paths to files
    """

    def tearDown(self):
        self.rmSim()

    def _runTranslation(self, unit_cls, ssaPasses):
        self.rmSim()
        with self.assertRaises(TestFinishedSuccessfuly):
            self.compileSimAndStart(unit_cls, target_platform=VirtualHlsPlatform(ssaPasses=ssaPasses))
        self.rmSim()

    def _test_ll(self, unit_constructor: Unit, name=None):
        buff = [StringIO() for _ in range(4)]
        ssaPasses = [
            SsaPassConsystencyCheck(),
            SsaPassDumpToLl(lambda name: (buff[0], False)),
            SsaPassExtractPartDrivers(),
            SsaPassConsystencyCheck(),
            SsaPassDumpToLl(lambda name: (buff[1], False)),
            SsaPassToLlvm(),
            SsaPassRunLlvmOpt(),
            SsaPassFromLlvm(),
            SsaPassConsystencyCheck(),
            SsaPassDumpToLl(lambda name: (buff[2], False)),
            SsaPassDumpPipelines(lambda name: (buff[3], False)),
            SsaPassRunFn(TestFinishedSuccessfuly.raise_)
        ]
        unit = unit_constructor()
        self._runTranslation(unit, ssaPasses)
        val = [b.getvalue() for b in buff]
        if name is None:
            name = unit.__class__.__name__

        self.assert_same_as_file(val[0], os.path.join("data", name + "_0.ll"))
        self.assert_same_as_file(val[1], os.path.join("data", name + "_1.ll"))
        self.assert_same_as_file(val[2], os.path.join("data", name + "_2.ll"))
        self.assert_same_as_file(val[3], os.path.join("data", name + "_3.pipeline.txt"))
