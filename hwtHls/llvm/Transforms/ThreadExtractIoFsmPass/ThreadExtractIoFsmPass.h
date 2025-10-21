#pragma once

#include <llvm/IR/PassManager.h>
#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>

namespace hwtHls {

class ThreadExtractIoFsmMetadata {
public:
	llvm::MDTuple *md;
	// :note: input/output is from new extracted function point of view
	size_t inputBufferCapacity;
	size_t outputBufferCapacity;

	static const std::string METADATA_NAME;
	ThreadExtractIoFsmMetadata(llvm::MDTuple *md);

	static std::optional<ThreadExtractIoFsmMetadata> find(
			HwtHlsIoMetadata &ioMd);
	void erase(HwtHlsIoMetadata &iomd);
};
/*
 * This pass extract the Load/StoreInst related to some specific IO Argument
 * into a separate thread like function while a taking also all instructions related to it.
 *
 * :note: This must be executed before StreamSegmentLoopUnrollPass because it produces irreducible CFG
 *        This is because this pass requires loops.
 *        The FixIrreducible pass is not ideal there because it would introduce many PHINodes
 *
 * .. code-block:: python3
 *
 *   def thread0():
 *       size = rx.read(u8)
 *       while size:
 *          r1 = tx.write(size)
 *          size -= 1
 *       PyBytecodeThreadExtractIoFsm(tx.interface, inputBufferSize=1)
 *
 *   # to
 *   def thread0(thread0_tx_size):
 *       size = rx.read(u8)
 *       thread0_tx_size.write(size)
 *
 *   def thread0_tx(thread0_tx_size):
 *       while 1:
 *          size = thread0_tx_size.read()
 *          while size:
 *             r1 = tx.write(size)
 *             size -= 1
 *
 * */
class ThreadExtractIoFsmPass: public llvm::PassInfoMixin<ThreadExtractIoFsmPass> {
public:
	llvm::PreservedAnalyses run(llvm::Module &M,
			llvm::ModuleAnalysisManager &AM);
};

}
