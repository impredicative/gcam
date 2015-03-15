#!/usr/bin/env python3.2

# GPFS Current Activity Monitor
# Run with -h to print help and allowable arguments.
# See params.py for more customizations.

# The code for this project is generally limited to 79 characters per line.

import argparse, collections, curses, datetime, functools, inspect
import itertools, locale, logging, signal, subprocess, sys, threading, time

# Local imports
import common, errors, params
from prettytable import PrettyTable
from numsort import numsorted  # Uses "@functools.lru_cache(maxsize=None)"

class ArgParser(argparse.ArgumentParser):
    """Parse and store input arguments. Arguments on the command line override
    those in the parameters file."""

    def __init__(self):

        epilog = "Pressing the '{}' key pauses or resumes the display.".format(
                 params.DISPLAY_PAUSE_KEY)

        super().__init__(description=params._PROGRAM_NAME, epilog=epilog,
                         prog=params._PROGRAM_NAME_SHORT)

        self._add_misc_args()
        self._add_logging_args()

        self._args = self.parse_args()

        self._store_misc_args()
        self._store_logging_args()

    def _add_misc_args(self):
        """Add miscellaneous arguments to parser."""

        self.add_argument('-hn', default=params.MMPMON_HOST,
                          help='GPFS node name on which to run mmpmon '
                               '(requires automated SSH login if not '
                               'localhost) (currently: %(default)s)')

        self.add_argument('-n', type=float,
                          default=params.MONITORING_INTERVAL_SECS,
                          help='Refresh interval in seconds (%(type)s >=1) '
                               '(currently: %(default)s)')

        nodeset = params.GPFS_NODESET or '(first available)'
        self.add_argument('-ns', default=params.GPFS_NODESET,
                          help='GPFS nodeset (currently: {})'.format(nodeset))

        self.add_argument('-t', default=params.TABLE_TYPE, choices=('s', 'i'),
                          help="Table type ('s'eparated or 'i'nterlaced) "
                               '(currently: %(default)s)')

    def _add_logging_args(self):
        """Add logging arguments to parser."""

        arg_group = self.add_argument_group(title='Diagnostic logging arguments')

        logging_status = 'enabled' if params.LOG_FILE_WRITE else 'disabled'
        arg_group.add_argument('-l', action='store_true',
                               default=params.LOG_FILE_WRITE,
                               help='Enable logging to file '
                                    '(currently: {})'.format(logging_status))

        arg_group.add_argument('-lf', default=params.LOG_FILE_PATH,
                               help='Log file path (if logging is enabled) '
                                    "(currently: '%(default)s')")
        # type=argparse.FileType('w') is not specified because its value is
        # automatically touched as a file. This is undesirable if -l is not
        # specified, etc.

        arg_group.add_argument('-ll', default=params.LOG_LEVEL,
                               choices=('i', 'd'),
                               help='Log level (if logging is enabled) '
                                    "('i'nfo or 'd'ebug) "
                                    '(currently: %(default)s)')

    def _store_misc_args(self):
        """Store parsed miscellaneous arguments."""

        params.MMPMON_HOST = self._args.hn
        params.MONITORING_INTERVAL_SECS = max(self._args.n, 1)
        params.GPFS_NODESET = self._args.ns

        if self._args.t == 's': params.TABLE_TYPE = 'separated'
        elif self._args.t == 'i': params.TABLE_TYPE = 'interlaced'

    def _store_logging_args(self):
        """Store parsed logging arguments."""

        params.LOG_FILE_WRITE = self._args.l
        params.LOG_FILE_PATH = self._args.lf

        if self._args.ll == 'i': params.LOG_LEVEL = 'info'
        elif self._args.ll == 'd': params.LOG_LEVEL = 'debug'


class DiagnosticLoggerSetup:
    """Set up a logger to which diagnostic messages can be logged."""

    def __init__(self):

        self.logger = logging.getLogger(params._PROGRAM_NAME_SHORT)
        self._configure()

        if params.LOG_FILE_WRITE:
            self._log_basics()
            self._log_params()

    def _configure(self):
        """Configure the logger with a level and a formatted handler."""

        if params.LOG_FILE_WRITE:

            # Set level
            level = getattr(logging, params.LOG_LEVEL.upper())
            self.logger.setLevel(level)

            # Create formatter
            attributes = ('asctime', 'levelname', 'module', 'lineno',
                          'threadName', 'message')
            attributes = ['%({})s'.format(a) for a in attributes]
            attributes.insert(0, '')
            format_ = '::'.join(attributes)
            formatter = logging.Formatter(format_)

            # Add handler
            handler = logging.FileHandler(params.LOG_FILE_PATH, mode='w')
            handler.setFormatter(formatter)

        else:
            handler = logging.NullHandler

        self.logger.addHandler(handler)

    def _log_basics(self):
        """Retrieve and log basics about the operating system, environment,
        platform, program input arguments, and the Python installation in
        use."""

        import os, platform, sys #@UnusedImport @Reimport

        items = ('os.name',
                 'os.getcwd()',
                 'os.ctermid()',
                 'os.getlogin()',
                 "os.getenv('USER')",
                 "os.getenv('DISPLAY')",
                 "os.getenv('LANG')",
                 "os.getenv('TERM')",
                 "os.getenv('SHELL')",
                 "os.getenv('HOSTNAME')",
                 "os.getenv('PWD')",
                 'os.uname()',

                 'platform.architecture()',
                 'platform.machine()',
                 'platform.node()',
                 'platform.platform()',
                 'platform.processor()',
                 'platform.python_build()',
                 'platform.python_compiler()',
                 'platform.python_implementation()',
                 'platform.python_revision()',
                 'platform.python_version_tuple()',
                 'platform.release()',
                 'platform.system()',
                 'platform.version()',
                 'platform.uname()',
                 'platform.dist()',

                 'sys.argv',
                 'sys.executable',
                 'sys.flags',
                 'sys.path',
                 'sys.platform',
                 'sys.version',
                 'sys.version_info',
                )

        # Run above-mentioned code and log the respective outputs
        for source in items:
            value = str(eval(source)).replace('\n', ' ')
            message = '{}::{}'.format(source, value)
            self.logger.info(message)

    def _log_params(self):
        """Log the names and values of all parameters."""

        for item in dir(params):
            if (not item.startswith('__')) and (item == item.upper()):
                value = str(getattr(params, item)).replace('\n', ' ')
                message = 'params.{}::{}'.format(item, value)
                self.logger.info(message)


class Logger:
    """
    Provide a base class to provision logging functionality.

    Instances of derived classes can log messages using methods self.logger and
    self.logvar.
    """

    logger = logging.getLogger(params._PROGRAM_NAME_SHORT)

    def logvar(self, var_str, level='info'):
        """Log the provided variable's access string and value, and also its
        class and method names at the optionally indicated log level.

        The variable can be a local variable. Alternatively, if accessed using
        the 'self.' prefix, it can be a class instance variable or otherwise a
        class variable.
        """

        # Inspect the stack
        stack = inspect.stack()
        try:

            # Obtain class and method names
            class_name = stack[1][0].f_locals['self'].__class__.__name__
            method_name = stack[1][3]

            # Obtain variable value
            if not var_str.startswith('self.'):
                # Assuming local variable
                var_val = stack[1][0].f_locals[var_str]
            else:
                var_name = var_str[5:] # len('self.') = 5
                try:
                    # Assuming class instance variable
                    var_val = stack[1][0].f_locals['self'].__dict__[var_name]
                except KeyError:
                    # Assuming class variable
                    var_val = (stack[1][0].f_locals['self'].__class__.__dict__
                               [var_name])

        finally:
            del stack  # Recommended.
            # See http://docs.python.org/py3k/library/inspect.html#the-interpreter-stack

        # Format and log the message
        message = '{}.{}::{}::{}'.format(class_name, method_name, var_str,
                                         var_val)
        level = getattr(logging, level.upper())
        self.logger.log(level, message)


class Receiver(Logger):
    """Return an iterable containing mmpmon fs_io_s recordset containing
    records for all responding nodes and file systems."""

    def __iter__(self):
        return self._fsios_record_group_objectifier()

    def close(self):
        """
        Close the subprocess providing data to the iterator.

        This must be used if an unhandled exception occurs.
        """
        try: self._mmpmon_subprocess.terminate()
        except AttributeError: pass

    @staticmethod
    def _process_cmd_args(cmd_args):
        """Return command line arguments conditionally modified to run on
        remote host."""

        if params.MMPMON_HOST not in ('localhost', 'localhost.localdomain',
                                      '127.0.0.1'):
            cmd_args = params.SSH_ARGS + [params.MMPMON_HOST] + cmd_args
        return cmd_args

    @property
    def node_seq(self):
        """Return a sequence of strings with names of all GPFS nodes in the
        specified nodeset."""

        try:
            return self._node_seq
        except AttributeError:

            cmd_args = [r'/usr/lpp/mmfs/bin/mmlsnode']
            cmd_args = self._process_cmd_args(cmd_args)
            self.logvar('cmd_args')

            try:
                output = subprocess.check_output(cmd_args)
            except (OSError, subprocess.CalledProcessError) as exception:
                # OSError example:
                #     [Errno 2] No such file or directory:
                #     '/usr/lpp/mmfs/bin/mmlsnode'
                # subprocess.CalledProcessError example:
                #     Command '['ssh', '-o', 'BatchMode=yes', '-o',
                #     'ConnectTimeout=4', 'invalidhost',
                #     '/usr/lpp/mmfs/bin/mmlsnode']' returned non-zero exit
                #     status 255
                raise errors.SubprocessError(str(exception))
            output = output.split(b'\n')[2:-1]

            # Extract node names for relevant nodeset only
            for line in output:
                line = line.decode()
                node_set, node_seq = line.split(None, 1)

                if ((not params.GPFS_NODESET) or
                    (node_set == params.GPFS_NODESET)):

                    node_seq = node_seq.split()
                    node_seq.sort() # possibly useful if viewing logs

                    self._node_seq = node_seq
                    return self._node_seq
            else:
                if params.GPFS_NODESET:
                    err = '{} is not a valid nodeset per mmlsnode'.format(
                          params.GPFS_NODESET)
                else:
                    err = 'no nodeset could be found using mmlsnode'
                raise errors.ArgumentError(err)

    @property
    def num_node(self):
        """Return the number of GPFS nodes in the specified nodeset."""

        try:
            return self._num_node
        except AttributeError:
            if not params.DEBUG_MODE:
                self._num_node = len(self.node_seq)
            else:
                self._num_node = len(params.DEBUG_NODES)
            return self._num_node

    def _mmpmon_caller(self):
        """Run and prepare the mmpmon subprocess to output data."""

        # Determine input arguments
        delay = str(int(params.MONITORING_INTERVAL_SECS * 1000))
            # int above removes decimals
        runs = '0' if not params.DEBUG_MODE else str(params.DEBUG_MMPMON_RUNS)

        # Determine mmpmon command
        cmd_args = [r'/usr/lpp/mmfs/bin/mmpmon', '-p', '-s', '-r', runs,
                    '-d', delay]
        cmd_args = self._process_cmd_args(cmd_args)
        self.logvar('cmd_args')

        # Determine input commands to mmpmon process

        node_seq = params.DEBUG_NODES if params.DEBUG_MODE else self.node_seq
        for node in node_seq: self.logvar('node') #@UnusedVariable

        mmpmon_inputs = ('nlist add {}'.format(node) for node in node_seq)
            # While multiple nodes can be added using the same nlist command,
            # this apparently restricts the number of nodes added to 98 per
            # nlist command. Due to this restriction, only one node is added
            # per command instead.
        mmpmon_inputs = itertools.chain(mmpmon_inputs, ('fs_io_s',))

        # Call subprocess, and provide it with relevant commands
        self._mmpmon_subprocess = subprocess.Popen(cmd_args,
                                                   bufsize=-1,
                                                   stdin=subprocess.PIPE,
                                                   stdout=subprocess.PIPE,
                                                   stderr=subprocess.STDOUT)
        for mmpmon_input in mmpmon_inputs:
            mmpmon_input = mmpmon_input.encode() + b'\n'
            self.logvar('mmpmon_input', 'debug')
            self._mmpmon_subprocess.stdin.write(mmpmon_input)
        self._mmpmon_subprocess.stdin.close() # this also does flush()

    def _mmpmon_stdout_processor(self):
        """Yield lines of text returned by mmpmon."""

        self._mmpmon_caller()

        # Handle possible known error message
        line = next(self._mmpmon_subprocess.stdout);
        line = self._mmpmon_line_processor(line)
        if line == 'Could not establish connection to file system daemon.':
            err_msg = ('Only a limited number of mmpmon processes can be run '
                       'simultaneously on a host. Kill running instances of '
                       'this application that are no longer needed. Also kill '
                       'unnecessary existing mmpmon processes on MMPMON_HOST, '
                       'i.e. {}.').format(params.MMPMON_HOST)
            # A max of 5 mmpmon processes were observed to run simultaneously
            # on a host.
            raise errors.SubprocessError(err_msg)

        # Yield mmpmon output
        yield line # (obtained earlier)
        for line in self._mmpmon_subprocess.stdout:
            yield self._mmpmon_line_processor(line)

    def _mmpmon_line_processor(self, line):
        """Return a formatted version of a line returned by mmpmon, so it can
        be used for further processing."""

        line = line.decode().rstrip()

        if params.LOG_FILE_WRITE and \
           (self.logger.getEffectiveLevel() <= logging.DEBUG) and \
           params.LOG_NUM_MMPMON_LINES:
            # Note: It is uncertain whether grouping the above conditions into 
            #       a single tuple will result in short-circuit evaluation.

            params.LOG_NUM_MMPMON_LINES -= 1
            self.logvar('line', 'debug') # CPU and disk intensive

#        else:
#            # Simplify method definition to avoid the now unnecessary check
#            self._mmpmon_line_processor = lambda line: line.decode().rstrip()

        return line

    def _record_processor(self):
        """Yield dicts corresponding to lines returned by mmpmon."""

        for record in self._mmpmon_stdout_processor():
            record = record.split()

            type_ = record[0][1:-1]
            properties = {k[1:-1]: v for k, v in common.grouper(2, record[1:])}

            record = {'type':type_, 'properties':properties}
            yield record

    def _fsios_record_filter(self):
        """Yield only fs_io_s records along with their group number."""

        # Yield records with their group number
        counter = itertools.count(start=1)
        for r in self._record_processor():
            if (r['type'] == 'fs_io_s' and r['properties']['rc'] == '0'):
                r['properties']['gn'] = count #@UndefinedVariable
                yield r['properties']
            elif (r['type'] == 'nlist' and 'c' in r['properties']):
                count = next(counter) #@UnusedVariable

    def _fsios_record_objectifier(self):
        """Yield fs_io_s record dicts as Record objects."""

        return (Record(record) for record in self._fsios_record_filter())

    def _fsios_record_grouper(self):
        """Yield fs_io_s records grouped into a sequence based on their
        creation time.
        """

        # Group records that were created approximately simultaneously, i.e.
        # with the same group number
        record_group_iterator = itertools.groupby(
                                    self._fsios_record_objectifier(),
                                    lambda r: r.gn)

        # Sort records in each group, and yield groups
        for _, record_group in record_group_iterator: # _ = record_group_num

            record_group = list(record_group)
                # converting from iterator to list, to allow list to be sorted
                # later.
            for i in range(len(record_group)): del record_group[i].gn
            record_group.sort(key = lambda r: (r.nn, r.fs))
                # sorting to allow further grouping by nn
            # "lambda r: operator.itemgetter('nn', 'fs')(r)"
            # may work alternatively

            yield record_group

    def _fsios_record_group_objectifier(self):
        """Yield fs_io_s record group sequences as RecordGroup objects."""

        return (RecordGroup(record_group) for record_group in
                self._fsios_record_grouper())

class Record:
    """Return a record object with attributes
    fs, gn, nn, ts, fs, br, bw, brw.
    """

    _filter_in_keys = {'gn', 'nn', 't', 'tu', 'fs', 'br', 'bw'}
    _non_int_keys = {'gn', 'nn', 'fs'}

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __str__(self):
        return str(self.__dict__)

    def __init__(self, fsios_dict):

        fsios_dict = self._process(fsios_dict)
        self.__dict__.update(fsios_dict)

    def _process(self, dict_):
        """Return the processed record dict."""

        # Filter out keys that are not needed
        dict_ = {key : dict_[key] for key in self._filter_in_keys}

        # Convert integer values from str to int
        for key in dict_:
            if key not in self._non_int_keys:
                dict_[key] = int(dict_[key])

        # Combine seconds and microseconds
        dict_['ts'] = dict_['t'] + dict_['tu']/1000000 # ts = timestamp
        for key in ['t', 'tu']: del dict_[key]

        # Calculate sum of bytes read and bytes written
        dict_['brw'] = dict_['br'] + dict_['bw']

        return dict_

    def __sub__(self, older): # self is newer
        return RecordDelta(self, older)


class RecordDelta(Record):
    """Return a record delta object computed from two successive records.
    Included attributes are fs, nn, ts, td, br, bw, brw, brps, bwps, brwps.
    """

    # Inheriting from Record allows its functions __getitem__, __setitem__ and
    # __str__ to be used.

    def __init__(self, new, old):

        assert new.fs == old.fs and new.nn == old.nn

        # Set identifying attribute values
        for attr in ('fs', 'nn', 'ts'):
            self[attr] = new[attr]

        self._compute_deltas_and_speeds(new, old)

    def _compute_deltas_and_speeds(self, new, old):
        """Compute transfer deltas and speeds."""

        self.td = new.ts - old.ts # td = time delta

        for attr in ('br', 'bw', 'brw'):

            self[attr] = (new[attr] - old[attr]) % 18446744073709551615
                # 18446744073709551615 == (2**64 - 1)
            self[attr + 'ps'] = self[attr] / self.td
                # (speed is in bytes per second)

            #delattr(self, attr)
            # If the above delattr line is uncommented, then
            # RecordGroupDelta._lev2_summary_stat_types should not contain
            # br, bw, brw.


class RecordGroup:
    """Return a record group object from a sequence of Record objects. Stats
    are available as attributes recs, lev1_summary_stats, and
    lev2_summary_stats. Timestamp is available as attribute timestamp.
    """

    _count = 0
    _lev1_summary_stat_types = ('nn', 'fs') # (totals)
    _lev2_summary_stat_types = ('br', 'bw', 'brw') # (grand totals)

    def count(self):
        """Increment class instance count."""

        self.__class__._count += 1
        self._count = self.__class__._count # (makes copy as is desired)

    def __init__(self, recs):

        self.count()

        self.recs = recs
        self.timestamp = max((datetime.datetime.fromtimestamp(rec.ts) for
                              rec in self.recs))
        #self.compute_summary_stats()
            # not necessary, except for debugging these values

    def rec_select(self, nn, fs):
        """Return the record for the given node name and file system. None is
        returned if the record is not found. Note that iterating over records
        using this approach approximately has a complexity of O(n**2).
        """

        for rec in self.recs:
            if nn == rec.nn and fs == rec.fs:
                return rec

    def compute_summary_stats(self):
        """Compute summary stats for records, and store them in
        self.lev1_summary_stats and self.lev2_summary_stats."""

        self.lev1_summary_stats = {}
        self.lev2_summary_stats = {}

        # Compute level 1 summary stats
        for lev1_stattype in self._lev1_summary_stat_types:
            seq = [rec[lev1_stattype] for rec in self.recs]
            self._compute_lev1_summary_stats(lev1_stattype, seq)

        # Compute level 2 summary stats
        for lev2_stattype in self._lev2_summary_stat_types:
            self.lev2_summary_stats[lev2_stattype] = sum(rec[lev2_stattype] for
                                                         rec in self.recs)

    def _compute_lev1_summary_stats(self, lev1_stattype, seq):
        """Compute level 1 summary stats, grouped by items in
        self._lev1_summary_stat_types.
        """

        self.lev1_summary_stats[lev1_stattype] = {}
        for i in seq:

            curr_summary_stats = {j:0 for j in self._lev2_summary_stat_types}

            for rec in self.recs: # can possibly use itertools for efficiency

                if i == rec[lev1_stattype]:
                    for stat in curr_summary_stats.keys():
                        curr_summary_stats[stat] += rec[stat]

            self.lev1_summary_stats[lev1_stattype][i] = curr_summary_stats

    @staticmethod
    def _sso(seq, tabs=0):
        """Return an informal String representation for the given Sequence of
        Objects.
        """

        tabs = '\t' * tabs
        if isinstance(seq, dict): seq = sorted(seq.items())
        strs = ('\n{}{}'.format(tabs, obj) for obj in seq)
        str_ = ''.join(strs)
        return str_

    def __str__(self):

        str_ = '{} (#{}) (as of {}):\n'.format(self.__class__.__name__,
                                               self._count, self.timestamp)

        # Try storing string for summary stats
        sss = lambda k: '\t\tSummarized by {}:{}'.format(k,
                        self._sso(self.lev1_summary_stats[k], 3))
        try:
            lev1_summary_stats = (sss(k) for k in self.lev1_summary_stats)
            lev1_summary_stats_str = '\n'.join(lev1_summary_stats)
            str_ += '\tSummarized record stats:\n{}{}\n'.format(
                    lev1_summary_stats_str,
                    self._sso((self.lev2_summary_stats,), 2))
        except AttributeError:
            pass

        # Store string for individual stats
        str_ += '\tIndividual record stats:{}'.format(self._sso(self.recs, 2))

        return str_

    def __sub__(self, older): # self is newer
        return RecordGroupDelta(self, older)


class RecordGroupDelta(RecordGroup):
    """Return a record delta object computed from two successive record groups.
    Stats are available as attributes recs, lev1_summary_stats, and
    lev2_summary_stats. Timestamp is available as attribute timestamp. Time
    duration in seconds of the delta is available as attribute
    time_duration_secs.
    """

    _count = 0
    _lev2_summary_stat_types = ('br', 'bw', 'brw', 'brps', 'bwps', 'brwps')
        # (grand totals)
    _table_types = collections.OrderedDict((
                   #('brwps', {'label': 'Read+Write', 'label_short': 'R+W'}),
                       # brwps is disabled as it takes up valuable screen space
                   ('brps', {'label': 'Read', 'label_short': 'R'}),
                   ('bwps', {'label': 'Write', 'label_short': 'W'}),
                   ))

    # Inheriting from RecordGroup allows its functions compute_summary_stats
    # __str__, etc. to be used.

    def __init__(self, new, old):

        self.count()

        self.timestamp = new.timestamp

        self.time_duration_secs = new.timestamp - old.timestamp
        self.time_duration_secs = self.time_duration_secs.total_seconds()

        self._compute_recs_deltas(new, old)
        self.compute_summary_stats()

    def _compute_recs_deltas(self, new, old):
        """Compute deltas (differences) of new and old records, and store them
        in self.recs.
        """

        self.recs = [] # seq of RecordDelta objects, once populated

        # Compute deltas
        # (very inefficient, but unoptimizable as long as recs is a seq, and
        #  not say an efficiently accessible multi-level dict instead)
        for rec_new in new.recs:
            for rec_old in old.recs:
                if rec_new.fs == rec_old.fs and rec_new.nn == rec_old.nn:
                    rec = rec_new - rec_old
                    self.recs.append(rec)
                    break

    @staticmethod
    def _bytes_str(num_bytes):
        """Return a human readable string representation of the provided number
        of bytes. Bytes can be an int or a float or None. Powers of 2 are used.
        As such, the units used are binary, and not SI. To save a character,
        numbers from 1000 to 1023 are transformed to the next largest unit.

        Examples: 256 --> ' 256.0 ', 1012 --> '1.0K ', 1450 --> '   1.4K',
        99**99 --> '3.7e+197', None --> '  N/A '
        """

        # To disable thousands-character-saving, increase width by 1, and
        # comment out str len test section.

        # Note that table field headers are hard-coded to have at least the
        # same output length as the general output of this function.

        width = 5 # output length is this + 1 for unit

        if num_bytes != None:

            units = (' ', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y')
            num_bytes_original = num_bytes

            for unit_index, unit in enumerate(units):
                if num_bytes < 1024:
                    if len('{:.1f}'.format(num_bytes)) > width:
                    # The above condition holds True when num_bytes is
                    # approximately > 999.94. If num_bytes is always an int, it
                    # could more simply be ">= 1000".
                        try:
                            num_bytes /= 1024
                                # is always actually less than 1.0, but
                                # formats as 1.0 with {:.1f}
                        except OverflowError:
                            break # num_bytes must be too large
                        try: unit = units[unit_index + 1]
                        except IndexError: # units are exhausted
                            break
                    str_ = '{:{}.1f}{}'.format(num_bytes, width, unit)
                        # this is always 6 characters
                    return str_
                try: num_bytes /= 1024
                except OverflowError: break

            try:
                # Fall back to scientific notation.
                str_ = '{:{}.1e}'.format(num_bytes_original, width)
                return str_
            except OverflowError:
                # Fall back to basic string representation.
                str_ = str(num_bytes_original)
                return str_
            # String length can be greater than normal for very large numbers.

        else:
            # num_bytes == None
            return '{:^{}}'.format('N/A', width + 1)

    @staticmethod
    @functools.lru_cache(maxsize=None)
    def _mmfa_ipf(num_avail_shares, demands):
        """Return the sequence of shares corresponding to the provided number
        of available shares and the sequence of demands. Max-min fair
        allocation, implemented by an incremental progressive filling algorithm
        is used. Note that the implemented algorithm is not entirely efficient
        due to its incremental filling nature.

        num_avail_shares should be a non-negative int.

        demands should be a hashable sequence (such as a tuple, and not a list)
        of non-negative ints.

        Results are cached in memory.
        """

        demands, indexes =  list(zip(*sorted(zip(demands, range(len(demands))),
                                             reverse=True)))
                                # This sorts 'demands' and get indexes.
#        indexes, demands = list(zip(*sorted(enumerate(demands),
#                                            key=operator.itemgetter(1),
#                                            reverse=True)))
#                                # alternative technique for above
        # Note that 'reverse' above can be set equal to False for any specific
        # applications that require it.
        demands = list(demands)
        indexes = sorted(range(len(indexes)), key=lambda k: indexes[k])
            # This transform indexes to make them useful later for restoring
            # the original order.

        len_ = len(demands)
        shares = [0] * len_

        i = 0
        while num_avail_shares and any(demands):
            if demands[i]:
                num_avail_shares -= 1
                demands[i] -= 1
                shares[i] += 1
            i = (i + 1) % len_

        shares = tuple(shares[k] for k in indexes)
        return shares

    def tables_str(self, format_, num_avail_lines=80):
        """Return a string representation of the table types previously
        specified in self.__class__._table_types. The representation is of the
        specified format, which can be either separated or interlaced. Inactive
        nodes are not included.
        """

        method_name = '_tables_{}_str'.format(format_)
        return getattr(self, method_name)(num_avail_lines)

    def _tables_separated_str(self, num_avail_lines):
        """Return a separated string representation of the table types
        previously specified in self.__class__._table_types. Inactive nodes are
        not included.
        """

        # Determine file systems used
        fs_seq = numsorted(tuple(self.lev1_summary_stats['fs']))
            # tuple results in a hashable object which is required
        table_fields = (['Node', 'Total'] +
                        ['{:>6}'.format(fs) for fs in fs_seq])
                            # 6 is the general len of a str returned by 
                            # self._bytes_str

        def nn_active_names_and_lens():
            """Return active node name sequences and their lengths for all
            table types. The returned items are dicts.
            """

            nn_seq = {}
                # Keys and values will be table types and respective node
                # names.
            nn_seq_len = {}
                # A key is a tuple containing
                # (table_type, 'displayed' or 'active'). The value is the
                # respective nn_seq len.

            for table_type in self._table_types:
                nn_seq_cur = [nn for nn, nn_summary_stats in
                              self.lev1_summary_stats['nn'].items() if
                              nn_summary_stats[table_type] > 0]
                #nn_seq_cur.sort()
                sort_key = (lambda nn:
                                self.lev1_summary_stats['nn'][nn][table_type])
                nn_seq_cur.sort(key = sort_key, reverse = True)
                nn_seq_len[table_type, 'active'] = len(nn_seq_cur)
                nn_seq[table_type] = nn_seq_cur

            return nn_seq, nn_seq_len

        nn_seq, nn_seq_len = nn_active_names_and_lens()

        def num_avail_lines_per_table(num_avail_lines, nn_seq):
            """Return a sequence containing the number of available lines for
            node name sequences of tables.
            """
            num_avail_lines -= (len(self._table_types) * 7)
                # 7 is the num of lines cumulatively used by headers, totals
                # row, and footers of each table
            num_avail_lines = max(num_avail_lines, 0)
            lines_reqd_seq = (len(nn_seq[table_type]) for table_type in
                              self._table_types)
            lines_reqd_seq = tuple(lines_reqd_seq)
            lines_avail_seq = self._mmfa_ipf(num_avail_lines, lines_reqd_seq)
            return lines_avail_seq

        lines_avail_seq = num_avail_lines_per_table(num_avail_lines, nn_seq)

        def nn_displayed_names_and_lens(nn_seq, nn_seq_len, lines_avail_seq):
            """Return displayed node name sequences and their lengths for all
            table types. The returned items are updated dicts.
            """

            for table_type, lines_avail in zip(self._table_types,
                                               lines_avail_seq):
                nn_seq[table_type] = nn_seq[table_type][:lines_avail]
                nn_seq_len[table_type, 'displayed'] = len(nn_seq[table_type])

            return nn_seq, nn_seq_len

        nn_seq, nn_seq_len = nn_displayed_names_and_lens(nn_seq, nn_seq_len,
                                                         lines_avail_seq)

        def nn_max_len():
            """Return the max length of a node name across all tables."""

            try:
#                nn_max_len = max(len(nn_cur) for nn_seq_cur in nn_seq.values()
#                                 for nn_cur in nn_seq_cur)
#                                # only for active nodes, but varies
                nn_max_len = max(len(nn) for nn in
                                 self.lev1_summary_stats['nn'])
                                # for all responding nodes, and less varying
            except ValueError: # max() arg is an empty sequence
                nn_max_len = 1
                    # not set to 0 because str.format causes "ValueError: '='
                    # alignment not allowed in string format specifier"
                    # otherwise

            return nn_max_len

        nn_max_len = nn_max_len()

        def tables_str_local(table_fields, fs_seq, nn_max_len, nn_seq,
                             nn_seq_len):
            """Return a string representations for the specified table
            types.
            """

            tables = []
            for table_type in self._table_types:

                # Initialize table
                table = PrettyTable(table_fields, padding_width=0)
                table.vertical_char = ' '
                table.junction_char = '-'
                table.set_field_align('Node', 'l')
                for field in table_fields[1:]:
                    table.set_field_align(field, 'r')

                # Add totals row
                total_speeds = [self.lev1_summary_stats['fs'][fs][table_type]
                                for fs in fs_seq]
                total_speeds = [self._bytes_str(i) for i in total_speeds]
                total_speeds_total = self.lev2_summary_stats[table_type]
                total_speeds_total = self._bytes_str(total_speeds_total)
                nn = '{:*^{}}'.format('Total', nn_max_len)
                row = [nn, total_speeds_total] + total_speeds
                table.add_row(row)

                # Add rows for previously determined file systems and node
                # names
                for nn in nn_seq[table_type]:
                    nn_recs = [self.rec_select(nn, fs) for fs in fs_seq]
                        # self.rec_select(nn, fs) can potentially be == None
                    nn_speeds = [(nn_rec[table_type] if nn_rec else None) for
                                 nn_rec in nn_recs]
                    nn_speeds = [self._bytes_str(i) for i in nn_speeds]
                    nn_speeds_total = (
                        self.lev1_summary_stats['nn'][nn][table_type])
                    nn_speeds_total = self._bytes_str(nn_speeds_total)
                    nn = '{:.<{}}'.format(nn, nn_max_len)
                        # e.g. '{:.<{}}'.format('xy',4) = 'xy..'
                    row = [nn, nn_speeds_total] + nn_speeds
                    table.add_row(row)

                # Construct printable tables string
                label_template = ('{} bytes/s for top {} of {} active nodes '
                                  'out of {} responding')
                label = label_template.format(
                            self._table_types[table_type]['label'],
                            nn_seq_len[table_type, 'displayed'],
                            nn_seq_len[table_type, 'active'],
                            len(self.lev1_summary_stats['nn']))
                table = '\n{}:\n{}'.format(label, table)
                tables.append(table)

            tables_str = '\n'.join(tables)
            return tables_str

        tables_str = tables_str_local(table_fields, fs_seq, nn_max_len, nn_seq,
                                      nn_seq_len)
        return tables_str

    def _tables_interlaced_str(self, num_avail_lines):
        """Return an interlaced string representation of the table types
        previously specified in self.__class__._table_types. Inactive nodes are
        not included.
        """

        # Determine file systems used
        fs_seq = numsorted(tuple(self.lev1_summary_stats['fs']))
            # tuple results in a hashable object which is required
        table_fields = (['Node', 'Type', 'Total'] +
                       ['{:>6}'.format(fs) for fs in fs_seq])
                            # 6 is the general len of a str returned by 
                            # self._bytes_str

        def nn_max(num_avail_lines):
            """Return the maximum number of nodes for which data can be
            displayed."""

            num_tables = len(self._table_types)
            nn_max = num_avail_lines - 6 - num_tables
                # 6 is the number of lines used by header and footer rows
                # num_tables is the number of lines used by totals rows
            nn_max = int(nn_max/num_tables)
            num_avail_lines = max(num_avail_lines, 0)
            return nn_max

        nn_max = nn_max(num_avail_lines)

        def nn_names_and_lens(nn_max):
            """Return a sequence of the displayed node names, and a dict of the
            node name sequence lengths.
            """

            nn_seq_len = {}

            nn_seq =  [nn for nn, nn_summary_stats in
                       self.lev1_summary_stats['nn'].items() if
                       nn_summary_stats['brw'] > 0]
            #nn_seq.sort()
            sort_key = lambda nn: self.lev1_summary_stats['nn'][nn]['brw']
            nn_seq.sort(key = sort_key, reverse=True)
            nn_seq_len['active'] = len(nn_seq)

            nn_seq = nn_seq[:nn_max]
            nn_seq_len['displayed'] = len(nn_seq)

            return nn_seq, nn_seq_len

        nn_seq, nn_seq_len = nn_names_and_lens(nn_max)

        def nn_max_len():
            """Return the max length of a node name."""

            try:
#                nn_max_len = max(len(nn_cur) for nn_seq_cur in nn_seq.values()
#                                 for nn_cur in nn_seq_cur)
#                    # this is only for active nodes, but varies
                nn_max_len = max(len(nn) for nn in
                                 self.lev1_summary_stats['nn'])
                    # this is for all responding nodes, and less varying
            except ValueError: # max() arg is an empty sequence
                nn_max_len = 1
                    # not set to 0 because str.format causes "ValueError: '='
                    # alignment not allowed in string format specifier"
                    # otherwise

            return nn_max_len

        nn_max_len = nn_max_len()

        def tables_str_local(table_fields, fs_seq, nn_max_len, nn_seq):
            """Return a string representation for the specified table types."""

            # Initialize table
            table = PrettyTable(table_fields, padding_width=0)
            table.vertical_char = ' '
            table.junction_char = '-'
            table.set_field_align('Node', 'l')
            for field in table_fields[2:]: table.set_field_align(field, 'r')

            # Add totals row
            nn = '{:*^{}}'.format('Total', nn_max_len)
            for table_type in self._table_types:
                total_speeds = [self.lev1_summary_stats['fs'][fs][table_type]
                                for fs in fs_seq]
                total_speeds = [self._bytes_str(i) for i in total_speeds]
                total_speeds_total = self.lev2_summary_stats[table_type]
                total_speeds_total = self._bytes_str(total_speeds_total)
                table_type = self._table_types[table_type]['label_short']
                row = [nn, table_type, total_speeds_total] + total_speeds
                table.add_row(row)
                nn = ''

            # Add rows for previously determined file systems and node names
            for nn in nn_seq:
                nn_recs = [self.rec_select(nn, fs) for fs in fs_seq]
                    # self.rec_select(nn, fs) can potentially be == None
                nn_formatted = '{:.<{}}'.format(nn, nn_max_len)
                    # e.g. '{:.<{}}'.format('xy',4) = 'xy..'
                for table_type in self._table_types:
                    nn_speeds = [(nn_rec[table_type] if nn_rec else None) for
                                 nn_rec in nn_recs]
                    nn_speeds = [self._bytes_str(i) for i in nn_speeds]
                    nn_speeds_total = (
                        self.lev1_summary_stats['nn'][nn][table_type])
                    nn_speeds_total = self._bytes_str(nn_speeds_total)
                    table_type = self._table_types[table_type]['label_short']
                    row = ([nn_formatted, table_type, nn_speeds_total] +
                           nn_speeds)
                    table.add_row(row)
                    nn_formatted = ''

            # Construct printable tables string
            label_template = ('Bytes/s for top {} of {} active nodes out of '
                              '{} responding')
            label = label_template.format(nn_seq_len['displayed'],
                                          nn_seq_len['active'],
                                          len(self.lev1_summary_stats['nn']))
            tables_str = '\n{}:\n{}'.format(label, table)

            return tables_str

        tables_str = tables_str_local(table_fields, fs_seq, nn_max_len, nn_seq)
        return tables_str

class RecordGroupDeltaIterator:
    """Yield RecordGroupDelta objects."""

    def __iter__(self):

        self._receiver = Receiver()

        for rec_grp_prev, rec_grp_curr in common.pairwise(self._receiver):
            rec_grp_delta = rec_grp_curr - rec_grp_prev
#            for obj in (rec_grp_prev, rec_grp_curr, rec_grp_delta, ''):
#                print(obj)
            yield rec_grp_delta

    def close(self):
        """Close the subprocess providing data to the iterator.
        This must be used if an unhandled exception occurs.
        """
        self._receiver.close()


class Display(Logger):
    """Write RecordGroupDelta objects to the console in a user friendly
    format.
    """
    
#    # Establish encoding for curses
#    locale.setlocale(locale.LC_ALL, '')
#    _encoding = locale.getpreferredencoding() # typically 'UTF-8'

    # Set format string for datetime
    try:
        _d_t_fmt = locale.nl_langinfo(locale.D_T_FMT)
    except AttributeError:
        _d_t_fmt = '%a %b %e %H:%M:%S %Y'
            # obtained with locale.getlocale() == ('en_US', 'UTF8')

    def __init__(self):

        if not sys.stdout.isatty():
            err_msg = ('stdout is not open and connected to a tty-like device.'
                      ' If running the application on a host using ssh, use '
                      'the -t ssh option.')
            raise errors.TTYError(err_msg)

        try:
            self._init_curses()
            self._write_initial_status()
            self._write_recs()
        finally:

            try: curses.endwin() #@UndefinedVariable
            except curses.error: pass #@UndefinedVariable

            try: self._recgrps.close()
            except AttributeError: # Attribute in question is self._recgrps
                pass

            # Any unhandled exception that may have happened earlier is now
            # raised automatically.

            if params.PRINT_LAST_RECORD:
                try: print(self._recgrp_output_str)
                except AttributeError: pass

    def _init_curses(self):
        """Set up the curses display."""
        
        self.logger.info('Initializing curses...')

        self._alert_msg = ''

        self._win = curses.initscr()
        signal.siginterrupt(signal.SIGWINCH, False)
        # siginterrupt above prevents the SIGWINCH signal handler of curses
        # from raising IOError in Popen. Whether the signal is nevertheless
        # raised or not is unconfirmed, although getmaxyx results are still
        # updated.

        # Make cursor invisible
        try: curses.curs_set(0) #@UndefinedVariable
        except curses.error: pass #@UndefinedVariable
        # The error message "_curses.error: curs_set() returned ERR" can
        # possibly be returned when curses.curs_set is called. This can happen
        # if TERM does not support curs_set.
        #
        # Alternative way:
#        if curses.tigetstr('civis') is not None: #@UndefinedVariable
#            curses.curs_set(0) #@UndefinedVariable
        
        def _init_key_listener():
            """Set up the curses key listener thread."""
            
            def _key_listener():
                """Run the curses pause and resume key listener."""
        
                curses.noecho() #@UndefinedVariable
                self._win.nodelay(False)
        
                pause_key = params.DISPLAY_PAUSE_KEY
                alert = 'paused'
        
                while True:
                    time.sleep(0.1)
                        #   Techncially, sleep should not be necessary here
                        # because non-blocking mode is previously set by means
                        # of nodelay(False).
                        #   Nevertheless, sleep was found to avoid getkey/getch 
                        # from crashing (without any Exception) in a host with 
                        # version 5.5-24.20060715 of ncurses. Another host 
                        # (with version 5.7-3.20090208 of ncurses) was not 
                        # observed to have this bug even without sleep.
                        #   Key presses were observed to always be registered
                        # despite the sleep.
                    if self._win.getkey() == pause_key:
                        self._active = not self._active
                        with self._disp_lock:
                            if not self._active:
                                self._ins_alert(alert)
                            else:
                                self._del_alert()
                                    # This is useful in the event the next 
                                    # normal update to the window is several 
                                    # seconds later.
    
            self._active = True
            self._disp_lock = threading.Lock()
    
            _key_listener_thread = threading.Thread(group=None,
                                                    target=_key_listener,
                                                    name='KeyListener')
            _key_listener_thread.daemon = True
            _key_listener_thread.start()

        _init_key_listener()

    def _ins_alert(self, alert):
        """Insert the supplied alert str into the second row. Any prior alert
        is first deleted.
        """

        self._del_alert()
            # Delete previous alert so that multiple alerts are not displayed
            # at once.
        self._alert_msg = alert
            # Store current alert to make it available for later deletion.

        # Insert alert
        if alert:
            w = self._win
            try:
                w.insstr(1, 0, '() ')
                w.insstr(1, 1, alert, curses.A_UNDERLINE) #@UndefinedVariable
            except: pass

    def _del_alert(self):
        """Delete the most recent alert str from the second row."""

        if self._alert_msg:
            try:
                for _ in range(len(self._alert_msg) + 3):
                    self._win.delch(1, 0)
            except: pass
            self._alert_msg = ''

    def _write_initial_status(self):
        """Write the initial collection status."""

        self.logger.info('Writing initial status...')
        with self._disp_lock:
            nodeset = params.GPFS_NODESET or 'first available'
            status_template = ('{}\n\nCollecting initial data for {} nodeset '
                               'from {}.\n\nWait {:.0f}s.')
            status = status_template.format(params._PROGRAM_NAME,
                                            nodeset,
                                            params.MMPMON_HOST,
                                            params.MONITORING_INTERVAL_SECS*2)
                # params.MONITORING_INTERVAL_SECS is multiplied by 2 because
                # data is fully received for an iteration only after the next
                # iteration has internally begun to be received.
            
            self._write(status)

    def _write_recs(self):
        """Write individual records."""

        self.logger.info('Writing records...')
        self._recgrps = RecordGroupDeltaIterator()
        for recgrp in self._recgrps:
            if self._active and self._disp_lock.acquire(False):
                self._recgrp_output_str = self._format_output(recgrp)
                self._write(self._recgrp_output_str)
                self._disp_lock.release()

        # Allow time for the final update to be seen
        time.sleep(params.MONITORING_INTERVAL_SECS)

    def _format_output(self, recgrp):
        """Return the formatted string to display to the screen."""
        
        strftime = lambda dt: dt.strftime(self._d_t_fmt).replace('  ', ' ')
            # replace is used above to for example replace 'Feb  3' to 'Feb 3'

        datetime_now = datetime.datetime.now()
        recgrp_timestamp_age = datetime_now - recgrp.timestamp
        recgrp_timestamp_age = recgrp_timestamp_age.total_seconds()

        # Determine header
        title = '{} [updated {}]'.format(params._PROGRAM_NAME,
                                         strftime(datetime_now))
        status_template = ('Displaying activity for {:.1f}s before the past '
                           '{:.1f}s.\n')
        status = status_template.format(recgrp.time_duration_secs,
                                        recgrp_timestamp_age)
        header = '\n'.join((title, status))

        # Determine table string
        num_avail_lines = self._win.getmaxyx()[0] - header.count('\n')
        num_avail_lines = max(num_avail_lines, 0)
        tables_str = recgrp.tables_str(format_=params.TABLE_TYPE,
                                       num_avail_lines=num_avail_lines)

        return header + tables_str

    def _write(self, str_):
        """Update the display with the provided string."""

        w = self._win
        w.erase()

        try:
            w.addstr(str(str_))
            w.addstr(0, 0, params._PROGRAM_NAME,
                     curses.A_BOLD) #@UndefinedVariable
        except: pass
        # The try except block was found to prevent occasional errors by
        # addstr, but not if the block enclosed all w actions, which is
        # unexpected.

        w.refresh()


if __name__ == '__main__':

    logger = logging.getLogger(params._PROGRAM_NAME_SHORT)

    try:
        ArgParser()
        DiagnosticLoggerSetup()
        Display()

    except (KeyboardInterrupt, errors.Error, Exception) as exception:

        try:
            logger.exception(exception)
        except AttributeError:
            # Likely cause: AttributeError: type object 'NullHandler' has no
            # attribute 'level'
            pass

        if isinstance(exception, KeyboardInterrupt):
            exit()
        elif isinstance(exception, errors.Error) and exception.args:
            exit('\n'.join(exception.args))
        else:
            raise
