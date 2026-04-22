#pragma once
#include <list>
#include <cassert>
#include <unordered_map>
#include <vector>

namespace hwtHls::techmap {

template<typename T>
class pool {
protected:
	std::list<T> m_list;
	using listIt = std::list<T>::iterator;
	std::unordered_map<T, listIt> m_item_position;
public:
	pool() {
	}
	pool(const pool<T> & items) {
		// otherwise m_item_position will be pointing to m_list in items instead of this->m_list
		for (auto item : items) {
			insert(item);
		}
	}
	pool(std::initializer_list<T> items) {
		for (auto item : items) {
			insert(item);
		}
	}
	pool(std::vector<T> items) {
		for (auto item : items) {
			insert(item);
		}
	}

	void insert(T item) {
		if (m_item_position.find(item) == m_item_position.end()) {
			m_list.push_back(item);
			m_item_position.insert(std::make_pair(item, std::prev(m_list.end())));
		}
	}

	template<class InputIterator>
	void insert(InputIterator first, InputIterator last) {
		for (; first != last; ++first)
			insert(*first);
	}

	void erase(T item) {
		auto pos = m_item_position.find(item);
		assert(pos != m_item_position.end());
		m_list.erase(pos->second);
		m_item_position.erase(pos);
	}
	void clear() {
		m_list.clear();
		m_item_position.clear();
	}

	T pop() {
		T item = m_list.front();
		m_list.pop_front();
		m_item_position.erase(item);
		return item;
	}
	bool contains(T item) const {
		return m_item_position.find(item) != m_item_position.end();
	}
	bool empty() const {
		return m_list.empty();
	}
	void reserve(size_t newSize) {
	}
	size_t size() const {
		return m_list.size();
	}
	auto begin() {
		return m_list.begin();
	}
	auto end() {
		return m_list.end();
	}
	auto begin() const {
		return m_list.begin();
	}
	auto end() const {
		return m_list.end();
	}
	void consystencyCheck() {
		assert(m_list.size() == m_item_position.size());
		for (auto &v: m_item_position) {
			bool foundInList = false;
			for (auto listIt = m_list.begin(); listIt != m_list.end(); ++listIt) {
				if (v.second == listIt) {
					foundInList = true;
					break;
				}
			}
			assert(foundInList);
		}
	}
	pool<T>& operator=(const pool<T>& other)
	{
	    this->clear();
		for (auto item : other) {
			insert(item);
		}
	    return *this;
	}
	bool operator==(const pool<T> &other) const {
		if (size() != other.size())
			return false;
		for (auto item : other) {
			if (!contains(item))
				return false;
		}
		return true;
	}
};

}
