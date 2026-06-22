import sys
from fetcher.fetch import main
main(force="--force" in sys.argv)
