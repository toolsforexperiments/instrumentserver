"""Proxy methods for instrument methods whose signatures are not valid client-side source.

``inspect.signature`` writes a non-builtin class annotation with its full module
path (e.g. ``-> instrumentserver.testing.dummy_instruments.generic.SweepRequest``),
and defaults with their ``repr`` (e.g. ``<StatusFlag.EAV: 4>`` or
``<object object at 0x...>``). The client must still be able to build proxy
methods for these, and omitted arguments must fall back to the server's defaults.
"""

import inspect

import pytest

from instrumentserver.testing.dummy_instruments.generic import SweepRequest

ANNOTATED_INSTRUMENT = (
    "instrumentserver.testing.dummy_instruments.generic.AnnotatedMethodsInstrument"
)


def test_proxy_for_instrument_with_custom_class_annotations(cli):
    ins = cli.find_or_create_instrument("annotated", ANNOTATED_INSTRUMENT)

    assert "make_request" in ins.functions
    assert "request_span" in ins.functions


def test_calling_method_with_custom_return_annotation(cli):
    ins = cli.find_or_create_instrument("annotated", ANNOTATED_INSTRUMENT)

    request = ins.make_request(5e9, 1e6)

    assert isinstance(request, SweepRequest)
    assert request.center_hz == 5e9
    assert request.span_hz == 1e6


def test_calling_method_with_custom_parameter_annotation(cli):
    ins = cli.find_or_create_instrument("annotated", ANNOTATED_INSTRUMENT)

    span = ins.request_span(SweepRequest(center_hz=5e9, span_hz=2e6))

    assert span == 2e6


DEFAULTS_INSTRUMENT = (
    "instrumentserver.testing.dummy_instruments.generic.DefaultValuesInstrument"
)


def test_proxy_for_instrument_with_unrepresentable_defaults(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    for name in ["add", "flag_value", "is_default", "scaled"]:
        assert name in ins.functions


def test_proxy_method_keeps_parameter_names(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    assert list(inspect.signature(ins.add).parameters) == ["a", "b"]
    assert list(inspect.signature(ins.scaled).parameters) == ["x", "factor"]


def test_literal_default(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    assert ins.add(1) == 11
    assert ins.add(1, 2) == 3
    assert ins.add(1, b=5) == 6
    assert ins.add(a=1, b=2) == 3


def test_missing_required_argument_raises(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    with pytest.raises(Exception, match="missing 1 required positional argument: 'a'"):
        ins.add()


def test_enum_default(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    assert ins.flag_value() == 4
    assert ins.flag_value(16) == 16


def test_omitted_argument_uses_server_default(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    assert ins.is_default() is True
    assert ins.is_default(None) is False


def test_keyword_only_default(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    assert ins.scaled(3) == 3
    assert ins.scaled(3, factor=2) == 6


def test_skipping_a_middle_default(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    assert ins.combine(0) == "0,1,2"
    assert ins.combine(0, c=5) == "0,1,5"
    assert ins.combine(0, 3, 4) == "0,3,4"


def test_positional_only_default(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    assert ins.positional_only(0) == "0,1"
    assert ins.positional_only(0, 2) == "0,2"


def test_required_keyword_only(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    assert ins.required_keyword(0, k=3) == "0,3"


def _fail_if_server_called(*args, **kwargs):
    pytest.fail("call should have been rejected on the client")


def test_positional_only_rejects_keyword_on_client(cli, monkeypatch):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)
    monkeypatch.setattr(ins, "askServer", _fail_if_server_called)

    with pytest.raises(TypeError, match="positional-only"):
        ins.positional_only(0, b=2)


def test_keyword_only_rejects_positional_on_client(cli, monkeypatch):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)
    monkeypatch.setattr(ins, "askServer", _fail_if_server_called)

    with pytest.raises(TypeError, match="positional argument"):
        ins.required_keyword(0, 3)


def test_defaults_with_variadic_arguments(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    assert ins.gather(0) == "0,1,[],[]"
    assert ins.gather(0, 2, 3, 4) == "0,2,[3, 4],[]"
    assert ins.gather(0, x=9) == "0,1,[],[('x', 9)]"


def test_proxy_signature_shows_server_signature(cli):
    """The client GUI uses ``str(inspect.signature(fun))`` as placeholder and tooltip."""
    annotated = cli.find_or_create_instrument("annotated", ANNOTATED_INSTRUMENT)
    defaults = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    assert str(inspect.signature(defaults.add)) == "(a, b=10)"
    assert str(inspect.signature(defaults.flag_value)) == "(flag=<StatusFlag.EAV: 4>)"
    assert str(inspect.signature(annotated.make_request)) == (
        "(center_hz: float, span_hz: float)"
        " -> instrumentserver.testing.dummy_instruments.generic.SweepRequest"
    )


def test_proxy_docstring_starts_with_server_signature(cli):
    ins = cli.find_or_create_instrument("defaults", DEFAULTS_INSTRUMENT)

    assert ins.add.__doc__.startswith("add(a, b=10)\n\n")
    assert "Plain literal default." in ins.add.__doc__
