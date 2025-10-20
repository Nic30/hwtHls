
// Placeholder instruction for netlist object which will be aded later in translation
// 
// inputs are in format $objId, $dstWidt, $src[n], $srcWidth[n], $enCond
class _HWTFPGA_PYOBJECT_PLACEHOLDER : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins variable_ops),
    []>;

def HWTFPGA_PYOBJECT_PLACEHOLDER: _HWTFPGA_PYOBJECT_PLACEHOLDER {
    	let hasSideEffects = false;
		let isNotDuplicable = false;
    }

def HWTFPGA_PYOBJECT_PLACEHOLDER_WITH_SIDEEFFECT: _HWTFPGA_PYOBJECT_PLACEHOLDER {
    	let hasSideEffects = true;
		let isNotDuplicable = false;
    }

def HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE: _HWTFPGA_PYOBJECT_PLACEHOLDER {
    	let hasSideEffects = false;
		let isNotDuplicable = true;
    }
    
def HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE_WITH_SIDEEFECT: _HWTFPGA_PYOBJECT_PLACEHOLDER {
    	let hasSideEffects = true;
		let isNotDuplicable = true;
    }
     
