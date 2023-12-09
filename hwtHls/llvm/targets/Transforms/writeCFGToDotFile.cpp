#include <hwtHls/llvm/targets/Transforms/writeCFGToDotFile.h>
#include <llvm/CodeGen/MachineCFGPrinter.h>
#include <llvm/Support/GraphWriter.h>
#include <limits>

using namespace llvm;

namespace hwtHls {

void writeCFGToDotFile(llvm::MachineFunction &MF, const std::string &Filename,
		bool debugMsgs, bool CFGOnly) {
	if (debugMsgs)
		errs() << "Writing '" << Filename << "'...";

	std::error_code EC;
	raw_fd_ostream File(Filename, EC, sys::fs::OF_Text);
	DOTMachineFuncInfo CFGInfo(&MF);

	if (!EC)
		WriteGraph(File, &CFGInfo, CFGOnly);
	else if (debugMsgs)
		errs() << "  error opening file for writing!";
	else
		throw std::ifstream::failure("error opening file for writing!");
	if (debugMsgs)
		errs() << "\n";
}

}
