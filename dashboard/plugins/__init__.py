# This finds all .py files in the plugin directory and adds them to _all_ so they get imported.
import os
import glob

modules = glob.glob(os.path.dirname(__file__) + "/*.py")
__all__ = [ os.path.basename(f)[:-3] for f in modules if not os.path.basename(f).startswith('_')]
