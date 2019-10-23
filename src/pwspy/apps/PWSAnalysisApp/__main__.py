import os
import traceback

from pwspy.apps.PWSAnalysisApp.App import PWSApp
from pwspy.apps.PWSAnalysisApp import applicationVars


def isIpython():
    try:
        return __IPYTHON__
    except:
        return False


if __name__ == '__main__':
    import sys

    # This prevents errors from happening silently. Found on stack overflow.
    sys.excepthook_backup = sys.excepthook
    def exception_hook(exctype, value, traceBack):
        print(exctype, value, traceBack)
        sys.excepthook_backup(exctype, value, traceBack)
        sys.exit(1)
    sys.excepthook = exception_hook

    try:
        if isIpython():  # IPython runs its own QApplication so we handle things slightly different.
            app = PWSApp(sys.argv)
        else:
            print("Starting setup")
            app = PWSApp(sys.argv)
            print("Application setup complete")
            sys.exit(app.exec_())
    except Exception as e: # Save error to text file.
        with open(os.path.join(applicationVars.dataDirectory, 'crashLog.txt'), 'w') as f:
            traceback.print_exc(limit=None, file=f)
            print(f"Error Occurred: Please check {os.path.join(applicationVars.dataDirectory, 'crashLog.txt')}")
        raise e
