#pragma once

#include <llvm/IR/Metadata.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

enum IODirection {
	IO_DIR_IN, // input of the function
	IO_DIR_OUT, // output of the function
	IO_DIR_UNRESOLVED,
};
IODirection IODirection_reverse(IODirection d);

// :note: the data are packed in format LSB data0,data1,...,vld0,vld1,... MSB
enum IOVectorizationType {
	IOV_SCALAR_SPARSE,		   // the disabled lanes are allowed on any position
	IOV_SCALAR_SPARSE_SYNCED, // special case of SPARSE where data are on known positions
				   // synchronized by other means and no additional conversion
				   // is required for this channel
	IOV_SCALAR_PACKED // valid segments packed at the beginning of the array,
		   // the disabled lanes may appear only at the end of the word.
};
struct IOVectorizationMd {
	IOVectorizationType type; //:see: IOVectorization
	std::optional<unsigned> laneCnt; // specifies the factor of vectorization,
									 // == how many lanes there will be in the vector 
    bool operator==(IOVectorizationMd const &) const = default;
};

class HwtHlsIoMetadata {
public:
	// non-optional members:
	IODirection direction;
	size_t addrWidth; // width of address for addressed io (0 for scalars)
	size_t readWordWidth; // specifies the native width of a single load from this io
	size_t writeWordWidth; // specifies the native width of a single store to this io
	llvm::Function *otherThreadFn; // :note: other thread or nullptr if this argument is connected to a top IO
	size_t otherArgIndex; // index of argument in other thread or at top where this IO is connected

	// optional members:

	// non-blocking load have extra 1 bit (msb) which specifies
	// if the read data is valid or not
	// :note: if hasBlockingLoad then readWordWidth = data width + 1
	bool hasBlockingLoad;
	bool hasBlockingStore; // hasBlockingLoad equivalent for store
	size_t bufferCapacity; // size of FIFO buffer for scalar io (0 means the size is infered automatically)
	// :note: if two HwtHlsIoMetadata are connected together using otherThreadFn/otherArgIndex the total buffer size is the sum from both
	llvm::MDTuple *ioPropertyPath; // optional property path specifying where exactly is this io connected on io object
	// (which is specified by otherThreadFn, otherArgIndex)
	// :note: typically used for IO which dissolve to communication on multiple channels like AMBA AXI4
	llvm::MDTuple *latenciesFromPredecessorIo; // optional tuple of latencies to other io of this function
	// the number is signed int where -1 marks not-specified value and the >=0 value marks how many
	// clock cycles must be left between predecessor and this IO during scheduling
	llvm::MDTuple *ioProtocolMd; // IO type dependent tuple specifying additional info about IO, e.g. StreamChannelFormatInfo
	std::optional<IOVectorizationMd> ioVectorization; // Specifies if and how the vectorization should/is allowed be performed
	std::vector<llvm::Metadata*> unparsedMd; // string or tuple with string as first operand

	static const std::string METADATA_NAME; // primary name under HwtHlsIoMetadata is stored as function metadata
	// secondary metadata names for members inside of HwtHlsIoMetadata tuple
	static const std::string METADATA_NAME_NON_BLOCKING_LOAD; // if this string appears in HwtHlsIoMetadata tuple hasBlockingLoad=true
	static const std::string METADATA_NAME_NON_BLOCKING_STORE; // same as METADATA_NAME_NON_BLOCKING_LOAD just for Store
	// following metadata names are used as a name of optional tuple for HwtHlsIoMetadata for example !{!"BUFFER_CAPACITY", i32 num}
	static const std::string METADATA_NAME_BUFFER_CAPACITY; // specifies bufferCapacity
	static const std::string METADATA_NAME_IO_PROPERTY_PATH; // specifies ioPropertyPath
	static const std::string METADATA_NAME_LATENCIES_FROM_PREDECESSOR_IO; // specifies latenciesFromPredecessorIo
	static const std::string METADATA_NAME_IO_PROTOCOL; // specifies ioProtocolMd
	static const std::string METADATA_NAME_IO_VECTORIZATION; // specifies ioVectorization

	HwtHlsIoMetadata() :
			direction(IODirection::IO_DIR_UNRESOLVED), addrWidth(0), readWordWidth(
					1), writeWordWidth(1), otherThreadFn(nullptr), otherArgIndex(
					0), hasBlockingLoad(true), hasBlockingStore(true), bufferCapacity(
					0), ioPropertyPath(nullptr), latenciesFromPredecessorIo(
					nullptr), ioProtocolMd(nullptr) {

	}
	HwtHlsIoMetadata(IODirection direction, size_t addrWidth,
			size_t readWordWidth, size_t writeWordWidth,
			llvm::Function *otherThreadFn, size_t otherArgIndex,
			bool hasBlockingLoad = true, bool hasBlockingStore = true,
			size_t bufferCapacity = 0, llvm::MDTuple *ioPropertyPath = nullptr,
			llvm::MDTuple *latenciesFromPredecessorIo = nullptr,
			llvm::MDTuple *ioProtocolMd = nullptr,
			std::optional<IOVectorizationMd> ioVectorization = { },
			const std::vector<llvm::Metadata*> &unparsedMd = { }) :
			direction(direction), addrWidth(addrWidth), readWordWidth(
					readWordWidth), writeWordWidth(writeWordWidth), otherThreadFn(
					otherThreadFn), otherArgIndex(otherArgIndex), hasBlockingLoad(
					hasBlockingLoad), hasBlockingStore(hasBlockingStore), bufferCapacity(
					bufferCapacity), ioPropertyPath(ioPropertyPath), latenciesFromPredecessorIo(
					latenciesFromPredecessorIo), ioProtocolMd(ioProtocolMd),
					ioVectorization(ioVectorization), unparsedMd(unparsedMd) {
		if (hasBlockingLoad || !hasBlockingStore)
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
	bool operator==(HwtHlsIoMetadata const &) const = default;

	//bool operator==(const HwtHlsIoMetadata &other) const;
	void print(llvm::raw_ostream &O, bool IsForDebug = false) const;

};

std::pair<llvm::Type*, llvm::Type*> getIrLoadOrStoreElementType(
		const llvm::Argument &arg);
std::pair<llvm::Type*, llvm::Type*> getIrLoadOrStoreElementType(
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
