#include "genericFpgaLegalizerInfo.h"

namespace llvm {

GenericFpgaLegalizerInfo::GenericFpgaLegalizerInfo(
		const GenericFpgaTargetSubtarget &ST) {
	getLegacyLegalizerInfo().computeTables();

	using namespace TargetOpcode;
	// add natively supported ops as legal
	for (auto op : { G_IMPLICIT_DEF, G_CONSTANT, G_SELECT, G_BRCOND, G_ICMP, G_ADD, G_SUB,
			G_LOAD, G_STORE, G_PHI, G_AND, G_OR, G_XOR, G_EXTRACT,
			G_MERGE_VALUES, G_ZEXT, G_SEXT }) {
		getActionDefinitionsBuilder(op) //
		.alwaysLegal();
	}

}

}
