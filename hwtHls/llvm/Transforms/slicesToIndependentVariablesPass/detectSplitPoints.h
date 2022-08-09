#include <llvm/IR/Function.h>
#include <map>
#include <set>

namespace hwtHls {


/*
 * Collect bit indexes where some slice on each variable is sliced by some bit slice.
 * Bit indexes for each value do specify the boundaries between segments of bit in this Value which are used independently.
 * */
std::map<llvm::Instruction*, std::set<uint64_t>> collectSplitPoints(llvm::Function &F);

}
