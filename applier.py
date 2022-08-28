#!/usr/bin/env python

import os
import types
import sys
import argparse
import subprocess
import shutil
from typing import Generator

"""
Script to apply modules that have various third-party or patch dependencies.

Shell instructions like mkdir, rm, and git are run via subprocess instead of using
a dedicated Python module because I'm lazy.
"""


TEMP = "temp"
MODULES_FORMAT = "{}/modules"
THIRDPARTY_FORMAT = "{}/thirdparty"
PATCHES_FORMAT = "{}/patches"

MODULES_FILE = "modules_file.txt"
APPLIED_MODULES_FILE = ".applied_modules"

HELPER_SCRIPT_FILE = "helper_script.py"
HELPER_SCRIPT_RUN_FUNC = "run"


class DirUtil(object):
    """
    Directory-related utilities.
    """

    @staticmethod
    def dir_exists(path: str) -> bool:
        return os.path.isdir(path)

    @staticmethod
    def file_exists(path: str) -> bool:
        return os.path.isfile(path)

    @staticmethod
    def list_dir(dir: str) -> Generator:
        for dir in os.listdir(os.fsencode(dir)):
            yield os.fsdecode(dir)

    @staticmethod
    def get_godot_dir(args: argparse.Namespace) -> str:
        """
        Actually only gets the directory of this script but is good enough.
        """
        return os.path.dirname(os.path.realpath(__file__))

    @staticmethod
    def mkdir(abs_path: str) -> None:
        """
        This might break if run in a shell that does not have `mkdir` functionality.
        """

        subprocess.run(["mkdir", abs_path])

    @staticmethod
    def rm_rf(abs_path: str) -> None:
        """
        This might break if run in a shell that does not have `rm -rf` functionality.
        Looking at you, cmd.
        """

        subprocess.run(["rm", "-rf", abs_path])

    @staticmethod
    def copy_dirs(from_dir: str, to_dir: str, force: bool) -> list:
        changed_files: list = []
        for dir in DirUtil.list_dir(from_dir):
            formatted_to: str = "{}/{}".format(to_dir, dir)
            shutil.copytree("{}/{}".format(from_dir, dir),
                            formatted_to, dirs_exist_ok=force)

            changed_files.append(formatted_to)

        return changed_files


class GitUtil(object):
    """
    Git-related utilities.
    """

    @staticmethod
    def git_clone(dir: str, url: str, branch: str = "") -> bool:
        """
        Equivalent to:

        ```
        cd <dir>
        git clone <url> OR git clone -b <branch> <url>
        ```
        """

        if not DirUtil.dir_exists(dir):
            return False

        params: list = ["git", "clone", "--recursive"]

        if not branch == "":
            params.append("-b")
            params.append(branch)

        params.append(url)

        subprocess.run(params, cwd=dir)

        return True

    @staticmethod
    def git_restore_dir(dir: str) -> None:
        """
        Equivalent to:

        ```
        git restore .
        ```
        """

        subprocess.run(["git", "restore", "."], cwd=dir)

    @staticmethod
    def apply_patches(patches_dir: str, godot_dir: str) -> None:
        """
        Equivalent to:

        ```
        cd <godot_dir>
        git apply --ignore-space-change --ignore-whitespace <file in patches_dir>
        ```
        """

        for file in DirUtil.list_dir(patches_dir):
            if not file.endswith("patch"):
                continue

            subprocess.run(
                ["git", "apply", "--ignore-space-change", "--ignore-whitespace", "{}/{}".format(patches_dir, file)], cwd=godot_dir)


def execute_helper_script(path: str, args: argparse.Namespace, func_name: str = HELPER_SCRIPT_RUN_FUNC) -> None:
    """
    Ultra dangerous way of executing a module's helper script
    """
    script_file = open("path", "r")

    try:
        code = compile(script_file.read(), path, "exec")

        # The name doesn't really matter, it just needs to be unique
        mod = types.ModuleTypes(path)
        exec(code, mod.__dict__)

        sys.modules[path] = mod

        entrypoint = getattr(mod, func_name)
        if entrypoint is not None:
            entrypoint(DirUtil.get_godot_dir(args))
    except Exception as e:
        print(e)


def apply(args: argparse.Namespace) -> None:
    """
    Clones all directories into a temp folder and copies the modules, copies any
    third-party files, and applies any patches.

    A log of the applied files is stored in the root Godot directory.
    """

    modules_file = args.modules_file
    if not DirUtil.file_exists(modules_file):
        raise Exception("path {} not found".format(modules_file))

    godot_dir = DirUtil.get_godot_dir(args)

    if not DirUtil.dir_exists(godot_dir):
        raise Exception("path {} not found".format(godot_dir))

    if shutil.which("git") is None:
        raise Exception("git command not found")

    temp_dir = "{}/{}".format(godot_dir, TEMP)

    # Always cleanup if there was an error from last time
    if DirUtil.dir_exists(temp_dir):
        DirUtil.rm_rf(temp_dir)

    DirUtil.mkdir(temp_dir)

    if not DirUtil.dir_exists(temp_dir):
        raise Exception(
            "Unable to create temp directory at {}".format(temp_dir))

    modules_file_handle = open(modules_file, "r")

    modules_file_content = modules_file_handle.read()
    for line in modules_file_content.splitlines():
        if line.startswith("#") or len(line) == 0:
            continue

        repo: str = line
        branch: str = ""

        split_line = line.split(" ", 1)
        if len(split_line) > 1:
            repo = split_line[0]
            branch = split_line[1]

        if not GitUtil.git_clone(temp_dir, repo, branch):
            raise Exception("Unable to clone {}".format(line))

    modules_file_handle.close()

    applied_files: list = []

    for dir in DirUtil.list_dir(temp_dir):
        repo_dir = "{}/{}".format(temp_dir, dir)

        modules_dir = MODULES_FORMAT.format(repo_dir)
        if DirUtil.dir_exists(modules_dir):
            applied_files.extend(DirUtil.copy_dirs(modules_dir, MODULES_FORMAT.format(
                godot_dir), force=args.force))

        thirdparty_dir = THIRDPARTY_FORMAT.format(repo_dir)
        if DirUtil.dir_exists(thirdparty_dir):
            applied_files.extend(DirUtil.copy_dirs(thirdparty_dir, THIRDPARTY_FORMAT.format(
                godot_dir), force=args.force))

        patches_dir = PATCHES_FORMAT.format(repo_dir)
        if DirUtil.dir_exists(patches_dir):
            GitUtil.apply_patches(patches_dir, godot_dir)

        helper_script_path = "{}/{}".format(repo_dir, HELPER_SCRIPT_FILE)
        if DirUtil.file_exists(helper_script_path):
            execute_helper_script(helper_script_path, args)

    DirUtil.rm_rf(temp_dir)

    applied_modules_handle = open(APPLIED_MODULES_FILE, "w")

    applied_modules_handle.writelines(file + "\n" for file in applied_files)

    applied_modules_handle.close()


def clean(args: argparse.Namespace) -> None:
    """
    Reads the log file of all applied modules and removes all changes.

    This will NOT unapply any patches.
    """

    if not DirUtil.file_exists(APPLIED_MODULES_FILE):
        raise Exception("{} does not exist".format(APPLIED_MODULES_FILE))

    GitUtil.git_restore_dir(DirUtil.get_godot_dir(args))

    applied_modules_handle = open(APPLIED_MODULES_FILE, "r")

    applied_modules = applied_modules_handle.readlines()
    applied_modules = [s.strip() for s in applied_modules]

    applied_modules_handle.close()

    for dir in applied_modules:
        if not DirUtil.dir_exists(dir):
            print("{} does not exist, skipping".format(dir))
            continue

        DirUtil.rm_rf(dir)

    DirUtil.rm_rf(APPLIED_MODULES_FILE)


def debug_script(args: argparse.Namespace) -> None:
    print(args)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply modules and patches to a Godot repo")
    parser.add_argument("--godot-directory", "-gd",
                        help="Relative path to the Godot repo's root directory", default="./")

    subparsers = parser.add_subparsers()

    debug_parser = subparsers.add_parser(
        "debug", help="Show debug information")
    debug_parser.set_defaults(func=debug_script)

    apply_parser = subparsers.add_parser("apply", help="Apply modules")
    apply_parser.add_argument("--modules-file", type=str, default=MODULES_FILE,
                              help="Path to a file containing paths to module repos")
    apply_parser.add_argument("--force", "-f", type=bool, default=False,
                              help="Whether to overwrite any existing modules or thirdparty files")
    apply_parser.set_defaults(func=apply)

    clean_parser = subparsers.add_parser(
        "clean", help="Clean up applied modules")
    clean_parser.set_defaults(func=clean)

    args = parser.parse_args()

    if not "func" in args:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
