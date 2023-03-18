#include <llvm/IR/Value.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/IR/IRBuilder.h>
#include <map>

namespace hwtHls {

struct OffsetWidthValue {
	uint64_t offset; // bit index where slice starts
	uint64_t width; // of result
	llvm::Value *value; // which is being sliced on
	bool operator==(const OffsetWidthValue &rhs) const;
};

void IRBuilder_setInsertPointBehindPhi(llvm::IRBuilder<> & builder, llvm::Instruction*I);

class ConcatMemberVector {
	llvm::Value* _memberToValue(OffsetWidthValue &item);
public:
	/*
	 * :ivar members: lower bits first arguments for a bit concatenation
	 * */
	llvm::SmallVector<OffsetWidthValue> members;
	llvm::IRBuilder<> &builder;
	std::unordered_map<OffsetWidthValue, llvm::Value*> &commonSubexpressionCache;

	ConcatMemberVector(llvm::IRBuilder<> &builder,
			std::unordered_map<OffsetWidthValue, llvm::Value*> & commonSubexpressionCache);

	void push_back(OffsetWidthValue item);

	llvm::Value* resolveValue(llvm::Instruction *builderPosition);

	uint64_t width();
};

OffsetWidthValue BitRangeGetOffsetWidthValue(llvm::CallInst *C);

}

template<>
struct std::hash<hwtHls::OffsetWidthValue> {
	std::size_t operator()(hwtHls::OffsetWidthValue const &s) const noexcept {
		std::size_t h = std::hash<uint64_t> { }(s.offset);
		h ^= std::hash<uint64_t> { }(s.width) << 1;
		h ^= std::hash<void*> { }(s.value) << 1;
		return h;
	}
};
