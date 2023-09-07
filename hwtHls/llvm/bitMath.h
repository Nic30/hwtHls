#pragma once
#include <stddef.h>
#include <stdlib.h>
#include <vector>
#include <functional>

#include <llvm/ADT/APInt.h>

namespace hwtHls {

inline size_t log2ceil(size_t x) {
	if (x == 0)
		return 1;
	size_t result = 0;
	--x;
	while (x > 0) {
		++result;
		x >>= 1;
	}
	return result;
}

inline long div_ceil(long numerator, long denominator) {
	std::ldiv_t res = std::div(numerator, denominator);
	return res.rem ? (res.quot + 1) : res.quot;
}

// https://stackoverflow.com/questions/466204/rounding-up-to-next-power-of-2
inline uint32_t upperPow2(uint32_t v) {
	v--;
	v |= v >> 1;
	v |= v >> 2;
	v |= v >> 4;
	v |= v >> 8;
	v |= v >> 16;
	v++;
	return v;
}

// :returns: a vector of pairs where first specifies the value of bits in segment and the second specifies length of segment
//   little endiand, lowest bit first.
std::vector<std::pair<bool, unsigned>> iter1and0sequences(const llvm::APInt &c,
		unsigned offset, unsigned width);
size_t getOneSequenceEnd(size_t off, const llvm::APInt &val);

/*
 * :param consumer: first argument is offset second is width of segment which has 1 in useMask
 * */
void iterUsedBitRangeSlices(const llvm::APInt &useMask,
		std::function<void(size_t, size_t)> consumer);
}
