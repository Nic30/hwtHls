#include <llvm/IR/Function.h>
#include <map>
#include <set>
#include <unordered_set>

namespace hwtHls {

using SplitPoints = std::map<llvm::Instruction*, std::unique_ptr<std::set<uint64_t>>>;
using InstrSet = std::unordered_set<llvm::Instruction*>;
/*
 * Collect bit indexes where some slice on each variable is sliced by some bit slice.
 * Bit indexes for each value do specify the boundaries between segments of bit in this Value which are used independently.
 * */
SplitPoints collectSplitPoints(llvm::Function &F, InstrSet & noSplitInstructions);

}
