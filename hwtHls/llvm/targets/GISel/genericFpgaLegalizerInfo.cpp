#include "genericFpgaLegalizerInfo.h"
#include "../genericFpgaTargetSubtarget.h"

#ifdef LLVM_NDEBUG
#define NDEBUG 1
#endif

namespace llvm {

GenericFpgaLegalizerInfo::GenericFpgaLegalizerInfo(
		const GenericFpgaTargetSubtarget &ST): LegalizerInfo() {
	//auto & LLI = getLegacyLegalizerInfo();
	using namespace TargetOpcode;
	// add natively supported ops as legal
	for (auto op : { G_IMPLICIT_DEF, G_CONSTANT, G_SELECT, G_BRCOND, G_ICMP, G_ADD, G_SUB,
			G_MUL, G_LOAD, G_STORE, G_PHI, G_AND, G_OR, G_XOR, G_EXTRACT,
			G_MERGE_VALUES, G_ZEXT, G_SEXT }) {
		getActionDefinitionsBuilder(op) //
		.alwaysLegal();
	}
	//LLI.computeTables();
	getLegacyLegalizerInfo().computeTables();
	verify(*ST.getInstrInfo());
}

}
