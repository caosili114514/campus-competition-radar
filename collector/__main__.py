"""支持 python -m collector。"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())