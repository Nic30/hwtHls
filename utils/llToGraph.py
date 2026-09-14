#!/usr/local/bin/python3
# encoding: utf-8
"""
Simple script which can convert LLVM LL (IR) to a graphwiz dot or asciiart graph for quick debug.

For asciiart you need graph-easy, it can be installed using:
sudo apt install libgraph-easy-perl

"""

import re
import subprocess
import sys
from typing import Optional

# -----------------------------------------------------------------------------
# LLVM identifier: %name or @"name" or @name, etc.
# We'll be fairly permissive: alnum, underscore, dot, paren, etc.
IDENTIFIER_RAW = r'[A-Za-z0-9_().]*'
IDENTIFIER_QUOTED = r'"[^"]*"'

# Label in function header: @name or @"name"
FUNC_NAME_RAW = r'@' + IDENTIFIER_RAW
FUNC_NAME_QUOTED = r'@"[^"]*"'

# Basic block label at start of line:
#   name:
#   "name with spaces":
# We allow both quoted and unquoted forms.
BB_LABEL_UNQUOTED = IDENTIFIER_RAW
BB_LABEL_QUOTED = r'"[^"]*"'

# -----------------------------------------------------------------------------
# Global compiled regexes
# -----------------------------------------------------------------------------

# Function header: define ... @name( or define ... @"name"(
FUNC_HEADER_RE = re.compile(
    r'^\s*define\s+.*?\s+(@?"?[^@\s(]+"?)\s*\('
)

# Basic block label: at start of line (after optional whitespace)
# Group 1: quoted label (without quotes)
# Group 2: unquoted label
BB_LABEL_RE = re.compile(
    r'^\s*(?:(' + BB_LABEL_QUOTED + r')|(' + BB_LABEL_UNQUOTED + r'))\s*:\s*'
)

# Terminators (we search inside a line after stripping comments)

# br label %target
BR_UNCOND_RE = re.compile(
    r'\bbr\s+label\s+%' + r'(' + IDENTIFIER_RAW + r')\b'
)

# br i1 %cond, label %t, label %f
BR_COND_RE = re.compile(
    r'\bbr\s+i1\s+%' + IDENTIFIER_RAW +
    r'\s*,\s*label\s+%' + r'(' + IDENTIFIER_RAW + r')' +
    r'\s*,\s*label\s+%' + r'(' + IDENTIFIER_RAW + r')\b'
)

# switch ... label %default [ ... ]
# We only capture the default label here; case labels are parsed separately.
SWITCH_DEFAULT_RE = re.compile(
    r'\bswitch\s+[^,]+,\s*label\s+%' + r'(' + IDENTIFIER_RAW + r')\s*\['
)

# Inside switch case list: label %target
SWITCH_CASE_LABEL_RE = re.compile(
    r'label\s+%' + r'(' + IDENTIFIER_RAW + r')'
)

# indirectbr ... [ ... label %t, label %f ... ]
INDIRECTBR_RE = re.compile(
    r'\bindirectbr\s+.*?\s*\['
)

INDIRECTBR_TARGET_RE = re.compile(
    r'label\s+%' + r'(' + IDENTIFIER_RAW + r')'
)

def llvm_ir_strip_comment(line: str) -> str:
    """
    Strip LLVM-style comment from a line.
    Comments start with ';' and go to end of line, but ';' inside quotes is not a comment.
    """
    in_string = False
    result_chars = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"' and (i == 0 or line[i - 1] != '\\'):
            in_string = not in_string
            result_chars.append(ch)
        elif ch == ';' and not in_string:
            # Comment starts here; ignore rest of line
            break
        else:
            result_chars.append(ch)
        i += 1
    return ''.join(result_chars).rstrip()


def parse_functions(ir: str) -> dict[str, list[str]]:
    """
    Parse LLVM IR text into a dict: function_name -> list of body lines (raw, with comments).
    """
    lines = ir.splitlines()
    funcs = {}
    current_func: Optional[str] = None
    current_body: list[str] = []
    brace_depth = 0

    for raw_line in lines:
        raw_line = llvm_ir_strip_comment(raw_line).strip()

        if current_func is None:
            m = FUNC_HEADER_RE.match(raw_line)
            if m:
                fname_raw = m.group(1)
                # Normalize function name: strip leading @ and optional quotes
                if fname_raw.startswith('@'):
                    fname_raw = fname_raw[1:]
                if fname_raw.startswith('"') and fname_raw.endswith('"'):
                    fname_raw = fname_raw[1:-1]
                current_func = fname_raw
                current_body = []
                # Count braces on this line (raw, but comments don't affect braces in practice)
                brace_depth = raw_line.count('{') - raw_line.count('}')
                if brace_depth == 0 and '{' in raw_line:
                    # Single-line function body (rare)
                    funcs[current_func] = current_body
                    current_func = None
                continue
            # Not inside a function yet
            continue

        # Inside a function body
        current_body.append(raw_line)
        brace_depth += raw_line.count('{') - raw_line.count('}')
        if brace_depth <= 0:
            funcs[current_func] = current_body
            current_func = None
            current_body = []

    return funcs


def extract_cfg_from_body(body: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """
    From a function body (list of raw lines), extract:
      - ordered list of basic block labels (as they appear)
      - dict: label -> list of successor labels

    Handles multi-line switch by accumulating lines until the matching ']' is found.
    """
    blocks_order: list[str] = []
    successors: dict[str, list[str]] = {}

    current_label: Optional[str] = None

    # For multi-line switch parsing
    in_switch = False
    switch_start_label: Optional[str] = None
    switch_buffer: list[str] = []

    for raw_line in body:
        line = llvm_ir_strip_comment(raw_line).strip()
        if not line:
            continue

        # If we are accumulating a switch, keep going until we see the closing ']'
        if in_switch:
            switch_buffer.append(raw_line)
            if ']' in raw_line:
                # End of switch; parse it now
                in_switch = False
                full_switch = ' '.join(switch_buffer)
                switch_buffer.clear()
                case_targets = SWITCH_CASE_LABEL_RE.findall(full_switch)

                if switch_start_label is not None:
                    succs = []
                    succs.extend(case_targets)
                    successors[switch_start_label] = succs
                switch_start_label = None
            continue

        # Check for basic block label
        m = BB_LABEL_RE.match(raw_line)
        if m:
            # Quoted or unquoted
            label = m.group(1) if m.group(1) is not None else m.group(2)
            current_label = label
            blocks_order.append(label)
            successors.setdefault(label, [])
            continue
        assert current_label is not None

        # Check for switch start (may be multi-line)
        if SWITCH_DEFAULT_RE.search(line):
            if '[' in line and ']' in line:
                # Single-line switch
                m_def = SWITCH_DEFAULT_RE.search(line)
                default_target = m_def.group(1) if m_def else None
                case_targets = SWITCH_CASE_LABEL_RE.findall(line)
                succs = []
                if default_target:
                    succs.append(default_target)
                succs.extend(case_targets)
                successors[current_label] = succs
            else:
                # Multi-line switch: start accumulating
                in_switch = True
                switch_start_label = current_label
                switch_buffer = [raw_line]
            continue

        # Unconditional branch
        m = BR_UNCOND_RE.search(line)
        if m:
            target = m.group(1)
            successors[current_label] = [target]
            continue

        # Conditional branch
        m = BR_COND_RE.search(line)
        if m:
            t, f = m.group(1), m.group(2)
            successors[current_label] = [t, f]
            continue

        # Indirectbr (best-effort, single-line assumption for the bracket part)
        if INDIRECTBR_RE.search(line):
            # Try to find all label %... in the rest of the line and possibly following lines
            # For simplicity, we assume the bracket content is on the same line.
            targets = INDIRECTBR_TARGET_RE.findall(line)
            if targets:
                successors[current_label] = targets
            continue

        # ret, unreachable, resume, etc.: no successors (leave list empty)

    return blocks_order, successors


def escape_dot_label(label: str) -> str:
    """Escape a string for use as a DOT label."""
    return label.replace('"', '\\"')


def llvm_ir_to_dot(
    ir: str,
    *,
    function_name: Optional[str] = None,
    label_mode: str = "name",
) -> str:
    """
    Convert LLVM IR (text) to a DOT representation of the CFG.

    Parameters
    ----------
    ir : str
        Full LLVM IR text (may contain multiple functions).
    function_name : str | None
        If given, only this function's CFG is emitted.
        If None, all functions are emitted (each as a separate subgraph).
    label_mode : {"name", "id"}
        How to label nodes in DOT:
        - "name": use the basic-block label (e.g. bb.entry, bb(1))
        - "id": use an internal numeric id (0,1,2,...)

    Returns
    -------
    str
        DOT source string.
    """
    funcs = parse_functions(ir)

    if function_name is not None:
        if function_name not in funcs:
            raise ValueError(f"Function {function_name!r} not found in IR.")
        funcs_to_process = {function_name: funcs[function_name]}
    else:
        funcs_to_process = funcs

    dot_lines = ["digraph CFG {", "  rankdir=TB;", "  node [shape=box];"]

    for fname, body in funcs_to_process.items():
        blocks_order, succs = extract_cfg_from_body(body)

        if len(funcs_to_process) > 1:
            safe_fname = re.sub(r'[^A-Za-z0-9_]', '_', fname)
            dot_lines.append(f"  subgraph cluster_{safe_fname} {{")
            dot_lines.append(f'    label="{escape_dot_label(fname)}";')

        # Create nodes
        for i, label in enumerate(blocks_order):
            node_id = f'"{fname}__{label}"' if len(funcs_to_process) > 1 else f'"{label}"'
            dot_label = escape_dot_label(label) if label_mode == "name" else str(i)
            dot_lines.append(f'  {node_id} [label="{dot_label}"];')

        # Create edges
        for label, targets in succs.items():
            src = f'"{fname}__{label}"' if len(funcs_to_process) > 1 else f'"{label}"'
            for t in targets:
                dst = f'"{fname}__{t}"' if len(funcs_to_process) > 1 else f'"{t}"'
                dot_lines.append(f"  {src} -> {dst};")

        if len(funcs_to_process) > 1:
            dot_lines.append("  }")

    dot_lines.append("}")
    return "\n".join(dot_lines)

def dot2ascii(dotStr: str, timeout=None) -> str:
    #  --png, --dot, --vcg, --gdl, --txt, --ascii, --boxart, --html, --svg
    cmd = ["graph-easy", f"--from=dot", "--boxart"]
    if timeout is not None:
        cmd.append(f"--timeout={timeout}")
        

    try:
        return subprocess.check_output(
            cmd,
            input=dotStr,
            text=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"graph-easy failed:\n{e.stderr}")
        sys.exit(e.returncode)
    

#def main(argv=None):
#    if argv is None:
#        argv = sys.argv
#    else:
#        sys.argv.extend(argv)
#
#    program_name = os.path.basename(sys.argv[0])
#    program_shortdesc = __import__('__main__').__doc__.split("\n")[1]
#    program_descrition = '''
#
#USAGE
#''' % (program_shortdesc)
#
#    try:
#        # Setup argument parser
#        parser = ArgumentParser(description=program_descrition, formatter_class=RawDescriptionHelpFormatter)
#        args = parser.parse_args()
#    except KeyboardInterrupt:
#        return 0
#    except Exception as e:
#        indent = len(program_name) * " "
#        sys.stderr.write(program_name + ": " + repr(e) + "\n")
#        sys.stderr.write(indent + "  for help use --help")
#        return 2


def test():
    ir_text = r"""
define void @Axi4SSParse2If.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !prof !0 !hwtHls.io !1 !hwthls.prof.dummy !7 {
bb0:
  %bb3.ioFsmStBefore.IoFsmSt = alloca i3, align 1
  br label %bb9.sink.split, !llvm.loop !8

bb9.sink.split:                                   ; preds = %bb0, %bb21.sink.split
  %.sink.sink = phi i3 [ %.sink, %bb21.sink.split ], [ 0, %bb0 ]
  %i_read3.r1.data.reg2mem.3.ph = phi i8 [ undef, %bb0 ], [ %i_read3.r1.data.reg2mem.4.ph, %bb21.sink.split ]
  %i_read7.r2.data.reg2mem.0.ph = phi i8 [ undef, %bb0 ], [ %i_read7.r2.data.reg2mem.1.ph, %bb21.sink.split ]
  %.reg2mem.2.ph = phi i1 [ undef, %bb0 ], [ %.reg2mem.3.ph, %bb21.sink.split ]
  %i_read3.r0.data.reg2mem.2.ph = phi i8 [ undef, %bb0 ], [ %i_read3.r0.data.reg2mem.3.ph, %bb21.sink.split ]
  %i_read_data.reg2mem.0.ph = phi i16 [ undef, %bb0 ], [ %i_read_data.reg2mem.1.ph, %bb21.sink.split ]
  %i_read1.r0.data.reg2mem.1.ph = phi i8 [ undef, %bb0 ], [ %i_read1.r0.data.reg2mem.2.ph, %bb21.sink.split ]
  store i3 %.sink.sink, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %0 = load volatile i10, ptr addrspace(1) %i, align 2
  %i_read1.r0.enable = call i1 @hwtHls.bitRangeGet.i10.i5.i1.8(i10 %0, i5 8) #2
  %i_read1.r0.data = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %0, i5 0) #2
  %i_read_data = call i16 @hwtHls.bitConcat.i8.i8(i8 %i_read1.r0.data.reg2mem.1.ph, i8 %i_read1.r0.data) #2
  %1 = icmp eq i16 %i_read_data.reg2mem.0.ph, 4
  %2 = call i16 @hwtHls.bitConcat.i8.i8(i8 %i_read7.r2.data.reg2mem.0.ph, i8 %i_read1.r0.data) #2
  %spec.select = zext i1 %i_read1.r0.enable to i3
  switch i3 %.sink.sink, label %bb22 [
    i3 0, label %bb3
    i3 1, label %bb21.sink.split
    i3 2, label %bb17
    i3 3, label %bb14
    i3 -4, label %bb20
    i3 -3, label %bb18
  ]

bb3:                                              ; preds = %bb9.sink.split
  br label %bb21.sink.split

bb14:                                             ; preds = %bb9.sink.split
  br i1 %.reg2mem.2.ph, label %bb21.sink.split, label %bb18

bb17:                                             ; preds = %bb9.sink.split
  switch i16 %i_read_data.reg2mem.0.ph, label %bb5 [
    i16 4, label %bb21.sink.split
    i16 2, label %bb21.sink.split
  ]

bb18:                                             ; preds = %bb9.sink.split, %bb14
  %i_read3.r1.data.reg2mem.1 = phi i8 [ %i_read3.r1.data.reg2mem.3.ph, %bb9.sink.split ], [ %i_read1.r0.data, %bb14 ]
  %i_read_data8.sink13 = phi i16 [ %2, %bb9.sink.split ], [ 0, %bb14 ]
  %3 = call i32 @hwtHls.bitConcat.i8.i8.i16(i8 %i_read3.r0.data.reg2mem.2.ph, i8 %i_read3.r1.data.reg2mem.1, i16 %i_read_data8.sink13) #2
  store volatile i32 %3, ptr addrspace(2) %o, align 4
  br label %bb5

bb5:                                              ; preds = %bb17, %bb18
  %i_read3.r1.data.reg2mem.0 = phi i8 [ %i_read3.r1.data.reg2mem.3.ph, %bb17 ], [ %i_read3.r1.data.reg2mem.1, %bb18 ]
  %.reg2mem.0 = phi i1 [ %1, %bb17 ], [ %.reg2mem.2.ph, %bb18 ]
  %i_read3.r0.data.reg2mem.0 = phi i8 [ %i_read1.r0.data, %bb17 ], [ %i_read3.r0.data.reg2mem.2.ph, %bb18 ]
  br label %bb21.sink.split

bb20:                                             ; preds = %bb9.sink.split
  br label %bb21.sink.split

bb21.sink.split:                                  ; preds = %bb3, %bb5, %bb14, %bb9.sink.split, %bb17, %bb17, %bb20
  %.sink = phi i3 [ -4, %bb14 ], [ 2, %bb9.sink.split ], [ 3, %bb17 ], [ 3, %bb17 ], [ -3, %bb20 ], [ 0, %bb5 ], [ %spec.select, %bb3 ]
  %i_read3.r1.data.reg2mem.4.ph = phi i8 [ %i_read1.r0.data, %bb14 ], [ %i_read3.r1.data.reg2mem.3.ph, %bb9.sink.split ], [ %i_read3.r1.data.reg2mem.3.ph, %bb17 ], [ %i_read3.r1.data.reg2mem.3.ph, %bb17 ], [ %i_read3.r1.data.reg2mem.3.ph, %bb20 ], [ %i_read3.r1.data.reg2mem.0, %bb5 ], [ %i_read3.r1.data.reg2mem.3.ph, %bb3 ]
  %i_read7.r2.data.reg2mem.1.ph = phi i8 [ %i_read7.r2.data.reg2mem.0.ph, %bb14 ], [ %i_read7.r2.data.reg2mem.0.ph, %bb9.sink.split ], [ %i_read7.r2.data.reg2mem.0.ph, %bb17 ], [ %i_read7.r2.data.reg2mem.0.ph, %bb17 ], [ %i_read1.r0.data, %bb20 ], [ %i_read7.r2.data.reg2mem.0.ph, %bb5 ], [ %i_read7.r2.data.reg2mem.0.ph, %bb3 ]
  %.reg2mem.3.ph = phi i1 [ %.reg2mem.2.ph, %bb14 ], [ %.reg2mem.2.ph, %bb9.sink.split ], [ %1, %bb17 ], [ %1, %bb17 ], [ %.reg2mem.2.ph, %bb20 ], [ %.reg2mem.0, %bb5 ], [ %.reg2mem.2.ph, %bb3 ]
  %i_read3.r0.data.reg2mem.3.ph = phi i8 [ %i_read3.r0.data.reg2mem.2.ph, %bb14 ], [ %i_read3.r0.data.reg2mem.2.ph, %bb9.sink.split ], [ %i_read1.r0.data, %bb17 ], [ %i_read1.r0.data, %bb17 ], [ %i_read3.r0.data.reg2mem.2.ph, %bb20 ], [ %i_read3.r0.data.reg2mem.0, %bb5 ], [ %i_read3.r0.data.reg2mem.2.ph, %bb3 ]
  %i_read_data.reg2mem.1.ph = phi i16 [ %i_read_data.reg2mem.0.ph, %bb14 ], [ %i_read_data, %bb9.sink.split ], [ %i_read_data.reg2mem.0.ph, %bb17 ], [ %i_read_data.reg2mem.0.ph, %bb17 ], [ %i_read_data.reg2mem.0.ph, %bb20 ], [ %i_read_data.reg2mem.0.ph, %bb5 ], [ %i_read_data.reg2mem.0.ph, %bb3 ]
  %i_read1.r0.data.reg2mem.2.ph = phi i8 [ %i_read1.r0.data.reg2mem.1.ph, %bb14 ], [ %i_read1.r0.data.reg2mem.1.ph, %bb9.sink.split ], [ %i_read1.r0.data.reg2mem.1.ph, %bb17 ], [ %i_read1.r0.data.reg2mem.1.ph, %bb17 ], [ %i_read1.r0.data.reg2mem.1.ph, %bb20 ], [ %i_read1.r0.data.reg2mem.1.ph, %bb5 ], [ %i_read1.r0.data, %bb3 ]
  br label %bb9.sink.split, !llvm.loop !12

bb22:                                             ; preds = %bb9.sink.split
  unreachable
}
    """
    
    dot = llvm_ir_to_dot(ir_text)
    print(dot)
    print(dot2ascii(dot))


if __name__ == "__main__":
    test()
    # sys.exit(main())
