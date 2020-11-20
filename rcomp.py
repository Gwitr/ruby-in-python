# Important things TODO: Overhaul the whole exception system (to add support for actual line numbers)

import dis
import sys
import warnings
import traceback
import rlex, rast
from functools import partial

class RubyErrors:
    
    class StandardError(Exception):
        pass

    class NameError(StandardError):
        pass

    class NoMethodError(StandardError):
        pass

class RubyWarning(UserWarning):
    pass

class Locals():
    
    def __init__(self):
        self.stack = [{}]

    def push(self):
        self.stack.append({})

    def pop(self):
        self.stack.pop()

    def update(self, d):
        if d is None:
            return
        self.stack[-1].update(d)

    def __getitem__(self, x):
        def _wrap(y):
            nonlocal x, self
            self[x[:-1]] = y
        
        if x.endswith("="):
            return _wrap
        
        for i in reversed(self.stack):
            if x in i:
                return i[x]
        
        raise RubyErrors.NameError("undefined local variable or method `%s'" % (x, ))

    def __setitem__(self, x, y):
        def _wrap():
            nonlocal y
            return y
        
        if callable(y):
            self.stack[-1][x] = y
        else:
            self.stack[-1][x] = _wrap

class Methods():

    def __init__(self, parent, v=None):
        self.parent = parent
        self.v = v
        if self.v is None:
            self.v = {}

    def __getitem__(self, x):
        try:
            return self.v[x]
        except KeyError:
            raise RubyErrors.NoMethodError("undefined method `%s' for %s" % (x, self.parent.__name__)) from None

    def __setitem__(self, x, y):
        self.v[x] = y

class Constants():

    def __init__(self, v):
        self.v = v
        if self.v is None:
            self.v = {}

    def __getitem__(self, x):
        if x not in self.v:
            raise RubyErrors.NameError("Uninitialized constant %s" % x)
        return self.v[x]

    def __setitem__(self, x, y):
        if x in self.v:
            warnings.warn(RubyWarning("alerady initialized constant %s" % x))
        self.v[x] = y

class Globals():

    def __init__(self, v):
        self.v = v
        if self.v is None:
            self.v = {}

    def __getitem__(self, x):
        return self.v.get(x)

    def __setitem__(self, x, y):
        self.v[x] = y

class Object():

    def __init__(self, *args):
        self.__name__ = "Object"
        self.methods = Methods(self, {
            "initialize": self.initialize,
            "to_s": self.to_s,
            "==": partial(object.__eq__, self),
            "!=": partial(object.__ne__, self)
        })
        self.ivars = {}
        return self.methods["initialize"](*args)
    
    def __add__(self, other):
        return self.methods["+"](other)
    def __sub__(self, other):
        return self.methods["-"](other)
    def __mul__(self, other):
        return self.methods["*"](other)
    def __truediv__(self, other):
        return self.methods["/"](other)

    def __gt__(self, other):
        return self.methods[">"](other)
    def __lt__(self, other):
        return self.methods["<"](other)
    def __ge__(self, other):
        return self.methods[">="](other)
    def __le__(self, other):
        return self.methods["<="](other)
    def __eq__(self, other):
        return self.methods["=="](other)
    def __ne__(self, other):
        return not self.methods["=="](other)

    def __repr__(self):
        return self.methods["to_s"]().s

    def to_s(self):
        return String("#<%s:0x%08x>" % (self.__name__, id(self)))

    def __str__(self):
        return self.methods["to_s"]().s

class Integer(Object):
    
    def initialize(self, *args):
        self.int = int(args[0])
        
        self.methods["+"] = lambda other: Integer(self.int + Integer(other).int)
        self.methods["-"] = lambda other: Integer(self.int - Integer(other).int)
        self.methods["*"] = lambda other: Integer(self.int * Integer(other).int)
        self.methods["/"] = lambda other: Integer(self.int / Integer(other).int)

        self.methods["=="] = lambda other: self.int == other.int
        self.methods["!="] = lambda other: self.int != other.int
        self.methods[">"]  = lambda other: self.int > other.int
        self.methods["<"]  = lambda other: self.int < other.int
        self.methods[">="] = lambda other: self.int >= other.int
        self.methods["<="] = lambda other: self.int <= other.int
        
        self.__name__ = "Integer"

    def to_s(self):
        return String(self.int)

    def __int__(self):
        return self.int

class String(Object):

    def initialize(self, *args):
        self.s = str(args[0])

        self.methods["=="] = lambda other: self.s == other.s
        self.methods["!="] = lambda other: self.s != other.s

    def to_s(self):
        return self
    
    def __repr__(self):
        return self.s

    def __str__(self):
        return self.s

class File(Object):

    def initialize(self, *args):
        self.file = args[0]

        self.methods["puts"] = self.puts
        self.methods["gets"] = self.gets
        self.methods["print"] = self.print
        self.methods["flush"] = self.flush

        self.__name__ = "File"

    def print(self, *args):
        self.file.write(" ".join(str(i) for i in args))

    def flush(self):
        self.file.flush()

    def puts(self, *args):
        self.file.write(" ".join(str(i) for i in args) + "\n")

    def gets(self):
        return String(self.file.readline()[:-1])

def ruby_aspython(ast, push_locals=False, pop_locals=False):
    if push_locals:
        code = "rlocals.push()\nresult = None\ntry:\n"
        indent = "  "
    else:
        code = "result = None\n"
        indent = ""

    for n in ast.children[0].children:
        code += indent + "rlocals[%r](%s)\n" % (n.token.value + "=", n.token.value)
    
    try:
        for i in ast.children[1:]:
            code += indent + ruby_compile_as_statement(i).replace("\n", "\n" + indent) + "\n"
    
    except:
        print("Code generated before crash:\n  " + code.replace("\n", "\n  "), file=sys.stderr)
        raise

    if pop_locals:
        code += "finally:\n"
        code += "  rlocals.pop()\n"
    
    return code

def ruby_compile_as_statement(ast):
    if isinstance(ast, rast.AssignGlobal):
        return "rglobals[%r] = %s" % (ast.token.value, ruby_compile_as_rvalue(ast.children[1]))

    elif isinstance(ast, rast.Call):
        return "result = " + ruby_compile_as_rvalue(ast)

    elif isinstance(ast, rast.Define):
        res = "def _method_definition(%s):\n" % (", ".join(i.token.value for i in ast.children[1].children[0].children))
        res += "  " + ruby_aspython(ast.children[1], push_locals=True, pop_locals=True).replace("\n", "\n  ")
        res += "\n  return result\n_method_definition.__name__ = %r\nrlocals[%r] = _method_definition\n" % (
            ast.children[0].token.value,
            ast.children[0].token.value
        )
        return res

    elif isinstance(ast, rast.If):
        if len(ast.children) == 3:
            return "if %s:\n  %s\nelse:\n  %s" % (
                ruby_compile_as_rvalue(ast.children[0]),
                ruby_aspython(ast.children[1]).replace("\n", "\n  "),
                ruby_aspython(ast.children[2]).replace("\n", "\n  ")
            )
        return "if %s:\n  %s" % (
            ruby_compile_as_rvalue(ast.children[0]),
            ruby_aspython(ast.children[1]).replace("\n", "\n  ")
        )
    
    else:
        raise NotImplementedError(type(ast).__name__)

def ruby_compile_as_lvalue(ast):
    if isinstance(ast, rast.Global):
        return "rglobals[%r]" % ast.token.value

    elif isinstance(ast, rast.Constant):
        return "rconsts[%r]" % ast.token.value

    elif isinstance(ast, rast.Name):
        return "rlocals[%r]" % ast.token.value
    
    else:
        raise NotImplementedError(type(ast).__name__)

def ruby_compile_as_rvalue(ast):
    if isinstance(ast, rast.Literal):
        return "LITERAL_TYPE_MAP[%r](%r)" % (type(ast.token.value).__name__, ast.token.value)

    elif isinstance(ast, rast.Name):
        return "rlocals[%r]" % ast.token.value

    elif isinstance(ast, rast.Global):
        return "rglobals[%r]" % ast.token.value

    elif isinstance(ast, rast.Constant):
        return "rconsts[%r]" % ast.token.value

    elif isinstance(ast, rast.Call):
        method_name = ast.children[1].token.value
        args = [ruby_compile_as_rvalue(i) for i in ast.children[2:]]
        args_repr = ", ".join("%s" % i for i in args)
        if ast.children[0] is None:
            return "rlocals[%r](%s)" % (method_name, args_repr)
        
        else:
            source_obj = ruby_compile_as_rvalue(ast.children[0])
            MAP = {
                "+":  "({0} + {2})",
                "-":  "({0} - {2})",
                "*":  "({0} * {2})",
                "/":  "({0} / {2})",
                "%":  "({0} % {2})",
                "&":  "({0} & {2})",
                "<<": "({0} << {2})",
                ">>": "({0} >> {2})",
                ">":  "({0} > {2})",
                "<":  "({0} < {2})",
                ">=": "({0} >= {2})",
                "<=": "({0} <= {2})",
                "==": "({0} == {2})",
                "!=": "({0} != {2})",
                
            }
            # print(args_repr)
            return MAP.get(method_name, "{0}.methods[{1}]({2})").format(source_obj, repr(method_name), args_repr)
    
    else:
        raise NotImplementedError(type(ast).__name__)

def ruby_exec(code, *, constants=None, rglobals=None, rlocals_init=None):
    constants = Constants(constants)
    rglobals = Globals(rglobals)
    eglobals = {
        "rlocals": Locals(),
        "rglobals": rglobals,
        "rconsts": constants,
        "__builtins__": {},
        "LITERAL_TYPE_MAP": {
            "int": Integer,
            "str": String
        }
    }
    eglobals["rlocals"].update(rlocals_init)
    locals = {}
    exec(code, eglobals, locals)
    return eglobals, locals

"""
ast = rast.Block(children=[
    rast.NameSequence(children=[]),

    rast.Define(children=[
        rast.Name(token=rlex.Name(value="bruh", line=-1, char=-1)),
        rast.Block(children=[
            rast.NameSequence(children=[
                rast.Name(token=rlex.Name(line=-1, char=-1, value="a")),
                rast.Name(token=rlex.Name(line=-1, char=-1, value="b")),
                rast.Name(token=rlex.Name(line=-1, char=-1, value="c"))
            ]),
            rast.Call(children=[
                rast.Call(children=[None, rast.Name(token=rlex.Name(value="a", line=-1, char=-1))]),
                rast.Name(token=rlex.Name(value="+", line=-1, char=-1)),
                rast.Call(children=[
                    rast.Call(children=[None, rast.Name(token=rlex.Name(value="b", line=-1, char=-1))]),
                    rast.Name(token=rlex.Name(value="+", line=-1, char=-1)),
                    rast.Call(children=[None, rast.Name(token=rlex.Name(value="c", line=-1, char=-1))])
                ])
            ])
        ])
    ]),
    
    rast.Call(children=[
        None,
        rast.Name(token=rlex.Name(value="x=", line=1, char=1)),
        rast.Literal(token=rlex.Literal(value=10, line=1, char=6))
    ]),
    rast.Call(children=[
        None,
        rast.Name(token=rlex.Name(value="y=", line=2, char=1)),
        rast.Literal(token=rlex.Literal(value=20, line=2, char=6))
    ]),

    rast.Call(children=[
        rast.Constant(token=rlex.Name(value="STDOUT", line=3, char=1)),
        rast.Name(token=rlex.Name(value="puts", line=3, char=8)),
        rast.Call(children=[
            None,
            rast.Name(token=rlex.Name(value="bruh", line=3, char=25)),
            rast.Literal(token=rlex.Literal(value=5, line=3, char=27)),
            rast.Literal(token=rlex.Literal(value=10, line=3, char=27)),
            rast.Literal(token=rlex.Literal(value=200, line=3, char=27))
        ])
    ]),
    
    rast.Call(children=[
        rast.Constant(token=rlex.Name(value="STDOUT", line=3, char=1)),
        rast.Name(token=rlex.Name(value="puts", line=3, char=8)),
        rast.Call(children=[
            rast.Call(children=[
                rast.Call(children=[None, rast.Name(token=rlex.Name(value="x", line=3, char=14))]),
                rast.Name(token=rlex.Name(value="+", line=3, char=17)),
                rast.Call(children=[
                    rast.Call(children=[None, rast.Name(token=rlex.Name(value="y", line=3, char=19))]),
                    rast.Name(token=rlex.Name(value="*", line=3, char=21)),
                    rast.Literal(token=rlex.Literal(value=10, line=3, char=23))
                ])
            ]),
            rast.Name(token=rlex.Name(value="-", line=3, char=25)),
            rast.Literal(token=rlex.Literal(value=6, line=3, char=27))
        ])
    ])
])
"""

##code = r"""
##print 'What\'s your name? '
##$stdout.flush
##name = gets
##
##if name == 'gwitr' then
##    puts 'Nice to meet you'
##end
##
##if name != 'gwitr' then
##    puts 'Ok'
##else
##    puts 'test'
##end
##"""

code = r"""
puts 1,2,
0
"""

toks = rlex.lex(code)
ast = rast.parse(toks)
code = ruby_aspython(ast)
print(code)
code = compile(code, "<compiled ruby code>", "exec")

try:
    STDIN  = File(sys.stdin)
    STDOUT = File(sys.stdout)
    env = ruby_exec(code, constants={
        "STDIN":  STDIN,
        "STDOUT": STDOUT
    }, rlocals_init={
        "puts": STDOUT.methods["puts"],
        "gets": STDIN.methods["gets"],
        "print": STDOUT.methods["print"]
    }, rglobals={
        "stdout": STDOUT,
        "stdin": STDIN
    })

except RubyErrors.StandardError as e:
    _, _, tb = sys.exc_info()
    stack = traceback.extract_tb(tb)
    i = 0
    while i < len(stack):
        if stack[i].filename.endswith(".py"):
            # i += 1
            stack.pop(i)
        else:
            i += 1
    print("%s:in `%s': %s (%s)" % (stack[-1].filename, stack[-1].name, str(e), type(e).__name__), file=sys.stderr)
    for s in stack[::-1]:
        print("        from %s:in `%s'" % (s.filename, s.name), file=sys.stderr)
    del tb, stack
