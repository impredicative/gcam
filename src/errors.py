# Reference:
# http://docs.python.org/dev/py3k/library/exceptions.html
# http://docs.python.org/dev/py3k/tutorial/errors.html

class Error(Exception):
    """Base class for exceptions in this module.

    Exceptions are expected to be raised with a descriptive str message
    argument."""

class ArgumentError(Error):
    """Exception raised for an invalid argument value provided by the user
    either on the command line or in the parameters file.
    """

class SubprocessError(Error):
    """Exception raised for an error while attempting to run a subprocess."""

class TTYError(Error):
    """Exception raised if stdout is not connected to a tty-like device."""