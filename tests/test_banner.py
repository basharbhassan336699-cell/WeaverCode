"""
test_banner.py — شعار WeaverCode للطرفية (Hello / WEAVER CODE + الرسمة)
======================================================================
يتحقّق أنّ الشعار مُخزَّن ويُطبَع بلا تبعيات: نصّ غير فارغ، فيه اللون البرتقالي
(ANSI truecolor) وحروف كتلية، وأنّ show() لا يرمي.
"""

from core import banner


def test_render_nonempty():
    s = banner.render()
    assert isinstance(s, str) and len(s) > 500


def test_has_orange_and_blocks():
    s = banner.render()
    assert "\033[38;2;198;113;33m" in s   # WeaverCode orange
    assert "█" in s                   # █ block char (title)
    assert "▀" in s                   # ▀ half-block (artwork)


def test_show_is_safe(capsys):
    banner.show()
    out = capsys.readouterr().out
    assert len(out) > 100
