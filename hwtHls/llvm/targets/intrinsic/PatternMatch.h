#pragma once

#include <llvm/IR/Instructions.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

namespace hwtHls {
namespace PatternMatch {
// :see: llvm::PatternMatch in llvm/IR/PatternMatch.h

/*
 * matcher for BitrangeGet intrinsic
 * */
template<typename Src_t>
struct m_BitrangeGet {
	Src_t src;
	size_t &offset;
	size_t &width;

	m_BitrangeGet(const Src_t &src, size_t &offset, size_t &width) :
			src(src), offset(offset), width(width) {
	}

	template<typename OpTy> inline bool match(OpTy *V) const {
		if (auto C = dyn_cast<llvm::CallInst>(V)) {
			if (IsBitRangeGet(C)) {
				offset = BitRangeGetOffset(C);
				width = C->getType()->getIntegerBitWidth();
				return src.match(C->getArgOperand(0));
			}
		}
		return false;
	}
};

/*
 * Same as :class:`m_BitrangeGet` but offset and width must have specified value
 * */
template<typename Src_t>
struct m_BitrangeGetSpecificConst {
	Src_t src;
	const size_t offset;
	const size_t width;

	m_BitrangeGetSpecificConst(const Src_t &src, size_t offset, size_t width) :
			src(src), offset(offset), width(width) {
	}

	template<typename OpTy> inline bool match(OpTy *V) const {
		if (auto C = dyn_cast<llvm::CallInst>(V)) {
			if (IsBitRangeGet(C)) {
				if (offset != BitRangeGetOffset(C))
					return false;
				if (width != C->getType()->getIntegerBitWidth())
					return false;
				return src.match(C->getArgOperand(0));
			}
		}
		return false;
	}
};

}
}
