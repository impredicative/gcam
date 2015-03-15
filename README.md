**gcam** ([GPFS](http://www-03.ibm.com/systems/software/gpfs/) Current Activity Monitor) uses [mmpmon](http://publib.boulder.ibm.com/infocenter/clresctr/vxrx/topic/com.ibm.cluster.gpfs321.advanceadm.doc/bl1adv_mmpmonch.html), [Python 3.2](http://www.python.org/download/releases/3.2/) and [ncurses](http://www.gnu.org/software/ncurses/) on Linux to display in a console the current GPFS read and write bytes across all currently active GPFS nodes and all GPFS file systems in a given GPFS cluster.

## Screenshot ##

<img src='http://i.imgur.com/7SgW5Xb.png' border='1' title='gcam screenshot' />

## Requirements ##
  * Linux or similar OS. The code is tested with [CentOS](http://centos.org/) 5.7.
  * GPFS. The code is developed with GPFS version 3.2.1-4 only. It has also been tested by users with GPFS versions 3.2.1-25 and 3.3.0. It is not know whether other versions of GPFS provide compatible mmpmon output. It is possible for the host providing mmpmon output to be different from the host running `gcam`.
  * [Python 3.2](http://www.python.org/download/releases/3.2/) (not >3.2) with `curses` support. On CentOS, ensure that `ncurses`, `ncurses-devel`, and all other such `ncurses` packages are installed before compiling Python. To install Python, one can download its source and use the commands `./configure`, `make`, and `make altinstall`. Older or newer versions of Python will not work. Using `altinstall` will allow the installation to coexist with other versions of Python that may be installed.

## Implementation ##
The program uses the `fs_io_s` command sent to the `mmpmon` program to obtain read and write bytes counters. It then calculates deltas over successive counters—these deltas are formatted and displayed on the screen.

### Limitations ###
The code is not nearly as efficient as it can be. Additionally, it has some quadratic operations which may make it scale poorly. A significant rewrite is warranted to address this and other issues.

`mmpmon` does not indicate when the current batch of counters has ended. The program currently learns of this by waiting until the next batch has begun. This delays the display by up to one iteration. The program can possibly be updated to use a more sophisticated approach to predict when the current batch has ended—this would reduce the display delay.

If necessary, the _refresh interval_ parameter value can be increased by the user to proportionately spread out the program's CPU usage over time. For large installations, this can ensure that the program's CPU usage does not persistently approach 100% for the specific CPU core that is in use.

At the current time, the program does not allow logging data for archival or analytic purposes, although it does allow diagnostic logging for debugging purposes.

## Installation ##
  * Ensure that the listed [requirements](#Requirements.md) are met.

  * Download at least the compiled byte code zip file from the [Downloads](http://code.google.com/p/gcam/downloads/list) tab into `/usr/local/src`, preferably on to a GPFS node. It is _not_ necessary to extract the contents of this archive into this destination, although they can optionally be extracted into an empty user directory to review or modify the code.

  * Create an executable text file `gcam` in `/usr/local/bin` with the contents:
```
#!/bin/bash
/usr/local/bin/python3.2 /usr/local/src/gcam.compiled.python3.2.zip "$@"
```
> Adjust the path to the Python binary in the line above if and as necessary.

  * If the program may be run by a non-root user `foousr`, use `visudo` to consider adding the line:
```
foousr   ALL=NOPASSWD:   /usr/local/bin/gcam
```
> This should allow the user to use `sudo` to run the program correctly. For further ease of use, an alias `gcam` pointing to `sudo gcam` can be added for this user to prevent from having to explicitly use `sudo`.

## Usage ##
After having performed the program installation as is noted above, it can be run as `gcam` without any arguments. Run with the `-h` argument to display help and available command-line options. The `params.py` file in the source zip archive can be edited to change the default values of some options, although this should typically not be necessary.

## Changelog ##
Note that minor changes are not documented.

2012-02-06
  * GPFS filesystem columns now use natural-sort.
  * Fixed a bytes/sec formatting bug.

2011-09-27
  * Worked around a `curses` `getkey` bug.

2011-05-04
  * Implemented optional diagnostic logging.
  * `mmpmon` is now sent one node name per line instead of all node names in the same line.

2011-03-07
  * Make cursor invisible only if this is supported by the terminal.

2011-02-03
  * Initial release.
