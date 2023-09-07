#pragma once
#include <set>
#include <map>
#include <optional>
#include <llvm/IR/Instructions.h>
#include <llvm/ADT/SetVector.h>

namespace hwtHls {

class StreamChunkMeta {
public:
	virtual llvm::raw_ostream& print(llvm::raw_ostream &OS) const = 0;
	virtual ~StreamChunkMeta() {
	}
};

// Container which holds information about if the chunk write is las in packet or not.
class StreamChunkLastMeta: public StreamChunkMeta {
public:
	std::optional<bool> isLast;
	llvm::Value *isLastExpr;
	bool prevWordMayBePending;

	StreamChunkLastMeta(std::optional<bool> isLast, llvm::Value *isLastExpr) :
			isLast(isLast), isLastExpr(isLastExpr) {
		prevWordMayBePending = true;
	}
	virtual llvm::raw_ostream& print(llvm::raw_ostream &OS) const override;
};

class StreamEoFMeta: public StreamChunkMeta {
public:
	bool inlinedToPredecessors;
	StreamEoFMeta(bool inlinedToPredecessors) :
			inlinedToPredecessors(inlinedToPredecessors) {
	}
	virtual llvm::raw_ostream& print(llvm::raw_ostream &OS) const override;
};

inline llvm::raw_ostream& operator<<(llvm::raw_ostream &OS,
		const hwtHls::StreamChunkMeta &V) {
	V.print(OS);
	return OS;
}

/**
 * Detector of informations about stream read/write operations for control flow graph
 *
 * :ivar cfg: the dependencies of reads/writes as they appear in code
 * :note: None represents the starting node
 * :ivar DATA_WIDTH: number of bits of data in a single stream word
 * :ivar allStms: list of all reads/writes to keep all structures ordered in deterministic order
 */
class StreamIoDetector {
public:
	using HlsReadOrWrite = llvm::CallInst;
	static constexpr HlsReadOrWrite *BEGIN = nullptr;
	const size_t DATA_WIDTH;
	const llvm::SetVector<const HlsReadOrWrite*> &allStms;

	std::map<const HlsReadOrWrite*,
			llvm::SetVector<std::pair<size_t, const HlsReadOrWrite*>>> cfg;
	std::map<const HlsReadOrWrite*, std::vector<size_t>> inWordOffset;
	std::map<const HlsReadOrWrite*, llvm::SetVector<const HlsReadOrWrite*>> predecessors;
	std::map<const HlsReadOrWrite*, std::unique_ptr<StreamChunkMeta>> ioInstrMeta;

    // temporary containers for other algs to use
	std::map<const llvm::BasicBlock*, std::set<const llvm::BasicBlock*>> seenPredecessors;
	std::set<const HlsReadOrWrite*> resolvedStms;

	// map used outside of this class to mark which blocks were visited
	StreamIoDetector(size_t DATA_WIDTH,
			const llvm::SetVector<const HlsReadOrWrite*> &allStms);
	void _addTransition(const HlsReadOrWrite *src, size_t dstInWordOffset,
			const HlsReadOrWrite *dst);

	/**
	 * DFS search all read/write sequences
	 *
	 * :param seenBlockOffsets: set of blocks which were seen for this specific position in packet
	 * :note: 1 read/write instance can actually be read/write multiple times e.g. in cycle
	 * however the thing what we care about are possible successor reads/writes of a read/write
	 * :param seenBlocks: a set to identify cycles during processing
	 */
	void _detectIoAccessGraphs(const HlsReadOrWrite *predecessor,
			size_t predEndOffset, const llvm::BasicBlock &block,
			std::set<std::tuple<const HlsReadOrWrite*, size_t, const llvm::BasicBlock*>> &seenBlocks,
			std::set<std::pair<size_t, const llvm::BasicBlock*>> &seenBlockOffsets);
	void detectIoAccessGraphs(const llvm::BasicBlock &startBlock);
	void resolvePossibleOffset();
	const llvm::BasicBlock* findStartBlock();
	const llvm::BasicBlock* _findStartBlock(
			const llvm::SetVector<std::pair<size_t, const HlsReadOrWrite*>> &firstInstrs);
	void _collectAllPredecessors(const llvm::BasicBlock &BB,
			std::set<const llvm::BasicBlock*> &seen);
	const llvm::BasicBlock* _findCommonPredecessorOfBlocks(
			const std::vector<const llvm::BasicBlock*> &blocks);
	llvm::raw_ostream& print(llvm::raw_ostream &OS) const;
};
inline llvm::raw_ostream& operator<<(llvm::raw_ostream &OS,
		const hwtHls::StreamIoDetector &V) {
	V.print(OS);
	return OS;
}
}
