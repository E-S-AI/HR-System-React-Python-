"""
اختبارات وحدة لدوال معالجة النص العربي (بدون قاعدة بيانات).
"""
import pytest
from app.core.text import clean_text, to_ascii_digits, norm_search, normalize_gender
from app.services.excel_utils import norm_text, to_int, to_phone, to_national_id, to_text


# ───────────────────────── clean_text ─────────────────────────
class TestCleanText:
    def test_strips_zero_width(self):
        # حرف عرض-صفر U+200C بين الكلمتين
        assert clean_text("محمد‌علي") == "محمدعلي"

    def test_removes_tatweel(self):
        assert clean_text("مـحـمـد") == "محمد"

    def test_nbsp_to_space(self):
        result = clean_text("علي\xa0أحمد")
        assert result == "علي أحمد"

    def test_collapses_spaces(self):
        assert clean_text("محمد   علي") == "محمد علي"

    def test_none_returns_none(self):
        assert clean_text(None) is None

    def test_empty_returns_none(self):
        assert clean_text("") is None

    def test_blank_returns_none(self):
        assert clean_text("   ") is None

    def test_keeps_diacritics(self):
        # clean_text يحفظ التشكيل – فقط norm_search يحذفه
        assert "مُحَمَّد" == clean_text("مُحَمَّد")


# ───────────────────────── to_ascii_digits ────────────────────
class TestToAsciiDigits:
    def test_arabic_indic(self):
        assert to_ascii_digits("١٢٣") == "123"

    def test_persian(self):
        assert to_ascii_digits("۴۵۶") == "456"

    def test_mixed(self):
        assert to_ascii_digits("٠١abc٢") == "01abc2"

    def test_none_passthrough(self):
        assert to_ascii_digits(None) is None

    def test_already_ascii(self):
        assert to_ascii_digits("789") == "789"


# ───────────────────────── norm_search ────────────────────────
class TestNormSearch:
    def test_strips_diacritics(self):
        assert norm_search("مُحَمَّد") == norm_search("محمد")

    def test_unifies_alef(self):
        assert norm_search("أحمد") == norm_search("احمد")
        assert norm_search("إبراهيم") == norm_search("ابراهيم")
        assert norm_search("آمنة") == norm_search("امنة")

    def test_unifies_ya(self):
        assert norm_search("موسى") == norm_search("موسي")

    def test_unifies_ta_marbuta(self):
        assert norm_search("فاطمة") == norm_search("فاطمه")

    def test_lowercases_latin(self):
        assert norm_search("ABC") == "abc"

    def test_empty_string(self):
        assert norm_search("") == ""


# ───────────────────────── normalize_gender ───────────────────
class TestNormalizeGender:
    @pytest.mark.parametrize("inp", ["ذكر", "male", "m", "M"])
    def test_male(self, inp):
        assert normalize_gender(inp) == "ذكر"

    @pytest.mark.parametrize("inp", ["أنثى", "انثى", "أنثي", "female", "f", "F"])
    def test_female(self, inp):
        assert normalize_gender(inp) == "أنثى"

    @pytest.mark.parametrize("inp", ["other", "x", "جنس", "", None])
    def test_unknown(self, inp):
        assert normalize_gender(inp) is None


# ───────────────────────── excel_utils: norm_text ─────────────
class TestNormText:
    """norm_text in excel_utils now delegates to core.text.norm_search."""

    def test_basic_normalisation(self):
        assert norm_text("مُحَمَّد") == norm_text("محمد")

    def test_alef_variants(self):
        assert norm_text("أحمد") == norm_text("احمد")


# ───────────────────────── excel_utils: to_int ────────────────
class TestToInt:
    def test_arabic_indic_digits(self):
        assert to_int("١٢٣") == 123

    def test_persian_digits(self):
        assert to_int("۴۵") == 45

    def test_float_zero(self):
        assert to_int("5.0") == 5

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError):
            to_int("abc")

    def test_none_returns_none(self):
        assert to_int(None) is None


# ───────────────────────── excel_utils: to_phone ──────────────
class TestToPhone:
    def test_valid_local(self):
        assert to_phone("0931234567") == "0931234567"

    def test_missing_leading_zero(self):
        assert to_phone("931234567") == "0931234567"

    def test_arabic_digits(self):
        assert to_phone("٠٩٣١٢٣٤٥٦٧") == "0931234567"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            to_phone("abc")

    def test_none_returns_none(self):
        assert to_phone(None) is None


# ───────────────────────── excel_utils: to_national_id ────────
class TestToNationalId:
    def test_arabic_indic(self):
        assert to_national_id("١٢٣٤٥٦٧٨٩٠") == "1234567890"

    def test_non_digit_raises(self):
        with pytest.raises(ValueError):
            to_national_id("12abc")

    def test_none_returns_none(self):
        assert to_national_id(None) is None


# ───────────────────────── arabic_search helper ───────────────
class TestNameSearchConditions:
    """Tests that name_search_conditions splits words correctly (pure Python part)."""

    def test_single_word_one_token(self):
        from app.core.text import norm_search
        words = norm_search("محمد").split()
        assert len(words) == 1

    def test_two_words_two_tokens(self):
        from app.core.text import norm_search
        words = norm_search("محمد علي").split()
        assert len(words) == 2

    def test_alef_normalised_in_search(self):
        from app.core.text import norm_search
        # "أحمد" and "احمد" normalise to the same token
        assert norm_search("أحمد") == norm_search("احمد")

    def test_empty_string_no_tokens(self):
        from app.core.text import norm_search
        words = norm_search("").split()
        assert words == []

    def test_diacritics_stripped_before_split(self):
        from app.core.text import norm_search
        # three words with diacritics -> three tokens after strip
        words = norm_search("مُحَمَّد عَلِيّ أَحْمَد").split()
        assert len(words) == 3
