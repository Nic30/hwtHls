#include <stdint.h>


inline uint64_t log2ceil(uint64_t x) {
	// https://graphics.stanford.edu/~seander/bithacks.html#IntegerLogObvious
	uint64_t v = (x - 1); // word to find the log base 2 of
	uint64_t r = 0; // r will be lg(v)
	while (v > 0) {
		v >>= 1;
		r++;
	}
	return r;
}

inline bool isPow2(uint64_t x) {
	if (x == 0)
		return false;

	while (x != 1) {
		if ((x & 1) != 0)
			return false;
		x >>= 1;
	}
	return true;
}
