import multiprocessing

from jev_cache.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
