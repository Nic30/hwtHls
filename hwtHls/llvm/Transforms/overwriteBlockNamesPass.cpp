#include <hwtHls/llvm/Transforms/overwriteBlockNamesPass.h>
#include <llvm/Support/CommandLine.h>

using namespace llvm;

namespace hwtHls {

static bool parseCanonicalBBName(StringRef N, unsigned &Id) {
	if (!N.starts_with("bb"))
		return false;

	StringRef Suffix = N.drop_front(2);
	if (Suffix.empty())
		return false;

	auto [Ptr, EC] =
		std::from_chars(Suffix.data(), Suffix.data() + Suffix.size(), Id);
	return EC == std::errc() && Ptr == Suffix.data() + Suffix.size();
}

static void overwriteNames(Function &F) {
	SmallVector<BasicBlock *, 16> ToRename;
	size_t MaxId = 0;

	for (BasicBlock &BB : F) {
		unsigned Id = 0;
		if (BB.hasName() && parseCanonicalBBName(BB.getName(), Id)) {
			MaxId = std::max(MaxId, static_cast<size_t>(Id));
		} else {
			ToRename.push_back(&BB);
		}
	}

	size_t NextId = MaxId + 1;
	for (BasicBlock *BB : ToRename) {
		BB->setName("bb" + std::to_string(NextId++));
	}
}

llvm::PreservedAnalyses
OverwriteBlockNamesPass::run(llvm::Function &F,
							 llvm::FunctionAnalysisManager &AM) {
	overwriteNames(F);
	return PreservedAnalyses::all();
}

static llvm::cl::opt<bool>
	OVERWRITE_BLOCK_NAMES("hwthls-overwrite-bb-names", cl::Hidden,
						  cl::init(false), llvm::cl::desc("(default = false)"));

llvm::PreservedAnalyses
OptionallyOverwriteBlockNamesPass::run(llvm::Function &F,
									   llvm::FunctionAnalysisManager &AM) {
	if (OVERWRITE_BLOCK_NAMES) {
		overwriteNames(F);
	}
	return PreservedAnalyses::all();
}
}
