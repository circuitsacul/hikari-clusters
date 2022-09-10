import sys

from .brain import run as runbrain
from .server import run as runserver

if __name__ == "__main__":
    try:
        t = sys.argv[1]
    except IndexError:
        print('Please specify either "brain" or "server":')
        print("\tpython -m examples.basic brain/server")
        exit()
    if t == "brain":
        runbrain()
    elif t == "server":
        runserver()
