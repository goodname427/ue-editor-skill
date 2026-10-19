#!/usr/bin/env python
"""
ue-editor 安装器 - 把本仓库的 Skill、规则与 AgentTools 插件链接到 Agent 目录和 UE 工程。

用法:
  python install.py --skills <Skill目录> --rules <规则目录> --project <工程目录或.uproject>   各项可重复、可只给其中几类
  python install.py --update                          git pull 后按安装记录逐个复查、修复链接
  python install.py --uninstall --skills ... --rules ... --project ...   卸载前先关闭编辑器
  python install.py                                   不带参数时交互输入

链接方式（Windows 目录用联接 junction，无需管理员；文件用符号链接）:
  <Skill目录>/ue-editor                    -> <仓库>/skills/ue-editor
  <规则目录>/ue-editor.md                  -> <仓库>/rules/ue-editor.md
  <工程>/Plugins/AgentTools/Source         -> <仓库>/Plugins/AgentTools/Source
  <工程>/Plugins/AgentTools/AgentTools.uplugin -> <仓库>/Plugins/AgentTools/AgentTools.uplugin
文件符号链接没有权限时退化为复制（[copy]），之后靠 --update 刷新。

装过的目标记在 <仓库>/installed.json（不入库）。平时 git pull 即生效；新增了安装项、
出现过 [copy]，或 IDE 把规则链接替换成了普通文件时，跑一次 --update 即可全部修好。
IDE 若回写规则文件（如 updatedAt），改动会落到仓库里，git status 能看到，不提交即可。
"""

import os
import sys
import json
import shutil
import argparse
import subprocess

REPO = os.path.dirname(os.path.abspath(__file__))
SKILL_NAME = 'ue-editor'
SKILL_SRC = os.path.join(REPO, 'skills', SKILL_NAME)
RULE_NAME = 'ue-editor.md'
RULE_SRC = os.path.join(REPO, 'rules', RULE_NAME)
PLUGIN_NAME = 'AgentTools'
PLUGIN_SRC = os.path.join(REPO, 'Plugins', PLUGIN_NAME)
UPLUGIN = PLUGIN_NAME + '.uplugin'
RECORD = os.path.join(REPO, 'installed.json')
KINDS = ('skills', 'rules', 'project')
IS_WIN = os.name == 'nt'

sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')


def _norm(path):
    path = os.path.abspath(path)
    if path.startswith('\\\\?\\'):
        path = path[4:]
    return os.path.normcase(os.path.normpath(path))


def _link_target(path):
    """目录联接/符号链接返回指向，普通文件或目录返回 None。"""
    try:
        return _norm(os.path.join(os.path.dirname(os.path.abspath(path)), os.readlink(path)))
    except (OSError, ValueError):
        return None


def _remove_link(path):
    # junction 与目录符号链接只删链接本身，不会进入目标目录
    if os.path.isdir(path) and not os.path.islink(path):
        os.rmdir(path)
    else:
        os.unlink(path)


def _read(path):
    with open(path, 'rb') as fp:
        return fp.read()


def _link_dir(dest, src):
    current = _link_target(dest)
    if current == _norm(src):
        print('[ok]      %s' % dest)
        return
    if current is not None:
        _remove_link(dest)
        print('[relink]  %s（原指向 %s）' % (dest, current))
    elif os.path.lexists(dest):
        raise RuntimeError('%s 已存在且不是链接，请先手动移走再安装' % dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if IS_WIN:
        r = subprocess.run(['cmd', '/d', '/c', 'mklink', '/J', dest, src], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError('创建目录联接失败: %s %s' % (dest, (r.stdout + r.stderr).strip()))
    else:
        os.symlink(src, dest, target_is_directory=True)
    print('[link]    %s -> %s' % (dest, src))


def _link_file(dest, src):
    """文件用符号链接；不用硬链接，git pull 会换掉仓库文件，硬链接会静默停在旧版本。"""
    if _link_target(dest) == _norm(src):
        print('[ok]      %s' % dest)
        return
    if os.path.lexists(dest):
        if _link_target(dest) is None and os.path.isfile(dest) and _read(dest) != _read(src):
            # 普通文件且内容不同：可能是 IDE 回写或手改过，留一份备份再替换
            shutil.copyfile(dest, dest + '.bak')
            print('[backup]  %s.bak' % dest)
        os.unlink(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        os.symlink(src, dest)
        print('[link]    %s -> %s' % (dest, src))
    except OSError:
        shutil.copyfile(src, dest)
        print('[copy]    %s（无符号链接权限，已复制；git pull 后跑 --update 刷新）' % dest)


def _project_dir(path):
    path = os.path.abspath(os.path.expanduser(path))
    if path.lower().endswith('.uproject'):
        path = os.path.dirname(path)
    if not os.path.isdir(path) or not any(n.lower().endswith('.uproject') for n in os.listdir(path)):
        raise RuntimeError('不是 UE 工程目录（找不到 .uproject）: %s' % path)
    return path


def _dir(path):
    return os.path.abspath(os.path.expanduser(path))


def install_skill(skills_dir):
    _link_dir(os.path.join(_dir(skills_dir), SKILL_NAME), SKILL_SRC)


def install_rule(rules_dir):
    _link_file(os.path.join(_dir(rules_dir), RULE_NAME), RULE_SRC)


def install_plugin(project):
    plugin_dir = os.path.join(_project_dir(project), 'Plugins', PLUGIN_NAME)
    if _link_target(plugin_dir) is not None:
        raise RuntimeError('%s 是链接（旧的整目录链接方式），请先删除该链接再安装' % plugin_dir)
    os.makedirs(plugin_dir, exist_ok=True)
    _link_dir(os.path.join(plugin_dir, 'Source'), os.path.join(PLUGIN_SRC, 'Source'))
    _link_file(os.path.join(plugin_dir, UPLUGIN), os.path.join(PLUGIN_SRC, UPLUGIN))


def uninstall_skill(skills_dir):
    dest = os.path.join(_dir(skills_dir), SKILL_NAME)
    if _link_target(dest) == _norm(SKILL_SRC):
        _remove_link(dest)
        print('[remove]  %s' % dest)
    elif os.path.lexists(dest):
        print('[skip]    %s 不是本仓库安装的链接' % dest)


def uninstall_rule(rules_dir):
    dest = os.path.join(_dir(rules_dir), RULE_NAME)
    if not os.path.lexists(dest):
        print('[skip]    %s 不存在' % dest)
    elif _link_target(dest) == _norm(RULE_SRC) or (os.path.isfile(dest) and _read(dest) == _read(RULE_SRC)):
        os.unlink(dest)
        print('[remove]  %s' % dest)
    else:
        print('[skip]    %s 不是本仓库安装的规则或已被修改，未删除' % dest)


def uninstall_plugin(project):
    plugin_dir = os.path.join(_project_dir(project), 'Plugins', PLUGIN_NAME)
    source = os.path.join(plugin_dir, 'Source')
    uplugin = os.path.join(plugin_dir, UPLUGIN)
    ours = _link_target(source) == _norm(os.path.join(PLUGIN_SRC, 'Source'))
    if not ours and os.path.lexists(source):
        print('[skip]    %s 不是本仓库安装的插件' % plugin_dir)
        return
    if not os.path.isdir(plugin_dir):
        print('[skip]    %s 不存在' % plugin_dir)
        return
    # 先删编译产物（编辑器占用 DLL 时会在这里失败），Source 链接最后删，失败后可直接重跑
    for name in ('Binaries', 'Intermediate'):
        path = os.path.join(plugin_dir, name)
        if os.path.isdir(path) and _link_target(path) is None:
            shutil.rmtree(path)
    # uplugin 可能是符号链接，也可能是安装时退化出的复制（旧版还可能是硬链接）
    if os.path.lexists(uplugin) and (ours or _link_target(uplugin) == _norm(os.path.join(PLUGIN_SRC, UPLUGIN))):
        os.unlink(uplugin)
    if ours:
        _remove_link(source)
    left = os.listdir(plugin_dir)
    if not left:
        os.rmdir(plugin_dir)
        print('[remove]  %s' % plugin_dir)
    else:
        print('[warn]    %s 已移除链接，但目录内还有未删除的文件: %s' % (plugin_dir, ', '.join(left)))


ACTIONS = {
    'skills': (install_skill, uninstall_skill),
    'rules': (install_rule, uninstall_rule),
    'project': (install_plugin, uninstall_plugin),
}


def _load_record():
    try:
        with open(RECORD, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        return {kind: list(data.get(kind, [])) for kind in KINDS}
    except (OSError, ValueError):
        return {kind: [] for kind in KINDS}


def _save_record(record):
    with open(RECORD, 'w', encoding='utf-8') as fp:
        json.dump(record, fp, ensure_ascii=False, indent=2)
        fp.write('\n')


def _record_key(kind, path):
    path = _dir(path)
    if kind == 'project' and path.lower().endswith('.uproject'):
        path = os.path.dirname(path)
    return _norm(path)


def _git_pull():
    r = subprocess.run(['git', '-C', REPO, 'pull', '--ff-only'], capture_output=True, text=True)
    print((r.stdout + r.stderr).strip())
    if r.returncode != 0:
        raise RuntimeError('git pull 失败，先处理本地改动或冲突再重跑 --update')


def _check_python_deps():
    missing = []
    for module, package in (('win32gui', 'pywin32'), ('PIL', 'pillow')):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        print('[warning] 截图功能缺少依赖: pip install %s' % ' '.join(missing))


def _ask(prompt):
    values = []
    print(prompt + '（每行一个，空行结束）')
    while True:
        line = input('> ').strip().strip('"')
        if not line:
            return values
        values.append(line)


def main():
    parser = argparse.ArgumentParser(description='安装 ue-editor Skill、规则与 AgentTools 插件（链接方式）')
    parser.add_argument('--skills', action='append', default=[], help='Agent 的 Skill 目录，如 ~/.codebuddy/skills，可多次指定')
    parser.add_argument('--rules', action='append', default=[], help='Agent 的规则目录，如 ~/.codebuddy/rules 或 <工程>/.codebuddy/rules，可多次指定')
    parser.add_argument('--project', action='append', default=[], help='UE 工程目录或 .uproject 路径，可多次指定')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--update', action='store_true', help='git pull 后按 installed.json 复查、修复所有已安装目标')
    mode.add_argument('--uninstall', action='store_true', help='移除本仓库创建的链接、规则与插件目录')
    args = parser.parse_args()

    record = _load_record()
    if args.update:
        if any(getattr(args, kind) for kind in KINDS):
            parser.error('--update 不接受路径参数；它按 installed.json 里的记录处理')
        _git_pull()
        targets = record
        if not any(targets.values()):
            print('[warning] installed.json 里没有安装记录；先用 --skills/--rules/--project 安装一次')
    else:
        if not any(getattr(args, kind) for kind in KINDS):
            args.skills = _ask('输入 Agent 的 Skill 目录')
            args.rules = _ask('输入 Agent 的规则目录')
            args.project = _ask('输入 UE 工程目录或 .uproject 路径')
        targets = {kind: getattr(args, kind) for kind in KINDS}

    failed = False
    for kind in KINDS:
        install, uninstall = ACTIONS[kind]
        for path in targets[kind]:
            try:
                (uninstall if args.uninstall else install)(path)
                key = _record_key(kind, path)
                record[kind] = [p for p in record[kind] if _record_key(kind, p) != key]
                if not args.uninstall:
                    record[kind].append(path)
            except Exception as e:
                failed = True
                print('[error]   %s' % e)
    _save_record(record)

    if not args.uninstall:
        if IS_WIN and targets['skills']:
            _check_python_deps()
        if targets['project']:
            print('插件源码有改动时需重新编译：编辑器开着用 Live Coding（Ctrl+Alt+F11），否则打开 .uproject 按提示重建，或用 Build.bat <工程>Editor Win64 Development。')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
