#pragma once
#include <map>
#include <set>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

enum IODirection {
	IO_DIR_IN, IO_DIR_OUT, IO_DIR_UNRESOLVED,
};
IODirection IODirection_reverse(IODirection d);

// :note: This record is an override of default argument connections.
//   if argument is connected directly to topIo on same index there is not metadata.
class HwtHlsIoMetadata {
public:
	IODirection direction;
	size_t addrWidth; // width of address for addressed io (0 for scalars)
	size_t readWordWidth; // specifies the native width of a single load from this io
	size_t writeWordWidth; // specifies the native width of a single store to this io
	bool isBlocking; // specifies if io is blocking non-blocking, non-blocking have extra 1 bit (msb) which specifies
	// if the read data is valid or not

	llvm::Function *otherThreadFn; // :note: other thread or nullptr if this argument is connected to a top IO
	size_t otherArgIndex; // index of argument in other thread or at top where this IO is connected
	size_t bufferCapacity; // size of FIFO buffer for scalar io
	// :note: if two HwtHlsIoMetadata are connected together using otherThreadFn/otherArgIndex the total buffer size is the sum from both

	llvm::MDTuple *ioPropertyPath; // optional property path specifying where exactly is this io connected on io object
	// (which is specified by otherThreadFn, otherArgIndex)
	// :note: typically used for IO which dissolve to communication on multiple channels like AMBA AXI4
	llvm::MDTuple *latenciesFromPredecessorIo; // optional tuple of latencies to other io of this function
	// the number is signed int where -1 marks not-specified value and the >=0 value marks how many
	// clock cycles must be left between predecessor and this IO during scheduling
	llvm::MDTuple *protocolSpecificMetadata; // IO type dependent tuple specifying additional info about IO
	llvm::MDTuple *streamIoMd; // optional metadata for StreamChannelFormatInfo
	llvm::MDTuple *ioFsmExtractMd; // optional metadata for ThreadExtractIoFsmPass

	HwtHlsIoMetadata() :
			direction(IODirection::IO_DIR_UNRESOLVED), addrWidth(0), readWordWidth(
					1), writeWordWidth(1), isBlocking(true), otherThreadFn(
					nullptr), otherArgIndex(0), bufferCapacity(0), ioPropertyPath(
					nullptr), latenciesFromPredecessorIo(nullptr), protocolSpecificMetadata(
					nullptr), streamIoMd(nullptr), ioFsmExtractMd(nullptr) {

	}
	HwtHlsIoMetadata(IODirection direction, size_t addrWidth,
			size_t readWordWidth, size_t writeWordWidth, bool isBlocking,
			llvm::Function *otherThreadFn, size_t otherArgIndex,
			size_t bufferCapacity, llvm::MDTuple *ioPropertyPath,
			llvm::MDTuple *latenciesFromPredecessorIo,
			llvm::MDTuple *protocolSpecificMetadata, llvm::MDTuple *streamIoMd,
			llvm::MDTuple *ioFsmExtractMd) :
			direction(direction), addrWidth(addrWidth), readWordWidth(
					readWordWidth), writeWordWidth(writeWordWidth), isBlocking(
					isBlocking), otherThreadFn(otherThreadFn), otherArgIndex(
					otherArgIndex), bufferCapacity(bufferCapacity), ioPropertyPath(
					ioPropertyPath), latenciesFromPredecessorIo(
					latenciesFromPredecessorIo), protocolSpecificMetadata(
					protocolSpecificMetadata), streamIoMd(streamIoMd), ioFsmExtractMd(
					ioFsmExtractMd) {
		if (!isBlocking)
			assert(addrWidth == 0);
		if (addrWidth != 0)
			assert(bufferCapacity == 0);
	}

	llvm::MDNode* asMetadata(llvm::LLVMContext &Ctx) const;
	static HwtHlsIoMetadata fromMetadata(llvm::Metadata &hwtHlsIOItem);
	void setLatenciesFromPredecessorIo(llvm::LLVMContext &Ctx,
			llvm::ArrayRef<int> latenciesFromPredecessorIo);
	void getLatenciesFromPredecessorIo(
			llvm::SmallVector<int> &latenciesFromPredecessorIo);

	bool isOut() const;
	bool isDefaultValue() const;
	void consystencyCheck() const;
	bool operator==(const HwtHlsIoMetadata &other) const;
	void print(llvm::raw_ostream &O, bool IsForDebug = false) const;
	static const std::string METADATA_NAME;
};

std::pair<llvm::Type*, llvm::Type*> getLoadOrStoreElementType(
		const llvm::Argument &arg);
std::pair<llvm::Type*, llvm::Type*> getLoadOrStoreElementType(
		const llvm::Instruction &I);

llvm::SmallVector<HwtHlsIoMetadata> HwtHlsIoMetadata_get(
		const llvm::Function &F);
std::optional<HwtHlsIoMetadata> HwtHlsIoMetadata_get(const llvm::Function &F,
		size_t argI);
void HwtHlsIoMetadata_set(llvm::Function &F,
		const llvm::SmallVector<HwtHlsIoMetadata> &mds);
void HwtHlsIoMetadata_set(llvm::Function &F, size_t argI,
		const HwtHlsIoMetadata &md);
// :returns: true if module is broken (same as llvm::verifyModule)
bool verifyHwtHlsIoMetadata(const llvm::Module &M,
		bool allowFunctionsWithoutHwtHlsIoMetadata = false,
		llvm::raw_ostream *OS = nullptr);

}

namespace llvm {

inline llvm::raw_ostream& operator<<(llvm::raw_ostream &OS,
		const hwtHls::HwtHlsIoMetadata &V) {
	V.print(OS);
	return OS;
}

}
