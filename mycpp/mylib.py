"""
runtime.py
"""
from __future__ import print_function

import sys
import cStringIO

from typing import Any

# For conditional translation
CPP = False
PYTHON = True


def NewStr(s):
  """Hack to translate conar char* s to Str * in C++."""
  return s


# C code ignores this!
def log(msg, *args):
  # type: (str, *Any) -> None
  if args:
    msg = msg % args
  print(msg, file=sys.stderr)


# TODO: Do we need this?
def p_die(msg, *args):
  # type: (str, *Any) -> None
  raise RuntimeError(msg % args)


BufWriter = cStringIO.StringIO

BufLineReader = cStringIO.StringIO


def Stdout():
  return sys.stdout


def Stdin():
  return sys.stdin


class switch(object):
  """A ContextManager that translates to a C switch statement."""

  def __init__(self, value):
    # type: (int) -> None
    self.value = value

  def __enter__(self):
    # type: () -> switch
    return self

  def __exit__(self, type, value, traceback):
    # type: (Any, Any, Any) -> bool
    return False  # Allows a traceback to occur

  def __call__(self, *cases):
    # type: (*Any) -> bool
    return self.value in cases


class typeswitch(object):
  """A ContextManager that translates to switch statement over ASDL types."""

  def __init__(self, value):
    # type: (int) -> None
    self.value = value

  def __enter__(self):
    # type: () -> typeswitch
    return self

  def __exit__(self, type, value, traceback):
    # type: (Any, Any, Any) -> bool
    return False  # Allows a traceback to occur

  def __call__(self, *cases):
    # type: (*Any) -> bool
    return isinstance(self.value, cases)
