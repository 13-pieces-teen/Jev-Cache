import multiprocessing

from jev_cache.native_host import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
