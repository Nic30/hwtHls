#pragma once
#include <map>
#include <set>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

enum IODirection {
	IO_DIR_IN, IO_DIR_OUT, IO_DIR_UNRESOLVED,
};

// :note: This record is an override of default argument connections.
//   if argument is connected directly to topIo on same index there is not metadata.
struct HwtHlsIoMetadata {
	IODirection direction;
	size_t addrWidth; // width of address for addressed io (0 for scalars)
	llvm::Function *otherThreadFn; // :note: other thread or nullptr if this argument is connected to a top IO
	size_t otherArgIndex; // index of argument in other thread or at top where this IO is connected
	HwtHlsIoMetadata() :
			direction(IO_DIR_UNRESOLVED), addrWidth(0), otherThreadFn(nullptr), otherArgIndex(
					0) {

	}
	HwtHlsIoMetadata(IODirection direction, size_t addrWidth,
			llvm::Function *otherThreadFn, size_t otherArgIndex) :
			direction(direction), addrWidth(addrWidth), otherThreadFn(
					otherThreadFn), otherArgIndex(otherArgIndex) {
	}
	bool isDefaultValue() const;
};

extern const std::string METADATA_NAME_hwtHlsIo;

llvm::SmallVector<HwtHlsIoMetadata> HwtHlsIoMetadata_get(llvm::Function &F);
HwtHlsIoMetadata HwtHlsIoMetadata_get(llvm::Metadata &hwtHlsIOItem);
std::optional<HwtHlsIoMetadata> HwtHlsIoMetadata_get(llvm::Function &F, size_t argI);
void HwtHlsIoMetadata_set(llvm::Function &F,
		const llvm::SmallVector<HwtHlsIoMetadata> &mds);

}
