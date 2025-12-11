
from app.media.ytdlp_profiles import (
    PROFILES,
    get_default_profile,
    get_fallback_profile,
    get_shorts_profile,
    get_telegram_optimization_profile,
)


def test_profiles_dict_contains_all_profiles():
    """Test that PROFILES dict contains all expected profile names."""
    expected_profiles = {"default", "shorts", "fallback", "telegram"}
    assert set(PROFILES.keys()) == expected_profiles


def test_default_profile_returns_dict():
    """Test that default profile returns a dictionary."""
    profile = get_default_profile()
    assert isinstance(profile, dict)
    assert "format" in profile
    assert "postprocessors" in profile


def test_shorts_profile_returns_dict():
    """Test that shorts profile returns a dictionary."""
    profile = get_shorts_profile()
    assert isinstance(profile, dict)
    assert "format" in profile
    assert "postprocessors" in profile


def test_fallback_profile_returns_dict():
    """Test that fallback profile returns a dictionary."""
    profile = get_fallback_profile()
    assert isinstance(profile, dict)
    assert "format" in profile
    assert "outtmpl" in profile


def test_telegram_profile_returns_dict():
    """Test that telegram optimization profile returns a dictionary."""
    profile = get_telegram_optimization_profile()
    assert isinstance(profile, dict)
    assert "format" in profile
    assert "postprocessors" in profile


def test_all_profiles_have_base_settings():
    """Test that all profiles include base settings."""
    base_keys = {"quiet", "no_warnings", "noplaylist", "outtmpl", "merge_output_format"}

    for profile_name, profile_func in PROFILES.items():
        profile = profile_func()
        for key in base_keys:
            assert key in profile, f"Profile '{profile_name}' missing base key '{key}'"


def test_profiles_dict_functions_are_callable():
    """Test that all PROFILES entries are callable."""
    for profile_name, profile_func in PROFILES.items():
        assert callable(profile_func), f"Profile '{profile_name}' is not callable"


def test_calling_profile_functions_returns_new_dict():
    """Test that calling profile functions returns new dict instances."""
    profile1 = get_default_profile()
    profile2 = get_default_profile()

    # Should be separate instances
    assert profile1 is not profile2

    # But should have the same content
    assert profile1 == profile2


def test_profiles_have_mp4_output():
    """Test that all profiles output MP4 format."""
    for profile_name, profile_func in PROFILES.items():
        profile = profile_func()
        assert profile.get("merge_output_format") == "mp4", (
            f"Profile '{profile_name}' does not output MP4"
        )


def test_fallback_profile_has_different_outtmpl():
    """Test that fallback profile has a different output template."""
    default = get_default_profile()
    fallback = get_fallback_profile()

    assert default["outtmpl"] != fallback["outtmpl"]
    assert "_fallback" in fallback["outtmpl"]


def test_telegram_profile_has_video_scaling():
    """Test that telegram profile includes video scaling."""
    profile = get_telegram_optimization_profile()

    # Check for video filter in postprocessor args
    assert "postprocessor_args" in profile
    args = profile["postprocessor_args"]

    # Should have -vf flag for video filtering
    assert "-vf" in args
