import pytest

from instrumentserver.helpers import (
    stringToArgsAndKwargs,
    flat_to_nested_dict,
    flatten_dict,
    is_flat_dict,
    nestedAttributeFromString,
    typeClassPath,
    objectClassPath,
)


# ---------------------------------------------------------------------------
# stringToArgsAndKwargs
# ---------------------------------------------------------------------------

def test_stringToArgsAndKwargs_empty_string():
    args, kwargs = stringToArgsAndKwargs("")
    assert args == []
    assert kwargs == {}


def test_stringToArgsAndKwargs_whitespace_only():
    args, kwargs = stringToArgsAndKwargs("   ")
    assert args == []
    assert kwargs == {}


@pytest.mark.parametrize("value, expected_args, expected_kwargs", [
    ("1, True", [1, True], {}),
    ("'hello'", ['hello'], {}),
    ("1, 2, 3", [1, 2, 3], {}),
    ("x=1, y=2", [], {'x': 1, 'y': 2}),
    ("1, abc=12.3", [1], {'abc': 12.3}),
])
def test_stringToArgsAndKwargs_valid(value, expected_args, expected_kwargs):
    args, kwargs = stringToArgsAndKwargs(value)
    assert args == expected_args
    assert kwargs == expected_kwargs


def test_stringToArgsAndKwargs_bad_kwarg_format():
    with pytest.raises(ValueError):
        stringToArgsAndKwargs("a=1=2")


def test_stringToArgsAndKwargs_unevaluable_arg():
    with pytest.raises(ValueError):
        stringToArgsAndKwargs("undefined_variable_xyz_abc")


def test_stringToArgsAndKwargs_unevaluable_kwarg_value():
    with pytest.raises(ValueError):
        stringToArgsAndKwargs("x=undefined_variable_xyz_abc")


# ---------------------------------------------------------------------------
# flat_to_nested_dict
# ---------------------------------------------------------------------------

def test_flat_to_nested_dict_already_flat():
    flat = {"a": 1, "b": 2}
    result = flat_to_nested_dict(flat)
    assert result == {"a": 1, "b": 2}


def test_flat_to_nested_dict_single_level():
    flat = {"a.b": 1, "a.c": 2}
    result = flat_to_nested_dict(flat)
    assert result == {"a": {"b": 1, "c": 2}}


def test_flat_to_nested_dict_multi_level():
    flat = {"a.b.c": 1, "a.b.d": 2, "x": 3}
    result = flat_to_nested_dict(flat)
    assert result == {"a": {"b": {"c": 1, "d": 2}}, "x": 3}


def test_flat_to_nested_dict_empty():
    assert flat_to_nested_dict({}) == {}


# ---------------------------------------------------------------------------
# flatten_dict
# ---------------------------------------------------------------------------

def test_flatten_dict_already_flat():
    d = {"a": 1, "b": 2}
    result = flatten_dict(d)
    assert result == {"a": 1, "b": 2}


def test_flatten_dict_nested():
    nested = {"a": {"b": 1}, "x": 3}
    result = flatten_dict(nested)
    assert result == {"a.b": 1, "x": 3}


def test_flatten_dict_custom_sep():
    nested = {"a": {"b": 1}}
    result = flatten_dict(nested, sep='/')
    assert result == {"a/b": 1}


def test_flatten_dict_round_trip():
    flat = {"a.b.c": 1, "a.b.d": 2, "x": 3}
    nested = flat_to_nested_dict(flat)
    back_to_flat = flatten_dict(nested)
    assert back_to_flat == flat


# ---------------------------------------------------------------------------
# is_flat_dict
# ---------------------------------------------------------------------------

def test_is_flat_dict_flat():
    assert is_flat_dict({"a": 1, "b": "hello"}) is True


def test_is_flat_dict_nested():
    assert is_flat_dict({"a": {"b": 1}}) is False


def test_is_flat_dict_mixed():
    assert is_flat_dict({"a": 1, "b": {"c": 2}}) is False


def test_is_flat_dict_empty():
    assert is_flat_dict({}) is True


# ---------------------------------------------------------------------------
# nestedAttributeFromString
# ---------------------------------------------------------------------------

class _Root:
    class _Child:
        value = 42

    scalar = 99


def test_nestedAttributeFromString_single_level():
    root = _Root()
    assert nestedAttributeFromString(root, 'scalar') == 99


def test_nestedAttributeFromString_two_levels():
    root = _Root()
    assert nestedAttributeFromString(root, '_Child.value') == 42


def test_nestedAttributeFromString_missing_raises():
    root = _Root()
    with pytest.raises(AttributeError):
        nestedAttributeFromString(root, 'nonexistent_attr')


def test_nestedAttributeFromString_nested_missing_raises():
    root = _Root()
    with pytest.raises(AttributeError):
        nestedAttributeFromString(root, '_Child.nonexistent')


# ---------------------------------------------------------------------------
# typeClassPath / objectClassPath
# ---------------------------------------------------------------------------

class _MyClass:
    pass


def test_typeClassPath_contains_class_name():
    path = typeClassPath(_MyClass)
    assert '_MyClass' in path
    assert '.' in path


def test_objectClassPath_contains_class_name():
    obj = _MyClass()
    path = objectClassPath(obj)
    assert '_MyClass' in path
    assert '.' in path


def test_typeClassPath_builtin():
    path = typeClassPath(int)
    assert 'int' in path


def test_objectClassPath_builtin_instance():
    path = objectClassPath(42)
    assert 'int' in path


def test_typeClassPath_and_objectClassPath_agree():
    """typeClassPath on the class and objectClassPath on an instance should match."""
    obj = _MyClass()
    assert typeClassPath(_MyClass) == objectClassPath(obj)