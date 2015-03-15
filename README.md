# gcam

**gcam** ([GPFS](http://www-03.ibm.com/systems/software/gpfs/) Current Activity Monitor) uses [mmpmon](http://publib.boulder.ibm.com/infocenter/clresctr/vxrx/topic/com.ibm.cluster.gpfs321.advanceadm.doc/bl1adv_mmpmonch.html), [Python 3.2](http://www.python.org/download/releases/3.2/) and [ncurses](http://www.gnu.org/software/ncurses/) on Linux to display in a console the current GPFS read and write bytes across all currently active GPFS nodes and all GPFS file systems in a given GPFS cluster.

https://github.com/impredicative/gcam/

## Contents
- [Screenshot](#screenshot)
- [Requirements](#requirements)
- [Usage](#usage)
- [Implementation](#implementation)
- [License](#license)

## Screenshot
<img src='http://i.imgur.com/7SgW5Xb.png' border='1' title='gcam screenshot' />

## Requirements
  * Linux or similar OS. The code is tested with [CentOS](http://centos.org/) 5.7.
  * GPFS. The code is developed with GPFS version 3.2.1-4 only. It has also been tested by users with GPFS versions 3.2.1-25 and 3.3.0. It is not know whether other versions of GPFS provide compatible mmpmon output. It is possible for the host providing mmpmon output to be different from the host running `gcam`.
  * [Python 3.2](http://www.python.org/download/releases/3.2/) (not >3.2) with `curses` support. On CentOS, ensure that `ncurses`, `ncurses-devel`, and all other such `ncurses` packages are installed before compiling Python. To install Python, one can download its source and use the commands `./configure`, `make`, and `make altinstall`. Older or newer versions of Python will not work. Using `altinstall` will allow the installation to coexist with other versions of Python that may be installed.

## Usage
The program can be run as `gcam` without any arguments. Run with the `-h` argument to display help and available command-line options. If the program fails to start, edit the `gcam` file. The `params.py` file in the source zip archive can be edited to change the default values of some options, although this should typically not be necessary.

### sudo
If the program needs to be run by a non-root user `foousr`, use `visudo` to consider add a line such as:
```
foousr   ALL=NOPASSWD:   ~/gcam/gcam
```
This should allow the user to use `sudo` to run the program. For further ease of use, an alias `gcam` pointing to `sudo gcam` can be added for this user to prevent from having to explicitly use `sudo`.

## Implementation
The program uses the `fs_io_s` command sent to the `mmpmon` program to obtain read and write bytes counters. It then calculates deltas over successive counters—these deltas are formatted and displayed on the screen.

The code is not nearly as efficient as it can be. Additionally, it has some quadratic operations which may make it scale poorly. A significant rewrite is warranted to address this and other issues.

`mmpmon` does not indicate when the current batch of counters has ended. The program currently learns of this by waiting until the next batch has begun. This delays the display by up to one iteration. The program can possibly be updated to use a more sophisticated approach to predict when the current batch has ended—this would reduce the display delay.

If necessary, the _refresh interval_ parameter value can be increased by the user to proportionately spread out the program's CPU usage over time. For large installations, this can ensure that the program's CPU usage does not persistently approach 100% for the specific CPU core that is in use.

At the current time, the program does not allow logging data for archival or analytic purposes, although it does allow diagnostic logging for debugging purposes.

## License
See [license](LICENSE). For the `prettytable` module, see [src/prettytable.py](src/prettytable.py).
