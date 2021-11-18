from pathlib import Path
import sys


def call_glob():
    if len(sys.argv) != 3:
        print("[Error] Usage `glob.py path 'module'|pattern`, but provided `%r`" % sys.argv, file=sys.stderr)
        sys.exit(1)

    root, mode = sys.argv[1:]
    if mode == 'module':
        # list all modules (the directories wich do contain .py files)
        seen_module_directories = set()
        for path in Path(root).rglob("*.py"):
            path: Path
            d = path.parent.as_posix()
            if d in seen_module_directories:
                continue
            else:
                print(d)
                seen_module_directories.add(d)

    else:
        # list files by extension in a folder
        for path in Path(root).glob(mode):
            print(path.as_posix())


if __name__ == "__main__":
    call_glob()
