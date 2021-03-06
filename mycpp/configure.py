#!/usr/bin/env python2
"""
configure.py

Layout:

examples/
  cgi.py
  containers.py

_gen/
  cgi.cc
  containers.cc
  (and _raw.cc generated by shell; not visible to Ninja)

  - change this to _translate?

_bin/
  cgi.{gc_debug,asan,opt}
  containers.{gc_debug,asan,opt}

  - change this to _build?  Then you'll have build logs too.

_test/
  cgi.{gc_debug,asan,opt}.task.txt   # status, elapsed time, rusage()
  cgi.{gc_debug,asan,opt}.log        # stdout an stderr

_benchmark/
  cgi.{gc_debug,asan,opt}.task.txt   # status, elapsed time, rusage()
  cgi.{gc_debug,asan,opt}.log        # stdout an stderr

  For 'opt', this is a benchmark.  For gc_debug and asan, it's really a stress
  test.

Also:

- TSV summary of all task.txt
  - test and benchmark.  And maybe translate/compile
- .wwz archive of all the logs.
- Turn it into HTML and link to logs.  Basically just like Toil does.

Notes for Oil: 

- escape_path() in ninja_syntax seems wrong?  It should really take $ to $$.

    return word.replace('$ ', '$$ ').replace(' ', '$ ').replace(':', '$:')

  Ninja shouldn't have used $ and ALSO used shell commands (sh -c)!  Better
  solutions:

  - Spawn a process with environment variables.
  - use % for substitution instead
"""

from __future__ import print_function

import os
import sys

sys.path.append('../vendor')
import ninja_syntax


def main(argv):
  n = ninja_syntax.Writer(open('build.ninja', 'w'))

  n.comment('Translate, compile, and test mycpp examples.')
  n.comment('Generated by %s.' % os.path.basename(__file__))
  n.newline()

  n.rule('translate',
         command='./run.sh ninja-translate $in $out',
         description='translate $in $out')
  n.newline()
  n.rule('compile',
         command='./run.sh ninja-compile $variant $in $out',
         description='compile $variant $in $out')
  n.newline()

  # TODO:
  # _ninja/
  #   logs/  # side effects
  #     typecheck/  # optional?
  #     translate/
  #     compile/
  #     test/
  #     benchmark/
  #   tasks/  # these are proper outputs, at least for test and benchmark?
  #     typecheck/  # optional?
  #     translate/
  #     compile/
  #     test/
  #     benchmark/
  #
  #   gen/    # source
  #   bin/    # binaries

  examples = ['cgi', 'containers']
  for ex in examples:
    n.build('_ninja/gen/%s.cc' % ex, 'translate', 'examples/%s.py' % ex)
    n.newline()

    # TODO: Can also parameterize by CXX: Clang or GCC.
    for variant in ['gc_debug', 'asan', 'opt']:
      n.build('_ninja/bin/%s.$variant' % ex, 'compile', '_ninja/gen/%s.cc' % ex,
              variables=[('variant', variant)])
      n.newline()


if __name__ == '__main__':
  try:
    main(sys.argv)
  except RuntimeError as e:
    print('FATAL: %s' % e, file=sys.stderr)
    sys.exit(1)
