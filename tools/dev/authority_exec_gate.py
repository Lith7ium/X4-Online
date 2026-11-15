#!/usr/bin/env python3
"""Exec a command only after one parent pipe byte; private test helper."""
import os
import sys


def main():
    if len(sys.argv)<3: return 2
    fd=int(sys.argv[1])
    try: go=os.read(fd,1)
    finally: os.close(fd)
    if go!=b'G': return 1
    os.execvp(sys.argv[2],sys.argv[2:])
    return 1

if __name__=='__main__': sys.exit(main())
