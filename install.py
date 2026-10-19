#!/usr/bin/env python
"""
ue-editor 安装器 - 把本仓库的 Skill 与 AgentTools 插件链接到 Agent 的 Skill 目录和 UE 工程。

用法:
  python install.py --skills <Skill目录> [--skills ...] --project <工程目录或.uproject> [--project ...]
  python install.py --uninstall --skills <Skill目录> --project <工程目录>
  python install.py                                   不带参数时交互输入

链接方式（Windows 用目录联接 junction，无需管理员；其它系统用符号链接）:
  <Skill目录>/ue-editor                    -> <仓库>/skills/ue-editor
  <工程>/Plugins/AgentTools/Source         -> <仓库>/Plugins/AgentTools/Source
  <工程>/Plugins/AgentTools/AgentTools.uplugin  符号链接，失败时退化为硬链接/复制

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


def install_plugin(project):
    plugin_dir = os.path.join(_project_dir(project), 'Plugins', PLUGIN_NAME)
    if _link_target(plugin_dir) is not None:
        raise RuntimeError('%s 是链接（旧的整目录链接方式），请先删除该链接再安装' % plugin_dir)
    os.makedirs(plugin_dir, exist_ok=True)
    _link_dir(os.path.join(plugin_dir, 'Source'), os.path.join(PLUGIN_SRC, 'Source'))
    _link_file(os.path.join(plugin_dir, UPLUGIN), os.path.join(PLUGIN_SRC, UPLUGIN))


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
    if _link_target(source) != _norm(os.path.join(PLUGIN_SRC, 'Source')):
        print('[skip]    %s 不是本仓库安装的插件' % plugin_dir)
        return
    _remove_link(source)
    for name in os.listdir(plugin_dir):
        path = os.path.join(plugin_dir, name)
        if name in ('Binaries', 'Intermediate') and _link_target(path) is None:
            shutil.rmtree(path)
        elif name == UPLUGIN:
            os.unlink(path)
    if not os.listdir(plugin_dir):
        os.rmdir(plugin_dir)
        print('[remove]  %s' % plugin_dir)
    else:
        print('[remove]  %s 中的链接与编译产物（目录内还有其它文件，已保留）' % plugin_dir)


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
    parser.add_argument('--project', action='append', default=[], help='UE 工程目录或 .uproject 路径，可多次指定')
    parser.add_argument('--uninstall', action='store_true', help='移除本仓库创建的链接与插件目录')
    args = parser.parse_args()

    if not args.skills and not args.project:
        args.skills = _ask('输入 Agent 的 Skill 目录')
        args.project = _ask('输入 UE 工程目录或 .uproject 路径')

    failed = False
    for skills_dir in args.skills:
        try:
            (uninstall_skill if args.uninstall else install_skill)(skills_dir)
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
