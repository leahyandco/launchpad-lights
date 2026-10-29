from launchpad_lights.config import DEFAULTS, Config


def test_bad_toml_falls_back_to_defaults_and_keeps_the_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[visualiser\nsub_mode = 3\n", encoding="utf-8")
    cfg = Config.load(path)
    assert cfg.section("visualiser")["sub_mode"] == DEFAULTS["visualiser"]["sub_mode"]
    assert (tmp_path / "config.bad.toml").exists()
    assert path.exists()  # rewritten with defaults


def test_wrong_types_are_fixed(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[visualiser]\nidle_timeout = "30s"\nfps = "45"\nauto_gain = "yes"\nsub_mode = 3.0\n'
        '[clock]\nview = "two"\n[app]\nmodes = "visualiser"\n',
        encoding="utf-8",
    )
    cfg = Config.load(path)
    viz = cfg.section("visualiser")
    assert viz["idle_timeout"] == DEFAULTS["visualiser"]["idle_timeout"]
    assert viz["fps"] == 45
    assert viz["auto_gain"] is True
    assert viz["sub_mode"] == 3 and isinstance(viz["sub_mode"], int)
    assert cfg.section("clock")["view"] == DEFAULTS["clock"]["view"]
    assert cfg.section("app")["modes"] == DEFAULTS["app"]["modes"]


def test_unknown_keys_survive(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[visualiser]\nsomething_new = 1\n", encoding="utf-8")
    assert Config.load(path).section("visualiser")["something_new"] == 1
