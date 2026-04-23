from llm_provider.provider import create_stub_provider, stub_capabilities


def test_stub_meets_all_capability_flags() -> None:
    p = create_stub_provider()
    assert p.capabilities() == stub_capabilities


def test_determinism() -> None:
    p = create_stub_provider()
    from llm_provider.provider import ChatMessage

    t = p.chat_complete((ChatMessage("user", "abc"),))
    assert t == "stub-out:3"
    e = p.embed("yz")
    assert e[0] == 2.0
