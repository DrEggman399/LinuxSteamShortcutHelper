from cx_Freeze import setup, Executable

setup(
    name="Linux Steam Shortcut Helper",
    version="0.1.3",
    description="A small PyQt helper application for configuring and quickly adding Non-Steam Shortcuts ",
    url="https://github.com/DrEggman399/LinuxSteamShortcutHelper",
    executables=[Executable("main.py", base="gui")],
)