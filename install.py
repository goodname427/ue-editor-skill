#!/usr/bin/env python
"""
ue-editor 安装器 - 把本仓库的 Skill 与 AgentTools 插件链接到 Agent 的 Skill 目录和 UE 工程。

用法:
  python install.py --skills <Skill目录> [--skills ...] --project <工程目录或.uproject> [--project ...]
  python install.py --uninstall --skills <Skill目录> --project <工程目录>   卸载前先关闭编辑器
  python install.py                                   不带参数时交互输入

链接方式（Windows 用目录联接 junction，无需管理员；其它系统用符号链接）:
  <Skill目录>/ue-editor                    -> <仓库>/skills/ue-editor
  <工程>/Plugins/AgentTools/Source         -> <仓库>/Plugins/AgentTools/Source
  <工程>/Plugins/AgentTools/AgentTools.uplugin  符号链接，失败时退化为硬链接/复制
  <rules目录>/ue-editor.md                 复制自 <仓库>/rules/ue-editor.md（IDE 可能回写文件，规则用复制）

插件目录本身留在工程内，Binaries / Intermediate 按工程各自生成，多个工程或分支共享同一份源码互不干扰。
之后 git pull 即可更新；uplugin 只在增减模块时变化，若安装时退化为复制，届时重跑一次安装器。
"""

import os
import sys
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
    if _link_target(dest) == _norm(src):
        print('[ok]      %s' % dest)
        return
    if os.path.lexists(dest):
        os.unlink(dest)
    try:
        os.symlink(src, dest)
        print('[link]    %s -> %s' % (dest, src))
        return
    except OSError:
        pass
    try:
        os.link(src, dest)
        print('[hard]    %s（硬链接；git 更新该文件后需重跑安装器）' % dest)
    except OSError:
        shutil.copyfile(src, dest)
        print('[copy]    %s（复制；uplugin 变化后需重跑安装器）' % dest)


def _project_dir(path):
    path = os.path.abspath(os.path.expanduser(path))
    if path.lower().endswith('.uproject'):
        path = os.path.dirname(path)
    if not os.path.isdir(path) or not any(n.lower().endswith('.uproject') for n in os.listdir(path)):
        raise RuntimeError('不是 UE 工程目录（找不到 .uproject）: %s' % path)
    return path


def install_skill(skills_dir):
    _link_dir(os.path.join(os.path.abspath(os.path.expanduser(skills_dir)), SKILL_NAME), SKILL_SRC)


def _read(path):
    with open(path, 'rb') as fp:
        return fp.read()


def install_rule(rules_dir):
    # 规则不建链接：IDE 可能回写 updatedAt 等字段，链接会改到仓库文件
    dest = os.path.join(os.path.abspath(os.path.expanduser(rules_dir)), RULE_NAME)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isfile(dest) and _read(dest) == _read(RULE_SRC):
        print('[ok]      %s' % dest)
        return
    shutil.copyfile(RULE_SRC, dest)
    print('[copy]    %s' % dest)


def install_plugin(project):
    plugin_dir = os.path.join(_project_dir(project), 'Plugins', PLUGIN_NAME)
    if _link_target(plugin_dir) is not None:
        raise RuntimeError('%s 是链接（旧的整目录链接方式），请先删除该链接再安装' % plugin_dir)
    os.makedirs(plugin_dir, exist_ok=True)
    _link_dir(os.path.join(plugin_dir, 'Source'), os.path.join(PLUGIN_SRC, 'Source'))
    _link_file(os.path.join(plugin_dir, UPLUGIN), os.path.join(PLUGIN_SRC, UPLUGIN))


def uninstall_rule(rules_dir):
    dest = os.path.join(os.path.abspath(os.path.expanduser(rules_dir)), RULE_NAME)
    if not os.path.isfile(dest):
        print('[skip]    %s 不存在' % dest)
    elif _read(dest) != _read(RULE_SRC):
        print('[skip]    %s 已被修改，未删除' % dest)
    else:
        os.unlink(dest)
        print('[remove]  %s' % dest)


def uninstall_skill(skills_dir):
    dest = os.path.join(os.path.abspath(os.path.expanduser(skills_dir)), SKILL_NAME)
    if _link_target(dest) == _norm(SKILL_SRC):
        _remove_link(dest)
        print('[remove]  %s' % dest)
    elif os.path.lexists(dest):
        print('[skip]    %s 不是本仓库安装的链接' % dest)


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
    # uplugin 可能是符号链接，也可能是安装时退化出的硬链接/复制
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
    parser = argparse.ArgumentParser(description='安装 ue-editor Skill 与 AgentTools 插件（链接方式）')
    parser.add_argument('--skills', action='append', default=[], help='Agent 的 Skill 目录，如 ~/.codebuddy/skills，可多次指定')
    parser.add_argument('--rules', action='append', default=[], help='Agent 的规则目录，如 ~/.codebuddy/rules，可多次指定')
    parser.add_argument('--project', action='append', default=[], help='UE 工程目录或 .uproject 路径，可多次指定')
    parser.add_argument('--uninstall', action='store_true', help='移除本仓库创建的链接、规则与插件目录')
    args = parser.parse_args()

    if not args.skills and not args.rules and not args.project:
        args.skills = _ask('输入 Agent 的 Skill 目录')
        args.rules = _ask('输入 Agent 的规则目录')
        args.project = _ask('输入 UE 工程目录或 .uproject 路径')

    failed = False
    for skills_dir in args.skills:
        try:
            (uninstall_skill if args.uninstall else install_skill)(skills_dir)
        except Exception as e:
            failed = True
            print('[error]   %s' % e)
    for rules_dir in args.rules:
        try:
            (uninstall_rule if args.uninstall else install_rule)(rules_dir)
        except Exception as e:
            failed = True
            print('[error]   %s' % e)
    for project in args.project:
        try:
            (uninstall_plugin if args.uninstall else install_plugin)(project)
        except Exception as e:
            failed = True
            print('[error]   %s' % e)

    if not args.uninstall:
        if IS_WIN and args.skills:
            _check_python_deps()
        if args.project:
            print('插件需随工程编辑器目标一起编译（打开 .uproject 时按提示重建，或用 Build.bat <工程>Editor Win64 Development）。')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
