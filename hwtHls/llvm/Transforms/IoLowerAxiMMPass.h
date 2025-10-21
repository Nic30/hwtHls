#pragma once

#include <llvm/IR/PassManager.h>
#include <llvm/ADT/APInt.h>

namespace hwtHls {

enum MemoryOrdering {
	MEMORDERING_NONE, // any transaction is dispatched/processed as soon as possible, not waiting for
	// any another potentially colliding transactions
	// :note: use this if you want to manage coherency and ordering manually or if it is known that
	//   transactions may be performed in any order
	MEMORDERING_MUST_WAIT_FOR_WRITE_CONFIRM, // read or write transactions may not begin until last write
// received confirmation on axi.b channel
// :note: use this if you want Total Store Order (TSO) and throughput is not important
};
const char* MemoryOrdering_toString(MemoryOrdering mo);
MemoryOrdering MemoryOrdering_fromString(const std::string &mo);

// to make this universal as possible the
// description of io is split into specification of important bits and default value for each channel
class MetadataIoAxiMM {
public:
	// :note: the width can be found from default values, width excludes ready/valid signal
	llvm::APInt arDefault;
	llvm::APInt rDefault;
	llvm::APInt awDefault;
	llvm::APInt wDefault;
	llvm::APInt bDefault;

	// pairs offset, width of signal bits in merged value of channel word
	std::pair<size_t, size_t> aId; // offset and width of id signal bits in address channels
	std::pair<size_t, size_t> bId; // same as aId but for b channel
	std::pair<size_t, size_t> rId; // same as aId but for r channel
	std::pair<size_t, size_t> wId; // same as aId but for w channel
	std::pair<size_t, size_t> addr;
	std::pair<size_t, size_t> len;
	std::pair<size_t, size_t> rData;
	std::pair<size_t, size_t> wData;
	size_t dataWidth; // number of bits of data only (r/w channels contains additional fields not just data)
	unsigned latencyArToR;
	unsigned latencyAwToW;
	unsigned latencyWToB;
	unsigned latencyBToR;
	MemoryOrdering memOrdering;

	MetadataIoAxiMM() :
			arDefault(), rDefault(), awDefault(), wDefault(), bDefault(), aId(0,
					0),  // Offset 0, width 0
			bId(0, 0), rId(0, 0), wId(0, 0), addr(0, 0), len(0, 0), rData(0, 0), wData(
					0, 0), dataWidth(), latencyArToR(1), latencyAwToW(
					0), latencyWToB(1), latencyBToR(1), memOrdering(
					MemoryOrdering::MEMORDERING_MUST_WAIT_FOR_WRITE_CONFIRM) {
	}
	MetadataIoAxiMM(                                 //
			const llvm::APInt &arDefault_,           //
			const llvm::APInt &rDefault_,            //
			const llvm::APInt &awDefault_,           //
			const llvm::APInt &wDefault_,            //
			const llvm::APInt &bDefault_,            //
			const std::pair<size_t, size_t> &aId_,   //
			const std::pair<size_t, size_t> &bId_,   //
			const std::pair<size_t, size_t> &rId_,   //
			const std::pair<size_t, size_t> &wId_,   //
			const std::pair<size_t, size_t> &addr_,  //
			const std::pair<size_t, size_t> &len_,   //
			const std::pair<size_t, size_t> &rData_, //
			const std::pair<size_t, size_t> &wData_, //
			size_t dataWidth,             //
			unsigned latencyArToR,                   //
			unsigned latencyAwToW,                   //
			unsigned latencyWToB,                    //
			unsigned latencyBToR,                    //
			MemoryOrdering memOrdering               //
			) :
			arDefault(arDefault_), rDefault(rDefault_), awDefault(awDefault_), wDefault(
					wDefault_), bDefault(bDefault_), //
			aId(aId_), bId(bId_), rId(rId_), wId(wId_), addr(addr_), len(len_), rData(
					rData_), wData(wData_), //
			dataWidth(dataWidth), latencyArToR(
					latencyArToR), latencyAwToW(latencyAwToW), latencyWToB(
					latencyWToB), latencyBToR(latencyBToR), memOrdering(
					memOrdering) {
	}
	// :note: size of native read and write word is physically different
	//     but in LLVM we use the larges one to have address in the same format
	size_t getWordWidth() const;
	static const std::string metadataName_ioAxiMM;
	llvm::MDTuple* toMetadata(llvm::LLVMContext &context);
	static MetadataIoAxiMM fromMetadata(const llvm::MDTuple &mdTuple);
};

class IoLowerAxiMMPass: public llvm::PassInfoMixin<IoLowerAxiMMPass> {
public:
	llvm::PreservedAnalyses run(llvm::Module &M,
			llvm::ModuleAnalysisManager &AM);

};

}
