

class SsaPass():

    def apply(self, hls: "HlsStreamProc", to_ssa: "AstToSsa"):
        raise NotImplementedError("Should be implemented in inheriting class", self)
