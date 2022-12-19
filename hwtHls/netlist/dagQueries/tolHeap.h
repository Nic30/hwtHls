#pragma once

#include <vector>
#include <algorithm>
#include <string>
#include <cstring>
#include <assert.h>
#include <limits.h>

#include "tolMap.h"
#include "tolVector.h"

namespace TOL {

/*
 * An implementation of heap where key is separated from a value
 * Heap property is maintained for values, the item can be modified using key.
 *
 * */
template<typename _Value>
class TolHeap {
public:
	using _Key = unsigned;
private:
	class Key_Value {
	public:
		_Key key;
		_Value value;

		Key_Value() :
				key(0) {
		}

		Key_Value(const _Key &k, const _Value &v) {
			key = k;
			value = v;
		}
	};
	TolMap<_Key> pos; // used to store positions of keys in m_data
	TolVector<Key_Value> m_data; // storage for heap items

	void up(unsigned p) {
		Key_Value x = m_data[p];
		for (; p > 0 && x.value < m_data[(p - 1) / 2].value; p = (p - 1) / 2) {
			m_data[p] = m_data[(p - 1) / 2];
			pos.insert(m_data[p].key, p);
		}
		m_data[p] = x;
		pos.insert(x.key, p);
	}
	void down(unsigned p) {
		Key_Value tmp;

		for (unsigned i; p < m_data.size(); p = i) {
			if (p * 2 + 1 < m_data.size()
					&& m_data[p * 2 + 1].value < m_data[p].value)
				i = p * 2 + 1;
			else
				i = p;
			if (p * 2 + 2 < m_data.size()
					&& m_data[p * 2 + 2].value < m_data[i].value)
				i = p * 2 + 2;
			if (i == p)
				break;

			tmp = m_data[p];
			m_data[p] = m_data[i];
			pos.insert(m_data[p].key, p);
			m_data[i] = tmp;
		}

		pos.insert(m_data[p].key, p);
	}
public:

	void initialize(size_t n) {
		pos.initialize(n);
		m_data.reserve(1024);
	}

	_Key head() {
		return m_data[0].key;
	}

	void clear() {
		pos.occur.clear();
	}

	void insert(_Key x, _Value y) {
		if (pos.notexist(x)) {
			// insert, regenerate heap
			m_data.push_back(Key_Value(x, y));
			pos.insert(x, m_data.size() - 1);
			up(m_data.size() - 1);
		} else {
			// update data, regenerate heap
			if (y < m_data[pos.get(x)].value) {
				m_data[pos.get(x)].value = y;
				up(pos.get(x));
			} else {
				m_data[pos.get(x)].value = y;
				down(pos.get(x));
			}
		}
	}
	_Key pop() {
		_Key tmp = m_data[0].key;
		pos.erase(tmp);
		if (m_data.size() == 1) {
			// only 1 item, no heap regeneration required
			m_data.pop_back();
			return tmp;
		}
		m_data[0] = m_data[m_data.size() - 1];
		m_data.pop_back();
		down(0);
		return tmp;
	}

	bool empty() {
		return (m_data.size() == 0);
	}
};

}
