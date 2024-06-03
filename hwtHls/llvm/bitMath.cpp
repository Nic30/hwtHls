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

void iterUsedBitRangeSlices(const llvm::APInt &useMask,
		std::function<void(size_t, size_t)> consumer) {
	if (useMask.isZero())
		return;
	if (useMask.isAllOnes()) {
		// no need for pruning
		consumer(0, useMask.getBitWidth());
		return;
	}

	// prune values which do not have the specific bit mask set
	int l = -1; // -1 as invalid value
	for (unsigned h = 0; h < useMask.getBitWidth(); ++h) {
		if (l == -1 && useMask[h]) {
			l = h;
		}

		// end of 1 sequence found
		if (l != -1 && (h == useMask.getBitWidth() - 1 || !useMask[h + 1])) {
			// start of 1 sequence, (+1 because [1:0] is 1b)
			unsigned w = h - l + 1;
			consumer(l, w);
			l = -1; // reset start;
		}
	}
}

}
