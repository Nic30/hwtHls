#include <hwtHls/llvm/bitMath.h>

namespace hwtHls {

std::vector<std::pair<bool, unsigned>> iter1and0sequences(
		const llvm::APInt &c, unsigned offset, unsigned width) {
	assert(
			width + offset <= c.getBitWidth()
					&& "offset and width is there to slice the APInt value");
	// if the bit in c is 0 the output bit should be also 0 else it is bit from v
	int l_1 = -1; // start of 1 sequence, -1 as invalid value
	int l_0 = -1; // start of 0 sequence, -1 as invalid value
	unsigned endIndex = offset + width;
	std::vector<std::pair<bool, unsigned>> res;
	for (unsigned h = offset; h < endIndex; ++h) {
		if (l_1 == -1 && c[h]) {
			l_1 = h; // start of 1 sequence
		} else if (l_0 == -1 && !c[h]) {
			l_0 = h; // start of 0 sequence
		}

		bool last = h == endIndex - 1;
		if (l_1 != -1 && (last || !c[h + 1])) {
			// end of 1 sequence found
			unsigned w = h - l_1 + 1;
			res.push_back( { 1, w });
			l_1 = -1; // reset start;
		} else if (l_0 != -1 && (last || c[h + 1])) {
			// end of 0 sequence found
			unsigned w = h - l_0 + 1;
			res.push_back( { 0, w });
			l_0 = -1; // reset start;
		}
	}
	return res;
}

size_t getOneSequenceEnd(size_t off, const llvm::APInt &val) {
	while (off < val.getBitWidth() && val[off]) {
		++off;
	}
	return off;
}

}
