"""Bounded literal-only Lua reader. No Lua runtime, expressions or code execution."""
import re
from decimal import Decimal, InvalidOperation

MAX_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 1000000
IDENTIFIER = re.compile(rb"[A-Za-z_][A-Za-z_0-9]*")
NAMED_FIELD = re.compile(rb"([A-Za-z_][A-Za-z_0-9]*)\s*=")
NUMBER = re.compile(rb"-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


class FormatError(ValueError):
    pass


def strip_lua_prefix(raw: bytes) -> bytes:
    return raw.lstrip(b" \t\r\n").removeprefix(b"\xef\xbb\xbf").lstrip(b" \t\r\n")


class ParseBudget:
    """One allocation budget shared by Lua and every nested CBOR decode."""
    def __init__(self, max_nodes=None):
        self.remaining = MAX_NODES if max_nodes is None else max_nodes

    def consume(self, count=1):
        if count > self.remaining:
            raise FormatError("shared parsing complexity limit exceeded")
        self.remaining -= count

    def require_capacity(self, count):
        if count > self.remaining:
            raise FormatError("container exceeds remaining parsing budget")


class LuaReader:
    def __init__(self, raw: bytes, *, budget=None):
        if len(raw) > MAX_BYTES:
            raise FormatError("SavedVariables exceeds 16 MiB")
        self.raw = strip_lua_prefix(raw)
        self.pos = 0
        self.nodes = 0
        self.budget = budget if budget is not None else ParseBudget()

    def skip(self):
        while self.pos < len(self.raw):
            if self.raw[self.pos] in b" \t\r\n":
                self.pos += 1
            elif self.raw.startswith(b"--", self.pos):
                if self.raw.startswith(b"--[", self.pos):
                    raise FormatError("long Lua comments are unsupported")
                end = self.raw.find(b"\n", self.pos)
                self.pos = len(self.raw) if end < 0 else end + 1
            else:
                break

    def take(self, token: bytes):
        self.skip()
        if not self.raw.startswith(token, self.pos):
            raise FormatError(f"expected {token!r} at byte {self.pos}")
        self.pos += len(token)

    def identifier(self):
        self.skip()
        match = IDENTIFIER.match(self.raw, self.pos)
        if not match:
            raise FormatError(f"expected identifier at byte {self.pos}")
        self.pos += len(match[0])
        return match[0].decode("ascii")

    def string(self):
        quote = self.raw[self.pos]
        self.pos += 1
        result = bytearray()
        escapes = {ord("a"): 7, ord("b"): 8, ord("f"): 12, ord("n"): 10,
                   ord("r"): 13, ord("t"): 9, ord("v"): 11, 92: 92, 34: 34, 39: 39}
        while self.pos < len(self.raw):
            char = self.raw[self.pos]
            self.pos += 1
            if char == quote:
                return bytes(result)
            if char in (10, 13):
                raise FormatError("unescaped newline in Lua string")
            if char == 92:
                if self.pos == len(self.raw):
                    break
                char = self.raw[self.pos]
                self.pos += 1
                if 48 <= char <= 57:
                    digits = bytes([char])
                    for _ in range(2):
                        if self.pos < len(self.raw) and 48 <= self.raw[self.pos] <= 57:
                            digits += self.raw[self.pos:self.pos + 1]
                            self.pos += 1
                        else:
                            break
                    char = int(digits)
                    if char > 255:
                        raise FormatError("invalid decimal byte escape")
                elif char in (10, 13):
                    if char == 13 and self.raw[self.pos:self.pos + 1] == b"\n":
                        self.pos += 1
                    char = 10
                elif char in escapes:
                    char = escapes[char]
                else:
                    raise FormatError("unsupported Lua string escape")
            result.append(char)
        raise FormatError("unterminated Lua string")

    def value(self, depth=0):
        self.skip()
        self.budget.consume()
        self.nodes += 1
        if depth > MAX_DEPTH or self.nodes > MAX_NODES:
            raise FormatError("Lua complexity limit exceeded")
        if self.pos >= len(self.raw):
            raise FormatError("truncated Lua value")
        char = self.raw[self.pos]
        if char in (34, 39):
            return self.string()
        if char == 123:
            self.pos += 1
            result = {}
            array_index = 1
            while True:
                self.skip()
                if self.raw[self.pos:self.pos + 1] == b"}":
                    self.pos += 1
                    return result
                explicit_key = self.raw[self.pos:self.pos + 1] == b"["
                if explicit_key:
                    self.pos += 1
                    key = self.value(depth + 1)
                    self.take(b"]")
                    self.take(b"=")
                else:
                    named = NAMED_FIELD.match(self.raw, self.pos)
                    if named:
                        key = named[1]
                        self.pos += len(named[0])
                    else:
                        key = array_index
                        array_index += 1
                if type(key) not in (int, bytes) or key in result:
                    raise FormatError("invalid or duplicate Lua table key")
                # Implicit/identifier keys do not recurse through value().
                if not explicit_key:
                    self.budget.consume()
                result[key] = self.value(depth + 1)
                self.skip()
                if self.raw[self.pos:self.pos + 1] in (b",", b";"):
                    self.pos += 1
                elif self.raw[self.pos:self.pos + 1] != b"}":
                    raise FormatError("expected table separator")
        number = NUMBER.match(self.raw, self.pos)
        if number:
            if len(number[0]) > 32:
                raise FormatError("numeric literal too long")
            self.pos += len(number[0])
            try:
                return Decimal(number[0].decode("ascii")) if b"." in number[0] or b"e" in number[0].lower() else int(number[0])
            except InvalidOperation as error:
                raise FormatError("invalid decimal literal") from error
        identifier = self.identifier()
        if identifier in ("true", "false", "nil"):
            return {"true": True, "false": False, "nil": None}[identifier]
        raise FormatError("Lua expressions and executable code are forbidden")

    def parse(self):
        result = {}
        while True:
            self.skip()
            if self.pos == len(self.raw):
                return result
            name = self.identifier()
            self.budget.consume()  # Global variable key.
            if name in result:
                raise FormatError("duplicate SavedVariable assignment")
            self.take(b"=")
            result[name] = self.value()
            self.skip()
            if self.raw[self.pos:self.pos + 1] == b";":
                self.pos += 1


class CBORReader:
    """Subset emitted by the inspected LibCBOR serializer: definite values only.

    Both string types retain bytes (LibCBOR's UTF8 strings can contain binary).
    Tags, indefinite lengths, floats and extensions deliberately fail closed.
    """
    def __init__(self, raw: bytes, *, budget=None):
        if len(raw) > MAX_BYTES:
            raise FormatError("CBOR size limit exceeded")
        self.raw, self.pos, self.nodes = raw, 0, 0
        self.budget = budget if budget is not None else ParseBudget()

    def read(self, size):
        if self.pos + size > len(self.raw):
            raise FormatError("truncated CBOR")
        data = self.raw[self.pos:self.pos + size]
        self.pos += size
        return data

    def value(self, depth=0):
        self.budget.consume()
        self.nodes += 1
        if depth > MAX_DEPTH or self.nodes > MAX_NODES:
            raise FormatError("CBOR complexity limit exceeded")
        byte = self.read(1)[0]
        major, info = byte >> 5, byte & 31
        if major == 7:
            if info in (20, 21, 22):
                return {20: False, 21: True, 22: None}[info]
            raise FormatError("unsupported CBOR simple value or float")
        if info < 24:
            length = info
        elif info in (24, 25, 26, 27):
            length = int.from_bytes(self.read(1 << (info - 24)), "big")
        else:
            raise FormatError("indefinite or invalid CBOR length")
        if major == 0:
            return length
        if major == 1:
            return -1 - length
        if major in (2, 3):
            return self.read(length)
        if major in (4, 5):
            if length > MAX_NODES or length > len(self.raw) - self.pos:
                raise FormatError("CBOR container length limit exceeded")
            self.budget.require_capacity(length * (2 if major == 5 else 1))
            result = {}
            for index in range(length):
                key = index + 1 if major == 4 else self.value(depth + 1)
                if type(key) not in (int, bytes) or key in result:
                    raise FormatError("invalid or duplicate CBOR key")
                result[key] = self.value(depth + 1)
            return result
        raise FormatError("unsupported CBOR type")

    def parse(self):
        value = self.value()
        if self.pos != len(self.raw):
            raise FormatError("trailing CBOR bytes")
        return value
