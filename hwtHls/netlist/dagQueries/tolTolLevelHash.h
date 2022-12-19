#pragma once

#include <assert.h>

#include "tolVector.h"

namespace TOL {

class TolLevelHash {

	void reconstruct() {
		for (unsigned i = 0, j = 0; i < L2N.size(); ++i) {
			if (L2N[i] != INVALID) {
				N2L[L2N[i]] = N2L.size() + j * C;
				j++;
				L2N[i] = INVALID;
			}
		}

		for (unsigned i = 0; i < N2L.size(); ++i) {
			if (N2L[i] != INVALID)
				L2N[N2L[i]] = i;
		}

		Last = N2L.size() * (C + 1);
	}
	int C;
public:
	static constexpr int INVALID = -1;
	static constexpr size_t RECONSTRUCT_THRESHOLD = 1000;
	unsigned Last;
	TolVector<int> N2L, L2N;

	void reserveForNodes(size_t nodeCnt) {
		N2L.reserve(nodeCnt);
		N2L.resize(nodeCnt);
		Last = nodeCnt * C + nodeCnt;

	}
	void initialize(const std::vector<unsigned> &level, size_t levelExtraSizeMultiplier) {
		size_t n = level.size();
		C = levelExtraSizeMultiplier;
		Last = n * C + n;
		N2L.reserve(n);
		N2L.resize(n);
		L2N.reserve(Last + n);
		L2N.resize(Last + n);

		for (size_t i = 0; i < L2N.size(); ++i) {
			L2N[i] = INVALID;
		}

		for (size_t i = 0; i < N2L.size(); ++i) {
			N2L[i] = level[i] * C + n;
			L2N[level[i] * C + n] = i;
		}
	}

	void insert(int node, int level) {
		assert(level > 0);
		assert(level < (int )L2N.size());
		assert(node > 0);
		assert(node < (int )N2L.size());
		for (int i = level - 1; i > 0; --i) {
			assert(i > 0);
			if (L2N[i] == INVALID) {
				L2N[i] = node;
				N2L[node] = i;
				if (level - i > (int) RECONSTRUCT_THRESHOLD) {
					reconstruct();
				}
				return;
			} else {
				int tmp = L2N[i];
				L2N[i] = node;
				N2L[node] = i;
				assert(tmp > 0);
				assert(tmp < (int )N2L.size());
				node = tmp;
			}
		}

		assert("should never happen");
	}

	void remove(unsigned x) {
		L2N[N2L[x]] = INVALID;
		N2L[x] = INVALID;
	}

	bool nottop(int k, unsigned x) {
		return (N2L[x] >= ((int) N2L.size()) + C * k);
	}

	void swap(unsigned x, unsigned y) {
		remove(x);

		if (y == Last) {
			N2L[x] = y;
			L2N[y] = x;
			Last++;
		} else {
			insert(x, y);
		}
	}
};
}
