#include <hwtHls/llvm/Transforms/LoopToIoFsmPass/normalizeLoops.h>

using namespace llvm;

namespace hwtHls {

bool normalizeLoopsForUnrolling(LoopInfo &LI, DominatorTree &DT,
								ScalarEvolution *SE,
								AssumptionCache *AC) {
	bool Changed = false;
	// The unroller requires loops to be in simplified form, and also needs
	// LCSSA. Since simplification may add new inner loops, it has to run before
	// the legality and profitability checks. This means running the loop
	// unroller will simplify all loops, regardless of whether anything end up
	// being unrolled.
	for (const auto &L : LI) {
		Changed |= simplifyLoop(L, &DT, &LI, SE, AC, nullptr,
									  false /* PreserveLCSSA */);
		Changed |= formLCSSARecursively(*L, DT, &LI, SE);
	}
	return Changed;
}

} // namespace hwtHls