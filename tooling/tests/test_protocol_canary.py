"""Execute the canary shell with asynchronous fake verdicts, without network."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

from tooling.practice_ci import config

TEMPLATE = Path(__file__).resolve().parents[2] / 'templates/.github/workflows/protocol-canary.yml'


class Canary(unittest.TestCase):
    def test_configured_policy_and_both_verdicts(self):
        source = TEMPLATE.read_text()
        values = config.load()
        values['protocol']['poll']['kind'] = 'custom-kind'
        values['protocol']['canary'].update(specVersion='custom-spec', messageType='custom-type',
                                            protocolVersion='custom-protocol')
        def expand(match):
            value = values
            for key in match[1].split('.'):
                value = value[key]
            return str(value)
        source = re.sub(r'@@([\w.]+)@@', expand, source)
        env = dict(os.environ, GH_TOKEN='test', REPO='example/test', RUN='test')
        env_block = source.split('          PREFIX: ', 1)[1].split('        run: |', 1)[0]
        env_block = '          PREFIX: ' + env_block
        for line in textwrap.dedent(env_block).splitlines():
            key, value = line.split(': ', 1)
            env[key] = value.strip("'")
        self.assertEqual(env['KIND_LABEL'], values['protocol']['prefixes']['kind'] + 'custom-kind')
        self.assertEqual([env[k] for k in ('SPEC_VERSION', 'TYPE', 'PROTOCOL')],
                         ['custom-spec', 'custom-type', 'custom-protocol'])
        script = textwrap.dedent(source.split('        run: |\n', 1)[1])
        with tempfile.TemporaryDirectory() as tmp:
            env.update(PATH=tmp + os.pathsep + env['PATH'], TRACE=tmp + '/trace')
            fake = Path(tmp) / 'gh'
            fake.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
p = Path(os.environ['TRACE'])
a = sys.argv[1:]
with p.open('a') as f: f.write(repr(a) + '\\n')
if 'POST' in a:
    if any('title=' in x and x.endswith(' valid') for x in a):
        assert 'labels[]=' + os.environ['INVALID_LABEL'] in a
        print(1)
    else: print(2)
elif 'PATCH' not in a:
    # Invalid finishes immediately; valid finishes only after a delay.
    n = p.read_text().count("'repos/example/test/issues/1',")
    print('false' if a[1].endswith('/1') and n >= 3 else 'true')
''')
            fake.chmod(0o755)
            sleep = Path(tmp) / 'sleep'
            sleep.write_text('#!/bin/sh\nexit 0\n')
            sleep.chmod(0o755)
            result = subprocess.run(['bash', '-c', script], env=env, capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            trace = Path(env['TRACE']).read_text()
            self.assertGreaterEqual(trace.count("'repos/example/test/issues/1',"), 3)
