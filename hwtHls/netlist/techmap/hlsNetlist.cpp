#include <assert.h>
#include <hwtHls/netlist/techmap/hlsNetlist.h>
#include <sstream>

namespace hwtHls {

HlsNetNodeIn::HlsNetNodeIn(HlsNetNode &obj) :
	obj(&obj), in_i(obj._inputs.size()) {}

bool HlsNetNodeIn::operator==(const HlsNetNodeIn &RHS) const {
	return obj == RHS.obj && in_i == RHS.in_i;
}

HlsNetNodeOut::HlsNetNodeOut(HlsNetNode &obj) :
	obj(&obj), out_i(obj._outputs.size()) {}

void HlsNetNodeOut::connectHlsIn(const HlsNetNodeIn &in) const {
	assert(!in.obj->dependsOn[in.in_i].has_value());
	in.obj->dependsOn[in.in_i] = *this;
	obj->usedBy[out_i].push_back(in);
}

bool HlsNetNodeOut::operator==(const HlsNetNodeOut &RHS) const {
	return obj == RHS.obj && out_i == RHS.out_i;
}

HlsNetNodeInDepNodes::Iterator::Iterator(
	std::vector<std::optional<HlsNetNodeOut>>::iterator ptr,
	std::vector<std::optional<HlsNetNodeOut>>::iterator end) :
	m_ptr(ptr), m_end(end) {
	while (m_ptr != m_end && !m_ptr->has_value()) {
		++m_ptr;
	}
}

HlsNetNodeInDepNodes::Iterator::reference
HlsNetNodeInDepNodes::Iterator::operator*() const {
	assert(m_ptr->has_value());
	return *m_ptr->value().obj;
}

HlsNetNodeInDepNodes::Iterator::pointer
HlsNetNodeInDepNodes::Iterator::operator->() {
	if (m_ptr->has_value())
		return m_ptr->value().obj;
	else
		return nullptr;
}
HlsNetNodeInDepNodes::Iterator &HlsNetNodeInDepNodes::Iterator::operator++() {
	m_ptr++;
	while (m_ptr != m_end && !m_ptr->has_value()) {
		++m_ptr;
	}
	return *this;
}
HlsNetNodeInDepNodes::Iterator HlsNetNodeInDepNodes::Iterator::operator++(int) {
	Iterator tmp = *this;
	++(*this);
	return tmp;
}
bool HlsNetNodeInDepNodes::Iterator::operator==(const Iterator &b) const {
	return m_ptr == b.m_ptr;
}
bool HlsNetNodeInDepNodes::Iterator::operator!=(const Iterator &b) const {
	return m_ptr != b.m_ptr;
}

HlsNetNodeInDepNodes::Iterator HlsNetNodeInDepNodes::begin() {
	return Iterator(node.dependsOn.begin(), node.dependsOn.end());
}
HlsNetNodeInDepNodes::Iterator HlsNetNodeInDepNodes::end() {
	return Iterator(node.dependsOn.end(), node.dependsOn.end());
}

HlsNetNodeInDepNodes::HlsNetNodeInDepNodes(HlsNetNode &node) :
	node(node) {}

HlsNetNodeOutUserNodes::Iterator::Iterator(
	UseListIt uselistIt, UseListIt uselistItEnd,
	std::vector<HlsNetNodeIn>::iterator inUseListPos) :
	m_uselist(uselistIt),
	m_uselist_end(uselistItEnd),
	m_uselist_pos(inUseListPos) {
	// iterate to first user or to end of this iterator
	while (m_uselist != m_uselist_end) {
		if (m_uselist_pos != m_uselist->end())
			break;
		++m_uselist;
		if (m_uselist == m_uselist_end) {
			m_uselist_pos = _VEC_VEC_IN_END;
		} else if (m_uselist->empty()) {
			m_uselist_pos = _VEC_VEC_IN_END;
			continue;			
		} else {
			m_uselist_pos = m_uselist->begin();
		}
	}
}

HlsNetNodeOutUserNodes::Iterator::reference
HlsNetNodeOutUserNodes::Iterator::operator*() const {
	assert(m_uselist != m_uselist_end);
	assert(m_uselist_pos != m_uselist->end());
	assert(m_uselist_pos != _VEC_VEC_IN_END);
	return *m_uselist_pos->obj;
}
HlsNetNodeOutUserNodes::Iterator::pointer
HlsNetNodeOutUserNodes::Iterator::operator->() {
	assert(m_uselist != m_uselist_end);
	return m_uselist_pos->obj;
}
HlsNetNodeOutUserNodes::Iterator &
HlsNetNodeOutUserNodes::Iterator::operator++() {
	// for uses in self.usedBy:
	//     for u in uses:
	//     		yield u.obj
	assert(m_uselist != m_uselist_end);
	assert(m_uselist_pos != m_uselist->end());
	assert(m_uselist_pos != _VEC_VEC_IN_END);

	m_uselist_pos++;
	while (m_uselist_pos == m_uselist->end()) {
		++m_uselist;
		if (m_uselist == m_uselist_end) {
			m_uselist_pos = _VEC_VEC_IN_END;
			break;
		} else if (m_uselist->empty()) {
			m_uselist_pos = _VEC_VEC_IN_END;
			continue;
		} else {
			m_uselist_pos = m_uselist->begin();
		}
	}
	if (m_uselist == m_uselist_end) {
		assert(m_uselist_pos == _VEC_VEC_IN_END);
	} else {
		assert(m_uselist_pos != m_uselist->end());
		assert(m_uselist_pos != _VEC_VEC_IN_END);
	}
	return *this;
}
HlsNetNodeOutUserNodes::Iterator
HlsNetNodeOutUserNodes::Iterator::operator++(int) {
	Iterator tmp = *this;
	++(*this);
	return tmp;
}
bool HlsNetNodeOutUserNodes::Iterator::operator==(const Iterator &b) const {
	return m_uselist == b.m_uselist && m_uselist_pos == b.m_uselist_pos;
}
bool HlsNetNodeOutUserNodes::Iterator::operator!=(const Iterator &b) const {
	return m_uselist != b.m_uselist || m_uselist_pos != b.m_uselist_pos;
}

HlsNetNodeOutUserNodes::Iterator HlsNetNodeOutUserNodes::begin() {
	return Iterator(node.usedBy.begin(), node.usedBy.end(),
					node.usedBy.empty() ? _VEC_VEC_IN_END
										: node.usedBy.begin()->begin());
}
HlsNetNodeOutUserNodes::Iterator HlsNetNodeOutUserNodes::end() {
	return Iterator(node.usedBy.end(), node.usedBy.end(), _VEC_VEC_IN_END);
}
HlsNetNodeOutUserNodes::HlsNetNodeOutUserNodes(HlsNetNode &node) :
	node(node) {}

const HlsNetNodeIn HlsNetNode::_addInput() {
	_inputs.push_back(HlsNetNodeIn(*this));
	dependsOn.push_back({});
	scheduledIn.push_back(0);
	inputWireDelay.push_back(0);
	inputClkTickOffset.push_back(0);
	return _inputs.back();
}

const HlsNetNodeOut HlsNetNode::_addOutput() {
	_outputs.push_back(HlsNetNodeOut(*this));
	usedBy.push_back({});
	scheduledOut.push_back(0);
	outputWireDelay.push_back(0);
	outputClkTickOffset.push_back(0);
	return _outputs.back();
}

HlsNetNodeInDepNodes HlsNetNode::iterInDepNodes() {
	return HlsNetNodeInDepNodes(*this);
}
HlsNetNodeOutUserNodes HlsNetNode::iterOutUserNodes() {
	return HlsNetNodeOutUserNodes(*this);
}

std::generator<HlsNetNode *>
HlsNetNode::iterAllNodesFlat(NODE_ITERATION_TYPE itTy) {
	switch (itTy) {
	case NODE_ITERATION_TYPE::ONLY_PARENT_PREORDER:
	case NODE_ITERATION_TYPE::ONLY_PARENT_POSTORDER:
		co_return;
	default:
		break;
	}
	co_yield this;
}

std::string HlsNetNode::__repr__() const {
	std::stringstream ss;
	ss << "<HlsNetNode(cpp) " << _id << " " << this << ">";
	return ss.str();
}

size_t HlsNetlistCtx::getUniqId() {
	auto res = _uniqNodeCntr;
	++_uniqNodeCntr;
	return res;
}

HlsNetNode *HlsNetlistCtx::createNode(size_t inCnt, size_t outCnt,
									  std::optional<size_t> id) {
	if (id.has_value()) {
		_uniqNodeCntr = std::max(_uniqNodeCntr, id.value() + 1);
	} else {
		id = getUniqId();
	}
	std::unique_ptr<HlsNetNode> n =
		std::make_unique<HlsNetNode>(*this, id.value());
	for (size_t i = 0; i < inCnt; ++i) {
		n->_addInput();
	}
	for (size_t i = 0; i < outCnt; ++i) {
		n->_addOutput();
	}
	auto _n = n.get();
	nodes.push_back(move(n));
	return _n;
}

} // namespace hwtHls
