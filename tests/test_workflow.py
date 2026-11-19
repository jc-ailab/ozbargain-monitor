"""Offline checks for executable guards and last-publication recovery."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from scripts.fallback import publish
from monitor_core.store import save

ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_action_versions_and_pages_artifact_contract(self):
        text = (ROOT / '.github/workflows/monitor.yml').read_text()
        self.assertEqual(re.findall(r'uses: (actions/\S+)', text), [
            'actions/checkout@v7', 'actions/setup-python@v7',
            'actions/upload-pages-artifact@v5', 'actions/deploy-pages@v5'])
        upload = text.split('      - name: Upload Pages artifact\n', 1)[1]
        upload, deploy = upload.split('      - name: Deploy Pages\n', 1)
        self.assertIn('name: github-pages', upload)
        self.assertIn('path: _site', upload)
        self.assertIn('artifact_name: github-pages', deploy)
        self.assertIn('url: ${{ steps.deployment.outputs.page_url }}', text)

    def test_sydney_stop_guard(self):
        text = (ROOT / '.github/workflows/monitor.yml').read_text()
        guard = re.search(r"python3 - <<'PY'\n(.*?)\n          PY", text, re.S)[1]
        code = '\n'.join(line[10:] for line in guard.splitlines())
        for event, stop, expected in [('schedule', '2000-01-01', 'false'), ('workflow_dispatch', '2000-01-01', 'true'), ('schedule', '2999-01-01', 'true'), ('push', '2000-01-01', 'true')]:
            with tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / 'output'
                result = subprocess.run([sys.executable, '-c', code], env={**os.environ, 'EVENT_NAME': event, 'STOP_DATE': stop, 'GITHUB_OUTPUT': str(out)}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(out.read_text().strip(), 'proceed=' + expected)
        for required in ("7,37 * * * *", 'models: read', 'cancel-in-progress: false', 'commit --amend --no-edit', 'push --force origin HEAD:state', 'upload-pages-artifact', 'deploy-pages', 'python-version: \'3.12\''):
            self.assertIn(required, text)

    def test_publish_fallback_first_run_and_previous(self):
        with tempfile.TemporaryDirectory() as temp:
            publish('ozbargain', temp)
            path = Path(temp) / 'data/ozbargain.json'
            data = json.loads(path.read_text())
            self.assertEqual(data['items'], [])
            self.assertIsNone(data['generated_at'])
            self.assertIn('error:', data['stats']['feeds']['pipeline'])
            data['items'] = [{'id': 'retained'}]
            data['generated_at'] = '2026-11-20T00:00:00Z'
            save(path, data)
            publish('ozbargain', temp)
            recovered = json.loads(path.read_text())
            self.assertEqual(recovered['items'], data['items'])
            self.assertEqual(recovered['generated_at'], data['generated_at'])

    def test_actual_state_branch_shell_first_run_and_amend(self):
        """Execute the workflow's actual state blocks against a local bare remote."""
        import textwrap
        import shutil
        if not shutil.which('git'):
            self.skipTest('Git unavailable')
        text = (ROOT / '.github/workflows/monitor.yml').read_text()
        def block(name):
            section = text.split('      - name: ' + name + '\n', 1)[1]
            return textwrap.dedent(section.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0])
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
            def git(*args, cwd=temp):
                result = subprocess.run(['git', *args], cwd=cwd, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()
            git('init', '--bare', '--initial-branch=main', str(temp / 'origin.git'))
            git('clone', str(temp / 'origin.git'), str(temp / 'work'))
            work = temp / 'work'
            git('config', 'user.name', 'Test', cwd=work)
            git('config', 'user.email', 'test@example.invalid', cwd=work)
            (work / 'seed').write_text('main')
            git('add', 'seed', cwd=work)
            git('commit', '-m', 'Seed', cwd=work)
            git('push', 'origin', 'main', cwd=work)
            for number in (1, 2):
                result = subprocess.run(['bash', '-e', '-c', block('Check out state branch or create orphan')], cwd=work, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                state = work / 'state'
                for name in ('ozbargain', 'hackernews', 'data'):
                    (state / name).mkdir(exist_ok=True)
                    if name == 'data' or number == 2:
                        (state / name / 'test.json').write_text(json.dumps({'run': number}))
                result = subprocess.run(['bash', '-e', '-c', block('Keep a single amended state commit')], cwd=work, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(git('rev-list', '--count', 'state', cwd=temp / 'origin.git'), '1')
                self.assertEqual(git('show', 'state:data/test.json', cwd=temp / 'origin.git'), json.dumps({'run': number}))
                self.assertEqual((work / 'seed').read_text(), 'main')
                git('worktree', 'remove', 'state', cwd=work)
