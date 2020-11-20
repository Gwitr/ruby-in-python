from __future__ import annotations

import rlex
import dataclasses
from typing import *
from dataclasses import dataclass

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
class Define(Node):
    # 1st child: Name
    # 2nd child: Block
    token: None = None
    children: List[rast.Node]

# Pain

class ElseSignal(Exception):

    def __init__(self, v):
        self.v = v

    def __str__(self):
        return "else signal not caught ????"

def parse(toks):
    return _tok2ast(toks.copy())
    
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
        
        e = expr2ast(t)
        
        if e is not None:
            exprs.append(e)
            # print(exprs[-1])
    
    return Block(children=[NameSequence(children=[]), *exprs])

def expr2ast(toks, ignore_sy_operator=False):
    if len(toks) == 0:
        return None
    
    tok = toks.pop(0)
    
    if isinstance(tok, rlex.GlobalName):
        ntok = toks.pop(0)
        
        if isinstance(ntok, rlex.Operator):
            if ntok.value == "=":
                return AssignGlobal(token=ntok, children=[Global(token=tok), expr2ast(toks)])

            elif ntok.value == ".":
                l = dot(tok, toks)
                res = Global(token=tok)
                for i in l[:0:-1]:
                    res = Call(children=[res, i])
                res.children += exprseq2astseq(toks)
                return res
            
            else:
                raise NotImplementedError("GlobalName, Operator %s" % ntok.value)
        
        else:
            toks.insert(0, ntok)
            return Global(token=tok)

    elif isinstance(tok, rlex.Keyword):
        if tok.value == "if":
            cond = expr2ast(toks)
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
            
        else:
            raise NotImplementedError("Keyword %s" % tok.value)

    elif isinstance(tok, rlex.Separator):
        return None

    elif isinstance(tok, rlex.Name):
        # [name] [equal sign] [expr]
        # [name] [operator] ...
        # [name] [dot] [name] [[dot] [name] [[dot] [name] [...]]]
        # [name] [expr] [, [expr] [, [expr] [...]]]
        ntok = toks.pop(0)
        if isinstance(ntok, rlex.Operator):
            if ntok.value == "=":
                return Call(children=[None, Name(token=rlex.Name(value=tok.value + "=", line=tok.line, char=tok.char)), expr2ast(toks)])

            elif ntok.value == ".":
                l = dot(tok, toks)
                res = Call(children=[None, Name(token=tok)])
                for i in l[:0:-1]:
                    res = Call(children=[res, i])
                res.children += exprseq2astseq(toks)
                return res
            
            else:
                toks.insert(0, ntok)
                if ignore_sy_operator or ntok.value == ",":
                    return Call(children=[None, Name(token=tok), *exprseq2astseq(toks)])
                else:
                    toks.insert(0, tok)
                    return shunting_yard(toks)

        else:
            toks.insert(0, ntok)
            return Call(children=[None, Name(token=tok), *exprseq2astseq(toks)])

    elif isinstance(tok, rlex.Literal):
        if len(toks) > 0:
            if isinstance(toks[0], rlex.Operator):
                if ignore_sy_operator or toks[0].value == ",":
                    return Literal(token=tok)
                else:
                    toks.insert(0, tok)
                    return shunting_yard(toks)
            
        return Literal(token=tok)
    
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
def shunting_yard(toks):

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
            if toks[0].value == ",":
                raise Break
            return toks.pop(0).value
        
        e = expr2ast(toks, ignore_sy_operator=True)
        if e is None:
            raise Break
        return e
    
    stack = [""]
    rlist = []
    try:
        while 1:
            v = vnext()
            if isinstance(v, str):
                while SY_PRECEDENCE[v] <= SY_PRECEDENCE[stack[-1]]:
                    rlist.append(stack.pop())
                stack.append(v)
            else:
                rlist.append(v)
    except Break:
        pass
    rlist += stack[1:]

    stack = []
    for v in rlist:
        if isinstance(v, str):
            y = stack.pop()
            x = stack.pop()
            stack.append(Call(children=[x, Name(token=rlex.Name(value=v, line=-1, char=-1)), y]))
            
        else:
            stack.append(v)
    
    return stack[-1]

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
            else:
                raise ValueError("Invalid token sequence: %s, %s, %s" % (tok, ntok, ", ".join(i for i in ntok2l)))
        else:
            toks.insert(0, ntok2l[-1])
            break
    return l

def exprseq2astseq(toks):
    if isinstance(toks[0], rlex.Separator):
        return []

    if isinstance(toks[0], rlex.Keyword):
        return []
    
    if isinstance(toks[0], rlex.Operator):
        return []
    
    r = [expr2ast(toks)]
    while len(toks) > 0:
        # print(r, toks[0])
        if isinstance(toks[0], rlex.Separator):
            break

        if isinstance(toks[0], rlex.Keyword):
            break
        
        if not (isinstance(toks[0], rlex.Operator) and toks[0].value == ","):
            break
        toks.pop(0)

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

        print("b", toks)
        e = expr2ast(toks)
        print("c", toks)
        if e is not None:
            r.append(e)
    return r

if __name__ == "__main__":
    # puts 1 + 2 - 3 * 4 * 5 + 6 - 7, 8 - 9 + 10 * 11 * 12 - 13 + 17
    toks = [
        rlex.Name(value="puts", line=-1, char=-1),
        rlex.Literal(value=1, line=-1, char=-1),
        rlex.Operator(value="+", line=-1, char=-1),
        rlex.Literal(value=2, line=-1, char=-1),
        rlex.Operator(value="-", line=-1, char=-1),
        rlex.Literal(value=3, line=-1, char=-1),
        rlex.Operator(value="*", line=-1, char=-1),
        rlex.Literal(value=1, line=-1, char=-1),
        rlex.Operator(value="*", line=-1, char=-1),
        rlex.Literal(value=1, line=-1, char=-1),
        rlex.Operator(value="+", line=-1, char=-1),
        rlex.Literal(value=1, line=-1, char=-1),
        rlex.Operator(value="-", line=-1, char=-1),
        rlex.Literal(value=1, line=-1, char=-1),
        rlex.Operator(value=",", line=-1, char=-1),
        rlex.Literal(value=8, line=-1, char=-1),
        rlex.Operator(value="-", line=-1, char=-1),
        rlex.Literal(value=9, line=-1, char=-1),
        rlex.Operator(value="+", line=-1, char=-1),
        rlex.Literal(value=10, line=-1, char=-1),
        rlex.Operator(value="*", line=-1, char=-1),
        rlex.Literal(value=11, line=-1, char=-1),
        rlex.Operator(value="*", line=-1, char=-1),
        rlex.Literal(value=12, line=-1, char=-1),
        rlex.Operator(value="-", line=-1, char=-1),
        rlex.Literal(value=13, line=-1, char=-1),
        rlex.Operator(value="+", line=-1, char=-1),
        rlex.Literal(value=14, line=-1, char=-1)
    ]
    
    ast = parse(toks)
    print(ast)
