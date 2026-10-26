"""Regression tests for the secure-default boot behavior (B9, Stage 1 audit).

The API key used to fall back to the publicly documented 'dseeker' silently;
an unset key is now generated, printed once and persisted next to the DB.
Explicit keys are honored unchanged.

Run:  python tests/test_security_defaults.py   (pytest-compatible)
"""

import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402
import functions  # noqa: E402


def _with_db_dir(tmpdir):
    """在测试期间把 functions.data_dir() 指向 tmpdir。

    B12 把数据库（以及与其同级的运行时文件）在导入时就锚定到 functions._db，
    因此测试改为打补丁该模块属性，而非设置 DB_PATH 环境变量。
    """
    saved = functions._db
    functions._db = os.path.join(tmpdir, "deeperseeker.db")

    def _restore():
        functions._db = saved

    return _restore


def test_explicit_key_honored():
    with mock.patch.dict(os.environ, {"DEEPSEEKER_API_KEY": "my-custom-key"}):
        key, generated = app_module._resolve_api_key()
    assert key == "my-custom-key"
    assert generated is False


def test_empty_key_generates_and_persists():
    tmpdir = tempfile.mkdtemp()
    key_file = os.path.join(tmpdir, "api_key.txt")
    restore = _with_db_dir(tmpdir)
    try:
        with mock.patch.dict(os.environ, {"DEEPSEEKER_API_KEY": ""}):
            key1, generated1 = app_module._resolve_api_key()
            assert generated1 is True
            assert key1.startswith("dsk-") and len(key1) > 20, key1
            # persisted with restrictive permissions
            assert os.path.isfile(key_file)
            with open(key_file) as f:
                assert f.read().strip() == key1
            if os.name == "posix":
                assert not (os.stat(key_file).st_mode & 0o077), (
                    "key file must not be group/world accessible"
                )
            # a second boot reuses the persisted key instead of rotating it
            key2, generated2 = app_module._resolve_api_key()
    finally:
        restore()
    assert key2 == key1, "the persisted key must survive restarts"
    assert generated2 is True  # still "generated" (not user-supplied), but stable


def test_generated_key_never_equals_documented_default():
    tmpdir = tempfile.mkdtemp()
    restore = _with_db_dir(tmpdir)
    try:
        with mock.patch.dict(os.environ, {"DEEPSEEKER_API_KEY": ""}):
            key, _ = app_module._resolve_api_key()
    finally:
        restore()
    assert key != "dseeker"


def test_banner_classifies_loopback_and_exposed_hosts():
    # Must not raise, and must pick the exposed-host branch when HOST != loopback.
    with mock.patch.dict(os.environ, {"HOST": "0.0.0.0"}):
        app_module._log_security_banner()  # smoke: logs, never crashes
    with mock.patch.dict(os.environ, {"HOST": "127.0.0.1"}):
        app_module._log_security_banner()


def test_module_api_key_always_present():
    assert app_module.API_KEY, "API_KEY must never be empty (fail-open)"


def test_boot3_default_admin_non_loopback_refuses():
    """默认口令遇到非环回绑定必须拒绝启动，且拒绝信息须指明具体改法。"""
    with mock.patch.dict(os.environ, {"HOST": "0.0.0.0"}):
        try:
            app_module._enforce_exposure_policy()
        except SystemExit as e:
            message = str(e)
            assert "DEEPSEEKER_ADMIN_PASSWORD" in message, (
                "拒绝信息必须指明具体的环境变量改法"
            )
            assert "DEEPSEEKER_ADMIN_USER" in message
        else:
            raise AssertionError("默认口令与非环回绑定同时存在时必须拒绝启动")


def test_boot2_default_admin_loopback_still_boots():
    """环回绑定配合默认口令保持既有行为：仅告警，不拒绝。"""
    with mock.patch.dict(os.environ, {"HOST": "127.0.0.1"}):
        app_module._enforce_exposure_policy()  # 不得抛出


def test_boot2_default_admin_unset_host_still_boots():
    """HOST 未设置时取默认值 127.0.0.1，属于环回启动。"""
    with mock.patch.dict(os.environ, {}, clear=True):
        app_module._enforce_exposure_policy()  # 不得抛出


def test_non_default_admin_non_loopback_boots():
    """显式口令加对外绑定属于合法部署，应予放行。"""
    with (
        mock.patch.dict(os.environ, {"HOST": "0.0.0.0"}),
        mock.patch.object(app_module, "ADMIN_USER", "ops"),
        mock.patch.object(app_module, "ADMIN_PASSWORD", "correct horse battery staple"),
    ):
        app_module._enforce_exposure_policy()  # 不得抛出


def test_boot3_escape_hatch_is_explicit():
    """放行开关必须存在，且只认显式取值 1。"""
    with mock.patch.dict(
        os.environ, {"HOST": "0.0.0.0", "DEEPSEEKER_ALLOW_DEFAULT_ADMIN": "1"}
    ):
        app_module._enforce_exposure_policy()  # 显式接受风险，放行
    with mock.patch.dict(
        os.environ, {"HOST": "0.0.0.0", "DEEPSEEKER_ALLOW_DEFAULT_ADMIN": "0"}
    ):
        try:
            app_module._enforce_exposure_policy()
        except SystemExit:
            pass
        else:
            raise AssertionError("除 1 以外的任何取值都必须继续拒绝")


TESTS = [
    test_explicit_key_honored,
    test_empty_key_generates_and_persists,
    test_generated_key_never_equals_documented_default,
    test_banner_classifies_loopback_and_exposed_hosts,
    test_module_api_key_always_present,
    test_boot3_default_admin_non_loopback_refuses,
    test_boot2_default_admin_loopback_still_boots,
    test_boot2_default_admin_unset_host_still_boots,
    test_non_default_admin_non_loopback_boots,
    test_boot3_escape_hatch_is_explicit,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    if failed:
        sys.exit(1)
    print(f"{len(TESTS)} tests passed")


if __name__ == "__main__":
    main()
