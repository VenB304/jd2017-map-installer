from pathlib import Path

path = Path(r'c:\Github\jd2017-map-installer\jd2017_installer\installers\game_writer.py')
text = path.read_text(encoding='utf-8')

# The bad replacement was this:
bad_str = '''\t\t\t<SceneConfigs activeSceneConfig="0" />
def write_game_files(*args, **kwargs): pass
def clean_orphaned_map_files(*args, **kwargs): pass
def is_map_installed(*args, **kwargs): return False
def uninstall_map(*args, **kwargs): pass


def generate_all_scenes(build_dir: Path, codename: str, num_coach: int = 1) -> dict[str, Path]:'''

good_str = '''\t\t</sceneConfigs>
\t</Scene>
</root>""", encoding="utf-8")


def write_game_files(*args, **kwargs): pass
def clean_orphaned_map_files(*args, **kwargs): pass
def is_map_installed(*args, **kwargs): return False
def uninstall_map(*args, **kwargs): pass


def generate_all_scenes(output_root: Path, codename: str, num_coach: int) -> dict[str, Path]:'''

if bad_str in text:
    text = text.replace(bad_str, good_str)
    path.write_text(text, encoding='utf-8')
    print("Fixed game_writer.py")
else:
    print("Could not find the bad string in game_writer.py")
