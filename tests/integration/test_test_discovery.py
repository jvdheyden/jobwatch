"""Exercise collection/skip policy through an isolated, newly added test file."""
import sys

import pytest


@pytest.mark.parametrize(('body', 'passes', 'summary'), [
    ('def test_new_file(): assert True', True, '1 passed'),
    ('def test_required(): pytest.skip("missing required fixture")', False, 'required tests must not skip'),
    ('pytest.skip("missing module fixture", allow_module_level=True)', False, 'collection must not skip'),
    ('@pytest.mark.optional\ndef test_optional(): pytest.skip("optional platform capability unavailable")', True, '1 skipped'),
])
def test_new_modules_are_collected_and_only_explicit_optional_tests_skip(tmp_path, repo_root, run_cmd, body, passes, summary):
    (tmp_path / 'conftest.py').symlink_to(repo_root / 'tests/conftest.py')
    (tmp_path / 'test_new_contribution.py').write_text('import pytest\n' + body + '\n')
    result = run_cmd(sys.executable, '-m', 'pytest', '-c', str(repo_root / 'pytest.ini'),
                     '--confcutdir', str(tmp_path), str(tmp_path), '-q')
    assert (result.returncode == 0) == passes, result.stdout + result.stderr
    assert summary in result.stdout
