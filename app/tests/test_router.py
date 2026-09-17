from app.telegram_bot.router import register


class _FakeApp:
    def __init__(self):
        self.handlers = {}

    def add_handler(self, handler, group=0):
        self.handlers.setdefault(group, []).append(handler)


def _names(handlers):
    return [
        getattr(h.callback, "__name__", str(h.callback))
        for h in handlers
        if hasattr(h, "callback")
    ]


def test_good_bot_is_in_group_zero_before_catch_all():
    app = _FakeApp()
    register(app)

    group0 = _names(app.handlers[0])
    assert "handle_good_bot_reply" in group0
    assert group0.index("handle_good_bot_reply") < group0.index("handle_message")
    assert 1 not in app.handlers
    assert "handle_good_bot_reply" not in _names(app.handlers.get(1, []))


def test_message_logger_stays_in_group_two():
    app = _FakeApp()
    register(app)
    assert "log_message_to_db" in _names(app.handlers[2])


def test_user_memory_handler_registered_before_generic_mention():
    app = _FakeApp()
    register(app)
    group0 = _names(app.handlers[0])
    assert "handle_user_memory" in group0
    assert group0.index("handle_user_memory") < group0.index("handle_mention")
