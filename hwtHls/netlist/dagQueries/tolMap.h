#pragma once

#include <limits.h>
#include <assert.h>

#include "tolVector.h"

namespace TOL {

template<typename _T>
class TolMap {
	size_t alloc_size;
	size_t item_cnt;
	std::vector<_T> m_key2val; // always ending with handle END
public:
	TolVector<size_t> occur; //
	static constexpr int END = INT_MAX;

	TolMap() {
		alloc_size = 0;
		item_cnt = 0;
	}
	size_t size() {
		return item_cnt;
	}
	void reserve(size_t cap) {
		m_key2val.reserve(cap);
	}
	void resize(size_t newSize) {
		size_t prevSize = alloc_size;
		m_key2val.resize(newSize);
		if (prevSize < newSize)
			for (size_t i = prevSize; i < newSize; ++i)
				m_key2val[i] = END;
		alloc_size = newSize;

	}
	void initialize(size_t n) {
		occur.clear();
		alloc_size = n;
		item_cnt = 0;
		m_key2val.resize(alloc_size);
		for (size_t i = 0; i < alloc_size; ++i)
			m_key2val[i] = END;
	}

	void clear() {
		for (size_t i = 0; i < occur.size(); ++i) {
			m_key2val[occur[i]] = END;
		}
		occur.clear();
		item_cnt = 0;
	}
	_T get(unsigned p) {
		assert(p < alloc_size);
		return m_key2val[p];
	}
	void erase(unsigned p) {
		assert(p < alloc_size);
		m_key2val[p] = END;
		item_cnt--;
	}
	bool notexist(unsigned p) {
		return !exist(p);
	}
	bool exist(unsigned p) {
		assert(p < alloc_size);
		return !(m_key2val[p] == END);
	}
	void insert(unsigned p, _T d) {
		assert(p < alloc_size);
		if (m_key2val[p] == END) {
			occur.push_back(p);
			item_cnt++;
		}
		m_key2val[p] = d;
	}
	void inc(unsigned p) {
		assert(p < alloc_size);
		assert(m_key2val[p] != END);
		m_key2val[p]++;
	}
};

}
