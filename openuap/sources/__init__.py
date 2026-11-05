"""Source loaders. Each module exposes `SOURCES` (metadata) and `load(raw_dir)` yielding record dicts."""
from . import geldreich, nuforc, geipan, urecat, uap_monitor

LOADERS = [geldreich, nuforc, geipan, urecat, uap_monitor]
