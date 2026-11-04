# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""The source installer's Node.js gate accepts exactly the versions its pinned tools accept.

scripts/install_twinpulse.ps1 runs the pinned pnpm (install, then `tsc -b && vite build` in
apps/twinpulse-web) and `npm ci` plus electron/install.js in apps/twinpulse-desktop. What
those tools accept comes from the two lock files and from pnpm's own minimum; the gate, its
messages and the docs must agree with it. No network, Windows, install or build is involved.
"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / 'scripts/install_twinpulse.ps1'
WEB = ROOT / 'apps/twinpulse-web'
DESKTOP = ROOT / 'apps/twinpulse-desktop'
# What `pnpm build` runs (package.json "build": "tsc -b && vite build"), with what they load.
WEB_BUILD_TOOLS = ('typescript', 'vite', '@vitejs/plugin-react')
# pnpm's own minimum is in neither lock. pnpm 11.19.0 declares engines.node ">=22.13", and its
# bin/pnpm.mjs exits with an error below 22.13 (Node 20 gets only a warning, which the electron
# engines rule out anyway). When the pin changes, add the new version's engines.node here.
PNPM_NODE = {'11.19.0': '>=22.13'}
DOCS = ('README.md', 'docs/QUICKSTART.md', 'docs/COMPANY_PC_INSTALL.md', 'docs/WINDOWS_EXE_BUILD.md')
# "Node.js 22.13+", "Node.js 22.13 or later", "Node.js 22.13 이상": a stated minimum.
DOC_MINIMUM = re.compile(r'Node(?:\.js)?\s+\**(\d+\.\d+(?:\.\d+)?)(?:\+|\s+or later|\s*이상)')
COMPARATOR = re.compile(r'\s*(>=|<=|>|<|=|\^|~)?\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?\s*')


def _bounds(op, major, minor, patch):
    """[low, high) of one node-semver comparator over release versions (int triples)."""
    low = (major, minor or 0, patch or 0)
    following = ((major + 1, 0, 0) if minor is None else (major, minor + 1, 0) if patch is None
                 else (major, minor, patch + 1))
    if op in ('', '='):
        return low, following
    if op == '^' and major > 0:
        return low, (major + 1, 0, 0)
    if op == '~':
        return low, (major + 1, 0, 0) if minor is None else (major, minor + 1, 0)
    if op == '>=':
        return low, None
    if op == '>':
        return following, None
    if op == '<':
        return None, low
    if op == '<=':
        return None, following
    raise ValueError('unsupported comparator ' + op + str(low))


def satisfies(version, spec):
    """The node-semver subset these locks use: alternatives joined by ||, each a list of
    comparators (^, ~, >=, >, <=, <, = or a bare, possibly partial, version)."""
    for alternative in spec.split('||'):
        alternative, position, accepted = alternative.strip(), 0, True
        if not alternative:
            raise ValueError('unsupported range ' + repr(spec))
        while position < len(alternative):
            match = COMPARATOR.match(alternative, position)
            if not match or match.end() == position:
                raise ValueError('unsupported range ' + repr(spec))
            position = match.end()
            numbers = [None if item is None else int(item) for item in match.group(2, 3, 4)]
            low, high = _bounds(match.group(1) or '', *numbers)
            accepted = accepted and (low is None or version >= low) and (high is None or version < high)
        if accepted:
            return True
    return False


def desktop_ranges():
    """engines.node of every package npm ci installs from the desktop lock (optional ones are skipped)."""
    lock = json.loads((DESKTOP / 'package-lock.json').read_text(encoding='utf-8'))
    ranges = {}
    for path, package in lock['packages'].items():
        engines = package.get('engines')
        if engines is None or package.get('optional'):
            continue
        if not isinstance(engines, dict):
            raise ValueError('engines is not an object: ' + path)
        if 'node' in engines:
            ranges[path] = engines['node']
    return ranges


def _lock_sections(text):
    """pnpm-lock.yaml v9 top-level sections as {section: {entry key: [its lines]}}."""
    sections, current, lines = {}, None, None
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith(' '):
            current = sections.setdefault(line.split(':', 1)[0], {})
        elif not line.startswith('   '):
            key = line.strip()
            key = key[:-1] if key.endswith(':') else key.rsplit(': ', 1)[0]
            lines = current.setdefault(key.strip("'"), [])
        else:
            lines.append(line)
    return sections


def _field(lines, name):
    for line in lines:
        if line.startswith('    ' + name + ': '):
            return line.split(': ', 1)[1].strip()
    return None


def _runs_on_windows_x64(lines):
    for name, wanted in (('os', 'win32'), ('cpu', 'x64')):
        value = _field(lines, name)
        if value is not None:
            items = [item.strip().strip("'") for item in value.strip('[]').split(',')]
            if wanted not in items and not (all(item.startswith('!') for item in items) and '!' + wanted not in items):
                return False
    return True


def _split(key):
    """'@scope/name@1.2.3(peer@4)' -> ('@scope/name', '1.2.3(peer@4)')."""
    at = key.split('(', 1)[0].rindex('@')
    return key[:at], key[at + 1:]


def web_build_ranges():
    """engines.node of the web build tools and everything they depend on, on Windows x64."""
    sections = _lock_sections((WEB / 'pnpm-lock.yaml').read_text(encoding='utf-8'))
    packages, snapshots, versions, group = sections['packages'], sections['snapshots'], {}, None
    for line in sections['importers']['.']:
        if re.match(r'^      \S', line):
            group = line.strip().rstrip(':').strip("'")
        elif line.startswith('        version: '):
            versions[group] = line.split(': ', 1)[1].strip().strip("'")
    pending, seen, ranges = [name + '@' + versions[name] for name in WEB_BUILD_TOOLS], set(), {}
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        name, version = _split(key)
        package = packages[name + '@' + version.split('(', 1)[0]]
        if not _runs_on_windows_x64(package):
            continue  # another platform's optional binary: never installed or run here
        engines = _field(package, 'engines')
        node = re.search(r"\bnode: ('[^']*'|[^,}]+)", engines or '')
        if node:
            ranges[name + '@' + version.split('(', 1)[0]] = node.group(1).strip().strip("'")
        group = None
        for line in snapshots[key]:
            heading = re.match(r'^    (\w+):', line)
            if heading:
                group = heading.group(1)
            elif group in ('dependencies', 'optionalDependencies'):
                dependency, reference = line.strip().split(': ', 1)
                pending.append(dependency.strip("'") + '@' + reference.strip().strip("'"))
    return ranges


def pnpm_range(test):
    pinned = json.loads((WEB / 'package.json').read_text(encoding='utf-8'))['packageManager']
    test.assertTrue(pinned.startswith('pnpm@'), pinned)
    version = pinned.split('@', 1)[1]
    # The installer's npm fallback runs the same pnpm the web package pins.
    test.assertEqual(set(re.findall(r'--package=pnpm@([0-9A-Za-z.+-]+)', INSTALLER.read_text(encoding='utf-8'))), {version})
    test.assertIn(version, PNPM_NODE, 'record engines.node of pnpm ' + version + ' in PNPM_NODE')
    return PNPM_NODE[version]


def grid(ranges):
    """Release versions around every bound the ranges name, plus a dense band of majors 14-27."""
    versions = {(major, minor, patch) for major in range(14, 28) for minor in range(41) for patch in (0, 1, 2, 99)}
    for spec in ranges:
        for numbers in re.findall(r'(\d+)(?:\.(\d+))?(?:\.(\d+))?', spec):
            major, minor, patch = (int(item or 0) for item in numbers)
            versions |= {(major, minor, patch), (major, minor, patch + 1), (major, minor, max(patch - 1, 0)),
                         (major, max(minor - 1, 0), 99)}
    return sorted(versions)


def required_ranges(test):
    ranges = [*desktop_ranges().values(), *web_build_ranges().values(), pnpm_range(test)]
    test.assertGreater(len(ranges), 20)  # both locks were read, not an empty walk
    return ranges


class SourceInstallNodeGateTests(unittest.TestCase):
    def test_range_reader_follows_node_semver_on_the_forms_these_locks_use(self):
        rows = (('>= 22.12.0', (22, 12, 0), True), ('>=22.12.0', (22, 11, 99), False),
                ('^20.19.0 || >=22.12.0', (21, 0, 0), False), ('^20.19.0 || >=22.12.0', (20, 99, 0), True),
                ('20 || >=22', (20, 5, 1), True), ('20 || >=22', (21, 9, 9), False),
                ('>=16 || 14 >=14.17', (14, 17, 0), True), ('>=16 || 14 >=14.17', (14, 16, 9), False),
                ('^22.22.2 || ^24.15.0 || >=26.0.0', (24, 14, 0), False), ('>=v12.22.7', (12, 22, 7), True),
                ('~1.2.3', (1, 3, 0), False), ('>22.13', (22, 13, 5), False), ('>22.13', (22, 14, 0), True),
                ('<=22.12', (22, 12, 9), True), ('<22.13.0', (22, 13, 0), False))
        for spec, version, expected in rows:
            self.assertIs(satisfies(version, spec), expected, (spec, version))
        with self.assertRaises(ValueError):
            satisfies((22, 0, 0), '1.x || >=22')

    def test_gate_accepts_exactly_the_node_versions_the_locked_tools_accept(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('node is not installed here; the source install needs it')
        ranges = required_ranges(self)
        scripts = re.findall(r'^\s*& node -e "([^"]*)"\s*$', INSTALLER.read_text(encoding='utf-8'), re.M)
        self.assertEqual(len(scripts), 1, 'one Node.js gate in the installer')
        # PowerShell would expand $ and ` inside its double quotes; the text node gets is the text here.
        self.assertNotRegex(scripts[0], r'[$`]')
        versions = grid(ranges)
        evaluate = ("const vm=require('vm');const input=JSON.parse(require('fs').readFileSync(0,'utf8'));"
                    "const script=new vm.Script('(function(){\\n'+input.gate+'\\n})()');const context=vm.createContext({});"
                    "const verdicts={};for(const version of input.versions){let code=0;"
                    "context.process={versions:{node:version},exit:(value)=>{throw {exitCode:value};}};"
                    "try{script.runInContext(context);}catch(error){if(error===null||typeof error!=='object'||!('exitCode' in error))throw error;"
                    "code=error.exitCode;}verdicts[version]=code;}process.stdout.write(JSON.stringify(verdicts));")
        names = ['%d.%d.%d' % version for version in versions]
        done = subprocess.run([node, '-e', evaluate], input=json.dumps({'gate': scripts[0], 'versions': names}),
                              capture_output=True, text=True, timeout=120, check=True)
        verdicts = json.loads(done.stdout)
        wrong = [name for name, version in zip(names, versions)
                 if (verdicts[name] == 0) != all(satisfies(version, spec) for spec in ranges)]
        self.assertEqual(wrong[:10], [], 'gate and locked engines disagree on %d versions' % len(wrong))
        self.assertEqual({verdicts[name] for name in names}, {0, 1})
        # The same text run by node itself, as the installer runs it, on this machine's Node.js.
        current = tuple(int(part) for part in subprocess.run([node, '-p', 'process.versions.node'], capture_output=True,
                                                            text=True, check=True).stdout.strip().split('.')[:3])
        real = subprocess.run([node, '-e', scripts[0]], capture_output=True, text=True, timeout=60)
        self.assertEqual(real.returncode == 0, all(satisfies(current, spec) for spec in ranges), current)

    def test_messages_and_docs_name_the_lowest_version_the_tools_accept(self):
        ranges = required_ranges(self)
        versions = grid(ranges)
        accepted = [version for version in versions if all(satisfies(version, spec) for spec in ranges)]
        lowest = accepted[0]
        # "X.Y or later" is true only when every later version is accepted too.
        self.assertEqual([version for version in versions if version >= lowest], accepted)
        text = '%d.%d' % lowest[:2] if lowest[2] == 0 else '%d.%d.%d' % lowest
        named = re.findall(r'(\d+\.\d+(?:\.\d+)?) or later', INSTALLER.read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(named), 2, 'the missing-Node message and the version-check label')
        self.assertEqual(set(named), {text})
        for name in DOCS:
            stated = DOC_MINIMUM.findall((ROOT / name).read_text(encoding='utf-8'))
            self.assertTrue(stated, name + ' states the Node.js minimum')
            self.assertEqual(set(stated), {text}, name)


if __name__ == '__main__':
    unittest.main()
