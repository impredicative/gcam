import os, tempfile

# All parameters defined in this module should be named in full uppercase. This
# hack allows the logging module to identify them.

# Values of the parameters defined here may be updated based on command line
# arguments to the program.

_PROGRAM_NAME = 'GPFS Current Activity Monitor'

_PROGRAM_NAME_SHORT = 'gcam'
# = (''.join([c[0] for c in _PROGRAM_NAME.split()])).lower()

DEBUG_MMPMON_RUNS = 3
# Min should be 2 because calculated deltas are 1 less. To run continuously,
# use 0.

DEBUG_MODE = False

DEBUG_NODES = ['penguin1', 'gadolinium']

DISPLAY_PAUSE_KEY = ' '
# Can be any single key. The same key is also used to resume the display.

GPFS_NODESET = None
# Can be a str. If None, first nodeset listed by mmlsnode is used.

LOG_FILE_PATH = os.path.join(tempfile.gettempdir(),
                             '{}{}{}'.format(_PROGRAM_NAME_SHORT, os.extsep,
                                             'log'))

LOG_FILE_WRITE = False
# If True, log is written to file.

LOG_LEVEL = 'info'
# Can be 'info' or 'debug'

LOG_NUM_MMPMON_LINES = 1000
# Number of initial mmpmon output lines to log, contingent upon other logging
# parameters.

MMPMON_HOST = 'localhost'
# Hostname of host on which to run mmpmon. Can also be localhost.

MONITORING_INTERVAL_SECS = 3
# Can't be less than 1. Can be an int or a float.

PRINT_LAST_RECORD = True
# If True, the last displayed record is printed to stdout.

SSH_ARGS = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=4']

TABLE_TYPE = 'separated'
# Can be 'separated' or 'interlaced'