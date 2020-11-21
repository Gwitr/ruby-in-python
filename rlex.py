from __future__ import annotations

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

def dataclass__repr__(self):
    args = ", ".join("%s=%r" % (k, getattr(self, k)) for k in self.__dataclass_fields__ if k not in self.REPR_IGNORE and getattr(self, k) is not None)
    return "%s(%s)" % (self.__class__.__name__, args)

@dataclass(init=False, repr=False)
class Token():

    __init__ = dataclass__init__
    __repr__ = dataclass__repr__

    REPR_IGNORE = ["line", "char"]
    
    value: Any
    line: int
    char: int

@dataclass(init=False, repr=False)
class Separator(Token):
    value: None = None

@dataclass(init=False, repr=False)
class Literal(Token):
    value: Union[int, str]

@dataclass(init=False, repr=False)
class Symbol(Token):
    value: str

@dataclass(init=False, repr=False)
class Operator(Token):
    value: str

@dataclass(init=False, repr=False)
class Name(Token):
    value: str

@dataclass(init=False, repr=False)
class GlobalName(Token):
    value: str

@dataclass(init=False, repr=False)
class Keyword(Token):
    value: str

IDENT_START_A = "QWERTYUIOPASDFGHJKLZXCVBNMqwertyuiopasdfghjklzxcvbnm_"
IDENT_A = "qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM_0123456789"
WHITESPACE_A = " \t\r"

def lex(code):
    toks = []
    i = 0
    li = 0
    line = 1
    char = 1
    while i < len(code):
        if code[i] == "\n":
            toks.append(Separator(line=line, char=char))
            char = 1
            line += 1
            i += 1
            continue
        
        chars_left = len(code) - i
        # print(repr(code[i]), chars_left)
        if chars_left >= 2:
            if code[i:i+2] in {"==", "!=", "**"}:
                toks.append(Operator(value=code[i:i+2], line=line, char=char))
                i += 2
                char += i - li
                li = i
                continue
        
        if chars_left >= 1:
            # print("in")
            if code[i:i+1] in {"+", "-", "*", "/", "(", ")", "=", "<", ">", ".", ","}:
                # print("in2", code[i:i+1])
                toks.append(Operator(value=code[i:i+1], line=line, char=char))
                # print(toks)
                i += 1
                char += i - li
                li = i
                continue

        if code[i] in IDENT_START_A:
            x = code[i]
            i += 1
            while i < len(code) and code[i] in IDENT_A:
                x += code[i]
                i += 1
            
            if x in {"if", "then", "else", "end", "while", "do", "def"}:
                toks.append(Keyword(value=x, line=line, char=char))
            else:
                toks.append(Name(value=x, line=line, char=char))

        elif code[i] == "'":
            i += 1
            x = ""
            while i < len(code) and code[i] != "'":
                if code[i] == "\\":
                    i += 1
                x += code[i]
                i += 1
            toks.append(Literal(value=x, line=line, char=char))
            i += 1

        elif code[i] == "$":
            x = ""
            i += 1
            while i < len(code) and code[i] in IDENT_A:
                x += code[i]
                i += 1
            
            toks.append(GlobalName(value=x, line=line, char=char))

        elif code[i] in WHITESPACE_A:
            i += 1

        elif code[i] in "0123456789.":
            x = ""
            while i < len(code) and code[i] in "0123456789.":
                x += code[i]
                i += 1
            toks.append(Literal(value=float(x) if '.' in x else int(x), line=line, char=char))

        else:
            raise ValueError("(line: %d, char: %d) Unexpected character '%c'" % (line, char, code[i]))
        
        char += i - li
        li = i

    return toks

if __name__ == "__main__":
    code = r"""
print 'What\'s your name? '
$stdout.flush
name = gets

if name == 'gwitr' then
    puts 'Nice to meet you'
end

if name == 'gwitr' then
    puts 'Ok'
else
    puts 'test'
end
"""
    toks = lex(code)
    print(toks)
