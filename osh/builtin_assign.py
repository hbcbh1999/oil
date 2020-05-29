#!/usr/bin/env python2
"""
builtin_assign.py
"""
from __future__ import print_function

from _devbuild.gen.option_asdl import builtin_i
from _devbuild.gen.runtime_asdl import (
    value, value_e, value_t, value__Bool, value__Str, value__MaybeStrArray,
    value__AssocArray,
    lvalue, lvalue_e, scope_e, cmd_value__Argv, cmd_value__Assign,
)
from _devbuild.gen.syntax_asdl import source
from _devbuild.gen import arg_types

from frontend import flag_spec
from frontend import args
from core import error
from core.pyerror import e_usage
from qsn_ import qsn
from core import state
from core import ui
from core import vm
from core.util import log, e_die

from typing import cast, Optional, Dict, List, TYPE_CHECKING
if TYPE_CHECKING:
  from _devbuild.gen.syntax_asdl import command__ShFunction
  from core import optview
  from core.state import Mem
  from core.ui import ErrorFormatter
  from frontend.args import _Attributes
  from frontend.parse_lib import ParseContext
  from osh.sh_expr_eval import ArithEvaluator

_ = log


_OTHER = 0
_READONLY = 1
_EXPORT = 2


def _PrintVariables(mem, cmd_val, attrs, print_flags, builtin=_OTHER):
  # type: (Mem, cmd_value__Assign, _Attributes, bool, int) -> int
  """
  Args:
    print_flags: whether to print flags
    builtin: is it the readonly or export builtin?
  """
  flag = attrs.attrs

  # Turn dynamic vars to static.
  tmp_g = flag.get('g')
  tmp_a = flag.get('a')
  tmp_A = flag.get('A')

  flag_g = cast(value__Bool, tmp_g).b if tmp_g and tmp_g.tag_() == value_e.Bool else False
  flag_a = cast(value__Bool, tmp_a).b if tmp_a and tmp_a.tag_() == value_e.Bool else False
  flag_A = cast(value__Bool, tmp_A).b if tmp_A and tmp_A.tag_() == value_e.Bool else False

  tmp_n = flag.get('n')
  tmp_r = flag.get('r')
  tmp_x = flag.get('x')

  #log('FLAG %r', flag)

  # SUBTLE: export -n vs. declare -n.  flag vs. OPTION.
  # flags are value.Bool, while options are Undef or Str.
  # '+', '-', or None
  flag_n = cast(value__Str, tmp_n).s if tmp_n and tmp_n.tag_() == value_e.Str else None
  flag_r = cast(value__Str, tmp_r).s if tmp_r and tmp_r.tag_() == value_e.Str else None
  flag_x = cast(value__Str, tmp_x).s if tmp_x and tmp_x.tag_() == value_e.Str else None

  lookup_mode = scope_e.Dynamic
  if cmd_val.builtin_id == builtin_i.local:
    if flag_g and not mem.IsGlobalScope():
      return 1
    lookup_mode = scope_e.LocalOnly
  elif flag_g:
    lookup_mode = scope_e.GlobalOnly

  if len(cmd_val.pairs) == 0:
    print_all = True
    cells = mem.GetAllCells(lookup_mode)
    names = sorted(cells)  # type: List[str]
  else:
    print_all = False
    names = []
    cells = {}
    for pair in cmd_val.pairs:
      name = pair.var_name
      if pair.rval and pair.rval.tag_() == value_e.Str:
        # Invalid: declare -p foo=bar
        # Add a sentinel so we skip it, but know to exit with status 1.
        s = cast(value__Str, pair.rval).s
        invalid = "%s=%s" % (name, s)
        names.append(invalid)
        cells[invalid] = None
      else:
        names.append(name)
        cells[name] = mem.GetCell(name, lookup_mode)

  count = 0
  for name in names:
    cell = cells[name]
    if cell is None: continue  # Invalid
    val = cell.val
    #log('name %r %s', name, val)

    if val.tag_() == value_e.Undef: continue
    if builtin == _READONLY and not cell.readonly: continue
    if builtin == _EXPORT and not cell.exported: continue

    if flag_n == '-' and not cell.nameref: continue
    if flag_n == '+' and cell.nameref: continue
    if flag_r == '-' and not cell.readonly: continue
    if flag_r == '+' and cell.readonly: continue
    if flag_x == '-' and not cell.exported: continue
    if flag_x == '+' and cell.exported: continue

    if flag_a and val.tag_() != value_e.MaybeStrArray: continue
    if flag_A and val.tag_() != value_e.AssocArray: continue

    decl = []  # type: List[str]
    if print_flags:
      flags = []  # type: List[str]
      if cell.nameref: flags.append('n')
      if cell.readonly: flags.append('r')
      if cell.exported: flags.append('x')
      if val.tag_() == value_e.MaybeStrArray:
        flags.append('a')
      elif val.tag_() == value_e.AssocArray:
        flags.append('A')
      if len(flags) == 0: flags.append('-')

      decl.extend(["declare -", ''.join(flags), " ", name])
    else:
      decl.append(name)

    if val.tag_() == value_e.Str:
      str_val = cast(value__Str, val)
      decl.extend(["=", qsn.maybe_shell_encode(str_val.s)])
    elif val.tag_() == value_e.MaybeStrArray:
      array_val = cast(value__MaybeStrArray, val)
      if None in array_val.strs:
        # Note: Arrays with unset elements are printed in the form:
        #   declare -p arr=(); arr[3]='' arr[4]='foo' ...
        decl.append("=()")
        first = True
        for i, element in enumerate(array_val.strs):
          if element is not None:
            if first:
              decl.append(";")
              first = False
            decl.extend([" ", name, "[", str(i), "]=",
                         qsn.maybe_shell_encode(element)])
      else:
        body = []  # type: List[str]
        for element in array_val.strs:
          if len(body) > 0: body.append(" ")
          body.append(qsn.maybe_shell_encode(element))
        decl.extend(["=(", ''.join(body), ")"])
    elif val.tag_() == value_e.AssocArray:
      assoc_val = cast(value__AssocArray, val)
      body = []
      for key in sorted(assoc_val.d):
        if len(body) > 0: body.append(" ")
        key_quoted = qsn.maybe_shell_encode(key, flags=qsn.MUST_QUOTE)
        value_quoted = qsn.maybe_shell_encode(assoc_val.d[key])
        body.extend(["[", key_quoted, "]=", value_quoted])
      if len(body) > 0:
        decl.extend(["=(", ''.join(body), ")"])

    print(''.join(decl))
    count += 1

  if print_all or count == len(names):
    return 0
  else:
    return 1


class Export(vm._AssignBuiltin):
  def __init__(self, mem, errfmt):
    # type: (Mem, ErrorFormatter) -> None
    self.mem = mem
    self.errfmt = errfmt

  def Run(self, cmd_val):
    # type: (cmd_value__Assign) -> int
    arg_r = args.Reader(cmd_val.argv, spids=cmd_val.arg_spids)
    arg_r.Next()
    attrs = flag_spec.Parse('export_', arg_r)
    arg = arg_types.export_(attrs.attrs)
    #arg = attrs

    if arg.f:
      e_usage(
          "doesn't accept -f because it's dangerous.  "
          "(The code can usually be restructured with 'source')")

    if arg.p or len(cmd_val.pairs) == 0:
      return _PrintVariables(self.mem, cmd_val, attrs, True, builtin=_EXPORT)


    if arg.n:
      for pair in cmd_val.pairs:
        if pair.rval is not None:
          e_usage("doesn't accept RHS with -n", span_id=pair.spid)

        # NOTE: we don't care if it wasn't found, like bash.
        self.mem.ClearFlag(pair.var_name, state.ClearExport, scope_e.Dynamic)
    else:
      for pair in cmd_val.pairs:
        # NOTE: when rval is None, only flags are changed
        self.mem.SetVar(lvalue.Named(pair.var_name), pair.rval, scope_e.Dynamic,
                        flags=state.SetExport)

    return 0


def _ReconcileTypes(rval, flag_a, flag_A, span_id):
  # type: (Optional[value_t], bool, bool, int) -> value_t
  """Check that -a and -A flags are consistent with RHS.

  Special case: () is allowed to mean empty indexed array or empty assoc array
  if the context is clear.

  Shared between NewVar and Readonly.
  """
  if flag_a and rval is not None and rval.tag_() != value_e.MaybeStrArray:
    e_usage("Got -a but RHS isn't an array", span_id=span_id)

  if flag_A and rval:
    # Special case: declare -A A=() is OK.  The () is changed to mean an empty
    # associative array.
    if rval.tag_() == value_e.MaybeStrArray:
      array_val = cast(value__MaybeStrArray, rval)
      if len(array_val.strs) == 0:
        return value.AssocArray({})
        #return value.MaybeStrArray([])

    if rval.tag_() != value_e.AssocArray:
      e_usage("Got -A but RHS isn't an associative array", span_id=span_id)

  return rval


class Readonly(vm._AssignBuiltin):
  def __init__(self, mem, errfmt):
    # type: (Mem, ErrorFormatter) -> None
    self.mem = mem
    self.errfmt = errfmt

  def Run(self, cmd_val):
    # type: (cmd_value__Assign) -> int
    arg_r = args.Reader(cmd_val.argv, spids=cmd_val.arg_spids)
    arg_r.Next()
    attrs = flag_spec.Parse('readonly', arg_r)
    arg = arg_types.readonly(attrs.attrs)

    if arg.p or len(cmd_val.pairs) == 0:
      return _PrintVariables(self.mem, cmd_val, attrs, True, builtin=_READONLY)

    for pair in cmd_val.pairs:
      if pair.rval is None:
        if arg.a:
          rval = value.MaybeStrArray([])  # type: value_t
        elif arg.A:
          rval = value.AssocArray({})
        else:
          rval = None
      else:
        rval = pair.rval

      rval = _ReconcileTypes(rval, arg.a, arg.A, pair.spid)

      # NOTE:
      # - when rval is None, only flags are changed
      # - dynamic scope because flags on locals can be changed, etc.
      self.mem.SetVar(lvalue.Named(pair.var_name), rval, scope_e.Dynamic,
                      flags=state.SetReadOnly)

    return 0


class NewVar(vm._AssignBuiltin):
  """declare/typeset/local."""

  def __init__(self, mem, funcs, errfmt):
    # type: (Mem, Dict[str, command__ShFunction], ErrorFormatter) -> None
    self.mem = mem
    self.funcs = funcs
    self.errfmt = errfmt

  def _PrintFuncs(self, names):
    # type: (List[str]) -> int
    status = 0
    for name in names:
      if name in self.funcs:
        print(name)
        # TODO: Could print LST for -f, or render LST.  Bash does this.  'trap'
        # could use that too.
      else:
        status = 1
    return status

  def Run(self, cmd_val):
    # type: (cmd_value__Assign) -> int
    arg_r = args.Reader(cmd_val.argv, spids=cmd_val.arg_spids)
    arg_r.Next()
    attrs = flag_spec.Parse('new_var', arg_r)
    arg = arg_types.new_var(attrs.attrs)

    status = 0

    if arg.f:
      names = arg_r.Rest()
      if len(names):
        # NOTE: in bash, -f shows the function body, while -F shows the name.
        # Right now we just show the name.
        status = self._PrintFuncs(names)
      else:
        e_usage('passed -f without args')
      return status

    if arg.F:
      names = arg_r.Rest()
      if len(names):
        status = self._PrintFuncs(names)
      else:  # weird bash quirk: they're printed in a different format!
        for func_name in sorted(self.funcs):
          print('declare -f %s' % (func_name))
      return status

    if arg.p:  # Lookup and print variables.
      return _PrintVariables(self.mem, cmd_val, attrs, True)
    elif len(cmd_val.pairs) == 0:
      return _PrintVariables(self.mem, cmd_val, attrs, False)

    #
    # Set variables
    #

    #raise error.Usage("doesn't understand %s" % cmd_val.argv[1:])
    if cmd_val.builtin_id == builtin_i.local:
      lookup_mode = scope_e.LocalOnly
    else:  # declare/typeset
      if arg.g:  
        lookup_mode = scope_e.GlobalOnly
      else:
        lookup_mode = scope_e.LocalOnly

    flags = 0
    if arg.x == '-': 
      flags |= state.SetExport
    if arg.r == '-':
      flags |= state.SetReadOnly
    if arg.n == '-':
      flags |= state.SetNameref

    flags_to_clear = 0
    if arg.x == '+': 
      flags |= state.ClearExport
    if arg.r == '+':
      flags |= state.ClearReadOnly
    if arg.n == '+':
      flags |= state.ClearNameref

    for pair in cmd_val.pairs:
      rval = pair.rval
      # declare -a foo=(a b); declare -a foo;  should not reset to empty array
      if rval is None and (arg.a or arg.A):
        old_val = self.mem.GetVar(pair.var_name)
        if arg.a:
          if old_val.tag_() != value_e.MaybeStrArray:
            rval = value.MaybeStrArray([])
        elif arg.A:
          if old_val.tag_() != value_e.AssocArray:
            rval = value.AssocArray({})

      rval = _ReconcileTypes(rval, arg.a, arg.A, pair.spid)
      self.mem.SetVar(lvalue.Named(pair.var_name), rval, lookup_mode, flags=flags)

    return status


# TODO:
# - It would make more sense to treat no args as an error (bash doesn't.)
#   - Should we have strict builtins?  Or just make it stricter?

class Unset(vm._Builtin):

  def __init__(self, mem, exec_opts, funcs, parse_ctx, arith_ev, errfmt):
    # type: (Mem, optview.Exec, Dict[str, command__ShFunction], ParseContext, ArithEvaluator, ErrorFormatter) -> None
    self.mem = mem
    self.exec_opts = exec_opts
    self.funcs = funcs
    self.parse_ctx = parse_ctx
    self.arith_ev = arith_ev
    self.errfmt = errfmt

  def _UnsetVar(self, arg, spid, proc_fallback):
    # type: (str, int, bool) -> bool
    """
    Returns:
      bool: whether the 'unset' builtin should succeed with code 0.
    """
    arena = self.parse_ctx.arena

    a_parser = self.parse_ctx.MakeArithParser(arg)
    arena.PushSource(source.ArgvWord(spid))
    try:
      anode = a_parser.Parse()
    except error.Parse as e:
      # show parse error
      ui.PrettyPrintError(e, arena)
      # point to word
      e_usage('Invalid unset expression', span_id=spid)
    finally:
      arena.PopSource()

    lval = self.arith_ev.EvalArithLhs(anode, spid)

    # Prevent attacks like these by default:
    #
    # unset -v 'A["$(echo K; rm *)"]'
    if not self.exec_opts.eval_unsafe_arith() and lval.tag_() != lvalue_e.Named:
      e_die('Expected a variable name.  Expressions are allowed with shopt -s eval_unsafe_arith', span_id=spid)

    #log('lval %s', lval)
    found = False
    try:
      # not strict
      found = self.mem.Unset(lval, scope_e.Dynamic, False)
    except error.Runtime as e:
      # note: in bash, myreadonly=X fails, but declare myreadonly=X doens't
      # fail because it's a builtin.  So I guess the same is true of 'unset'.
      e.span_id = spid
      ui.PrettyPrintError(e, arena)
      return False

    if proc_fallback and not found:
      if arg in self.funcs:
        del self.funcs[arg]

    return True

  def Run(self, cmd_val):
    # type: (cmd_value__Argv) -> int
    attrs, arg_r = flag_spec.ParseCmdVal('unset', cmd_val)
    arg = arg_types.unset(attrs.attrs)

    argv, arg_spids = arg_r.Rest2()
    for i, name in enumerate(argv):
      spid = arg_spids[i]

      if arg.f:
        if name in self.funcs:
          del self.funcs[name]

      elif arg.v:
        if not self._UnsetVar(name, spid, False):
          return 1

      else:
        # proc_fallback: Try to delete var first, then func.
        if not self._UnsetVar(name, spid, True):
          return 1

    return 0


class Shift(vm._Builtin):

  def __init__(self, mem):
    # type: (Mem) -> None
    self.mem = mem

  def Run(self, cmd_val):
    # type: (cmd_value__Argv) -> int
    num_args = len(cmd_val.argv) - 1
    if num_args == 0:
      n = 1
    elif num_args == 1:
      arg = cmd_val.argv[1]
      try:
        n = int(arg)
      except ValueError:
        e_usage("Invalid shift argument %r" % arg)
    else:
      e_usage('got too many arguments')

    return self.mem.Shift(n)
