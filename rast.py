from __future__ import annotations

import rlex
import traceback
import dataclasses
from typing import *
from dataclasses import dataclass

# TODO: Implement "f (f a1), a2" type expression support

AST_DEBUG = False

def dataclass__init__(self, *args, **kwargs):
    for k in self.__dataclass_fields__:
        v = kwargs.get(k, self.__dataclass_fields__[k].default)
        if isinstance(v, dataclasses._MISSING_TYPE):
            vf = self.__dataclass_fields__[k].default_factory
            if isinstance(vf, dataclasses._MISSING_TYPE):
                raise ValueError("Missing keyword argument '%s'" % k)
            v = vf()
        setattr(self, k, v)

@dataclass(init=False)
class Node():

    __init__ = dataclass__init__
    
    children: List[Node]
    token: rlex.Token
    
@dataclass(init=False)
class Call(Node):
    # 1st argument: The object (none for local binding)
    # 2nd argument: The name (if None then 1st argument called directly)
    # The rest: The function arguments
    token: None = None

@dataclass(init=False)
class AssignGlobal(Node):
    token: rlex.GlobalName     # The GlobalName to assign to
    children: List[rast.Node]

@dataclass(init=False)
class Name(Node):
    token: rlex.Name
    children: None = None

@dataclass(init=False)
class Constant(Node):
    token: rlex.Name
    children: None = None

@dataclass(init=False)
class Global(Node):
    token: rlex.GlobalName
    children: None = None

@dataclass(init=False)
class Literal(Node):
    token: rlex.Literal
    children: None = None

@dataclass(init=False)
class Symbol(Node):
    token: rlex.Symbol
    children: None = None

@dataclass(init=False)
class NameSequence(Node):
    token: None = None

@dataclass(init=False)
class Block(Node):
    # 1st child: NameSequence
    # All next children: The instructions inside of the block
    token: None = None

@dataclass(init=False)
class If(Node):
    # 1st child: The condition
    # 2nd child: "then ... end/else" block
    # 3rd child (optional): "else ... end" block
    token: None = None
    children: List[rast.Node]

@dataclass(init=False)
class While(Node):
    # 1st child: The condition
    # 2nd child: "do ... end" block
    token: None = None
    children: List[rast.Node]

@dataclass(init=False)
class Define(Node):
    # 1st child: Name
    # 2nd child: Block
    token: None = None
    children: List[rast.Node]

# Pain

if AST_DEBUG:
    def lrepr(x):
        r = repr(x)
        if len(r) > 50:
            return r[:97] + "..."
        return r

    def lstr(x):
        r = str(x)
        if len(r) > 50:
            return r[:97] + "..."
        return r
    
    def dbg(f):
        def wrap(*args, **kwargs):
            nonlocal f
            if len(kwargs) > 0:
                print(
                    "ENTER %s(%s,"  % (f.__name__, ", ".join(lrepr(i) for i in args)), "%s)" % (", ".join("%s=%s"%(i,lrepr(kwargs[i])) for i in kwargs))
                )
            else:
                print(
                    "ENTER %s(%s)" % (f.__name__, ", ".join(lrepr(i) for i in args)),
                )
            dbg.counter += 1
            r = f(*args, **kwargs)
            dbg.counter -= 1
            return r
        return wrap
    dbg.counter = 0

    def dbg_print(*args, sep=" ", end="\n"):
        if dbg_print.last_end == "\n":
            try:
                __builtins__["print"](dbg.counter * "  ", end="")
            except TypeError:
                __builtins__.print(dbg.counter * "  ", end="")
        dbg_print.last_end = end
        try:
            __builtins__["print"](*[lstr(i) for i in args], sep=sep, end=end)
        except TypeError:
            __builtins__.print(*[lstr(i) for i in args], sep=sep, end=end)
    dbg_print.last_end = "\n"

    print = dbg_print
else:
    def dbg(f):
        return f

class ElseSignal(Exception):

    def __init__(self, v):
        self.v = v

    def __str__(self):
        return "else signal not caught ????"

@dbg
def parse(toks):
    return _tok2ast(toks.copy())

@dbg    
def _tok2ast(t):
    exprs = []
    while len(t) > 0:
        if isinstance(t[0], rlex.Keyword):
            if t[0].value == "end":
                t.pop(0)
                break
            
            elif t[0].value == "else":
                t.pop(0)
                raise ElseSignal(Block(children=[NameSequence(children=[]), *exprs]))

        elif isinstance(t[0], rlex.Operator):
            if t[0].value == ")":
                t.pop(0)
                break
        
        e = expr2ast(t, exprs=exprs)
        
        if e is not None:
            exprs.append(e)
            # print(exprs[-1])
    
    return Block(children=[NameSequence(children=[]), *exprs])

@dbg
def expr2ast(toks, exprs, ignore_sy_operator=False):
    if len(toks) == 0:
        return None
    
    tok = toks.pop(0)
    
    if isinstance(tok, rlex.GlobalName):
        ntok = toks.pop(0)
        
        if isinstance(ntok, rlex.Operator):
            if ntok.value == "=":
                return AssignGlobal(token=ntok, children=[Global(token=tok), expr2ast(toks, exprs=exprs)])

            elif ntok.value == ".":
                l = dot(tok, toks)
                res = Global(token=tok)
                for i in l[:0:-1]:
                    res = Call(children=[res, i])
                res.children += exprseq2astseq(toks, exprs=exprs)
                return res
            
            else:
                raise NotImplementedError("GlobalName, Operator %s" % ntok.value)
        
        else:
            toks.insert(0, ntok)
            return Global(token=tok)

    elif isinstance(tok, rlex.Keyword):
        if tok.value == "if":
            cond = expr2ast(toks, exprs=exprs)
            # print(toks[0])
            if (not isinstance(toks[0], rlex.Keyword)) or (not toks[0].value == "then"):
                raise ValueError("Expected Keyword then, got %s %s" % (
                    type(toks[0]).__name__, toks[0].value
                ))
            toks.pop(0)
            try:
                block = _tok2ast(toks)
            except ElseSignal as e:
                block = e.v
                try:
                    eblock = _tok2ast(toks)
                    return If(children=[cond, block, eblock])
                except ElseSignal:
                    raise ValueError("If block cannot have more than one else block") from None
            return If(children=[cond, block])

        elif tok.value == "while":
            cond = expr2ast(toks, exprs=exprs)
            # print(toks[0])
            if (not isinstance(toks[0], rlex.Keyword)) or (not toks[0].value == "do"):
                raise ValueError("Expected Keyword then, got %s %s" % (
                    type(toks[0]).__name__, toks[0].value
                ))
            toks.pop(0)
            try:
                block = _tok2ast(toks)
            except ElseSignal as e:
                raise ValueError("While block cannot have an else block") from None
            return While(children=[cond, block])

        elif tok.value == "def":
            ntok = toks.pop(0)
            if not isinstance(ntok, rlex.Name):
                raise ValueError("Expected Name, got %s %s" % (type(ntok).__name__, ntok.value))

            if len(toks) == 0:
                raise ValueError("Expected Operator ( or Separator, not EOF") from None
            
            if isinstance(toks[0], rlex.Operator) and toks[0].value == "(":
                argnames = exprseq2astseq(toks, exprs=exprs)
                # ntok2_1 = toks.pop(0)
                # if not (isinstance(ntok2_1, rlex.Operator) and ntok2_1.value == ")"):
                #     raise ValueError("Expected Operator ) or Separator, not EOF")

            elif isinstance(toks[0], rlex.Separator):
                argnames = []
            
            else:
                raise ValueError("Expected Operator ( or Separator, not %s %s" % (type(ntok2).__name__, ntok2.value))
            
            for i in argnames:
                if not isinstance(i, Call):
                    raise ValueError("Argument name list must only contain Name tokens")
                if i.children[0] is not None:
                    raise ValueError("Argument name list must only contain Name tokens")
                if len(i.children) != 2:
                    raise ValueError("Argument name list must only contain Name tokens")
                if not isinstance(i.children[1], Name):
                    raise ValueError("Argument name list must only contain Name tokens")
            
            args = NameSequence(children=[i.children[1] for i in argnames])
            return Define(children=[Name(token=ntok), Block(children=[args] + _tok2ast(toks).children[1:])])
        
        else:
            raise NotImplementedError("Keyword %s" % tok.value)

    elif isinstance(tok, rlex.Separator):
        return None

    elif isinstance(tok, rlex.Name):
        try:
            ntok = toks.pop(0)
        except IndexError:
            if tok.value[0] in "QWERTYUIOPASDFGHJKLZXCVBNM":
                # Constant name
                return Constant(token=tok)
            return Call(children=[None, Name(token=tok)])
        
        if isinstance(ntok, rlex.Operator):
            if ntok.value == "=":
                if tok.value[0] in "QWERTYUIOPASDFGHJKLZXCVBNM":
                    return Call(children=[None, Constant(token=rlex.Name(value=tok.value + "=", line=tok.line, char=tok.char)), expr2ast(toks, exprs=exprs)])
                return Call(children=[None, Name(token=rlex.Name(value=tok.value + "=", line=tok.line, char=tok.char)), expr2ast(toks, exprs=exprs)])

            elif ntok.value == ".":
                l = dot(tok, toks)
                if tok.value[0] in "QWERTYUIOPASDFGHJKLZXCVBNM":
                    res = Constant(token=tok)
                else:
                    res = Call(children=[None, Name(token=tok)])
                for i in l[:0:-1]:
                    res = Call(children=[res, i])
                if isinstance(toks[0], rlex.Operator) and toks[0].value == "(":
                    toks.pop(0)
                    res.children += exprseq2astseq(toks, exprs=exprs, st_paren=True)
                else:
                    res.children += exprseq2astseq(toks, exprs=exprs)
                return res
            
            else:
                toks.insert(0, ntok)
                if ignore_sy_operator or ntok.value in {",", "(", ")"}:
                    if tok.value[0] in "QWERTYUIOPASDFGHJKLZXCVBNM":
                        # Constant name
                        return Constant(token=tok)
                    if isinstance(toks[0], rlex.Operator) and toks[0].value == "(":
                        toks.pop(0)
                        return Call(children=[None, Name(token=tok), *exprseq2astseq(toks, exprs=exprs, st_paren=True)])
                    return Call(children=[None, Name(token=tok), *exprseq2astseq(toks, exprs=exprs)])
                else:
                    toks.insert(0, tok)
                    return shunting_yard(toks, exprs=exprs)

        else:
            toks.insert(0, ntok)
            if tok.value[0] in "QWERTYUIOPASDFGHJKLZXCVBNM":
                # Constant name
                return Constant(token=tok)
            if isinstance(toks[0], rlex.Operator) and toks[0].value == "(":
                toks.pop(0)
                return Call(children=[None, Name(token=tok), *exprseq2astseq(toks, exprs=exprs, st_paren=True)])
            return Call(children=[None, Name(token=tok), *exprseq2astseq(toks, exprs=exprs)])

    elif isinstance(tok, rlex.Literal):
        if len(toks) > 0:
            if isinstance(toks[0], rlex.Operator):
                if ignore_sy_operator or toks[0].value in {",", "(", ")"}:
                    return Literal(token=tok)
                else:
                    toks.insert(0, tok)
                    return shunting_yard(toks, exprs=exprs)
            
        return Literal(token=tok)

    elif isinstance(tok, rlex.Operator) and tok.value == ",":
        raise ValueError("Operator , is invalid here.")

    elif isinstance(tok, rlex.Operator) and tok.value == "(":
        toks.insert(0, tok)
        t = exprseq2astseq(toks, exprs=exprs)
        if len(t) > 1:
            raise ValueError("More than 1 expression in parenthesis")
        if len(t) < 1:
            raise ValueError("Empty parenthesis")
        return t[0]

    elif isinstance(tok, rlex.Operator):
        p = exprs.pop()
        toks.insert(0, tok)
        s = shunting_yard(toks, init=[p], exprs=exprs)
        # print("shunting_yard", s)
        return s
    
    raise NotImplementedError(type(tok).__name__)

SY_PRECEDENCE = {
    "**": 5,
    "*": 4,
    "/": 4,
    "-": 3,
    "+": 3,
    "==": 2,
    "!=": 2,
    "<": 2,
    ">": 2,
    "<=>": 2,
    "": float("-inf")
}
@dbg
def shunting_yard(toks, exprs, init=[]):

    # TODO: Add input validation
    # TODO: Don't lose line / char info on operators

    class Break(Exception):
        pass

    def vnext():
        nonlocal toks

        if len(toks) == 0:
            raise Break

        if isinstance(toks[0], (rlex.Keyword, rlex.Separator)):
            raise Break
        
        if isinstance(toks[0], rlex.Operator):
            if toks[0].value == ")":
                toks.pop(0)
                raise Break

            if toks[0].value == "(":
                e = expr2ast(toks, exprs=exprs)
                if e is None:
                    raise Break
                return e
            
            if toks[0].value == ",":
                raise Break
            return toks.pop(0).value
        
        e = expr2ast(toks, ignore_sy_operator=True, exprs=exprs)
        if e is None:
            raise Break
        return e
    
    stack = [""]
    rlist = init.copy()
    try:
        while 1:
            if AST_DEBUG:
                print("Getting vnext")
            v = vnext()
            if AST_DEBUG:
                print("vnext is", v)
            if isinstance(v, str):
                while SY_PRECEDENCE[v] <= SY_PRECEDENCE[stack[-1]]:
                    rlist.append(stack.pop())
                stack.append(v)
            else:
                rlist.append(v)
    
    except Break:
        if AST_DEBUG:
            print("Broke out", toks, rlist, stack)
    rlist += reversed(stack[1:])

    stack = []
    for v in rlist:
        if isinstance(v, str):
            y = stack.pop()
            x = stack.pop()
            stack.append(Call(children=[x, Name(token=rlex.Name(value=v, line=-1, char=-1)), y]))
            
        else:
            stack.append(v)
    
    return stack[-1]

@dbg
def dot(tok, toks):
    l = [tok]
    ntok2l = [toks.pop(0)]
    while 1:
        if not isinstance(ntok2l[-1], rlex.Name):
            raise ValueError("Invalid token sequence: %s, %s, %s" % (tok, ntok, ", ".join(i for i in ntok2l)))
        l.append(Name(token=ntok2l[-1]))

        ntok2l.append(toks.pop(0))
        if isinstance(ntok2l[-1], rlex.Operator):
            if ntok2l[-1].value == ".":
                ntok2l.append(toks.pop(0))
            elif ntok2l[-1].value == "(":
                toks.insert(0, ntok2l[-1])
                break
            else:
                raise ValueError("Invalid token sequence: %s, Operator ., %s" % (tok, ", ".join("%s %s" % (type(i).__name__, i.value) for i in ntok2l)))
        else:
            toks.insert(0, ntok2l[-1])
            break
    return l

@dbg
def exprseq2astseq(toks, exprs, st_paren=False):
    if AST_DEBUG:
        print(st_paren)
    if isinstance(toks[0], rlex.Operator) and toks[0].value == "(":
        toks.pop(0)
        r = exprseq2astseq(toks, exprs, st_paren=True)
    else:
        if isinstance(toks[0], rlex.Separator):
            return []

        if isinstance(toks[0], rlex.Keyword):
            return []
        
        if isinstance(toks[0], rlex.Operator) and toks[0].value != "(":
            return []

        r = [expr2ast(toks, exprs=exprs)]
    
    while len(toks) > 0:
        #print("ibp", toks[0])
        #print("c1")
        if isinstance(toks[0], rlex.Separator):
            break

        #print("c2")
        if isinstance(toks[0], rlex.Keyword):
            break

        #print("c3")
        if isinstance(toks[0], rlex.Operator) and toks[0].value == ")":
            if st_paren:
                toks.pop(0)
            break

        #print("c4")
        if isinstance(toks[0], rlex.Operator) and toks[0].value == "(":
            toks.pop(0)
            r += exprseq2astseq(toks, exprs)

        #print("c5")
        if isinstance(toks[0], rlex.Operator) and toks[0].value != ",":
            s = shunting_yard(toks, init=[r.pop()], exprs=exprs)
            r.append(s)
            continue

        #print("c6")
        if not (isinstance(toks[0], rlex.Operator) and toks[0].value == ","):
            break

        #print("c7")
        toks.pop(0)

        #print("c8", toks[0])
        if isinstance(toks[0], rlex.Operator) and toks[0].value == "(":
            toks.pop(0)
            r += exprseq2astseq(toks, exprs, st_paren=True)
            ntok = toks.pop(0)
            if isinstance(ntok, rlex.Operator) and ntok.value == ")":
                if st_paren:
                    toks.pop(0)
                break

            if isinstance(ntok, rlex.Separator):
                if st_paren:
                    raise ValueError("Unexpected EOL")
                break
            
            if not (isinstance(ntok, rlex.Operator) and ntok.value == ","):
                raise ValueError("Expected Operator , - got %s %s" % (type(ntok).__name__, ntok.value))

        #print("c9")
        f = False
        while isinstance(toks[0], rlex.Separator):
            # print("is separator")
            toks.pop(0)
            if len(toks) == 0:
                f = True
                break
        if f:
            break
        # print("a", r, toks[0])

        # print("b", toks)
        e = expr2ast(toks, exprs=exprs)
        # print("c", toks)
        if e is not None:
            r.append(e)
    return r

if __name__ == "__main__":
    # puts 1 + 2 - 3 * 4 * 5 + 6 - 7, 8 - 9 + 10 * 11 * 12 - 13 + 17
    toks = [
        rlex.Keyword(value="while", line=-1, char=-1),
        rlex.Literal(value=1, line=-1, char=-1),
        rlex.Keyword(value="do", line=-1, char=-1),
        rlex.Separator(line=-1, char=-1),
        rlex.Name(value="puts", line=-1, char=-1),
        rlex.Literal(value="bruh", line=-1, char=-1),
        rlex.Keyword(value="end", line=-1, char=-1)
    ]
    
    ast = parse(toks)
    print(ast)
