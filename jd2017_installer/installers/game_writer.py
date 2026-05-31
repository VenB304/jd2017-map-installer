"""JD2017 PC MainScene Generator — programmatic recreation of Augusto's scene maker.

Generates all required UbiArt engine configuration files for Just Dance 2017 PC
from the cooked CKD format directly. Writes .isc.ckd, .tpl.ckd, .stape.ckd,
and .act.ckd files into the standard cache/itf_cooked/pc/ directory tree.

Credits:
- AugustoDoidin: Original PC_MainScene_Maker_by_AugustoDoidin.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from jd2017_installer.installers.binary_generators import (
    write_mpd_ckd,
)

logger = logging.getLogger("jd2017.installers.game_writer")

# Engine version used in JD2017 PC ISC files
_ENGINE_VERSION = "253653"


def setup_dirs(output_root: Path, codename: str) -> dict[str, Path]:
    """Create the standard JD2017 PC directory structure and return key paths.

    Args:
        output_root: The root output directory (e.g. output/codename_pc/).
        codename: The lowercase map codename.

    Returns:
        Dictionary mapping subsystem names to their Path objects.
    """
    name = codename.lower()
    cache_base = output_root / "cache" / "itf_cooked" / "pc" / "world" / "maps" / name
    world_base = output_root / "world" / "maps" / name

    paths = {
        "cache_root": cache_base,
        "cache_audio": cache_base / "audio",
        "cache_autodance": cache_base / "autodance",
        "cache_cinematics": cache_base / "cinematics",
        "cache_graph": cache_base / "graph",
        "cache_menuart": cache_base / "menuart",
        "cache_menuart_textures": cache_base / "menuart" / "textures",
        "cache_menuart_actors": cache_base / "menuart" / "actors",
        "cache_timeline": cache_base / "timeline",
        "cache_pictos": cache_base / "timeline" / "pictos",
        "cache_videoscoach": cache_base / "videoscoach",
        "world_root": world_base,
        "world_audio": world_base / "audio",
        "world_autodance": world_base / "autodance",
        "world_timeline_moves": world_base / "timeline" / "moves" / "wiiu",
        "world_videoscoach": world_base / "videoscoach",
        "world_menuart": world_base / "menuart",
        "world_menuart_textures": world_base / "menuart" / "textures",
    }

    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    return paths


def write_audio_files(paths: dict[str, Path], codename: str) -> None:
    """Write audio subsystem CKD files (.stape.ckd, _audio.isc.ckd, _sequence.tpl.ckd)."""
    name = codename.lower()
    cache_audio = paths["cache_audio"]

    # .stape.ckd
    stape = {
        "__class": "Tape",
        "Clips": [],
        "TapeClock": 0,
        "TapeBarCount": 1,
        "FreeResourcesAfterPlay": 0,
        "MapName": codename,
    }
    (cache_audio / f"{name}.stape.ckd").write_text(
        json.dumps(stape, ensure_ascii=True), encoding="utf-8"
    )

    # _audio.isc.ckd
    (cache_audio / f"{name}_audio.isc.ckd").write_text(f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<root>
\t<Scene ENGINE_VERSION="{_ENGINE_VERSION}" GRIDUNIT="0.500000" DEPTH_SEPARATOR="0" NEAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" FAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" viewFamily="0">
\t\t<ACTORS NAME="Actor">
\t\t\t<Actor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="MusicTrack" MARKER="" POS2D="1.125962 -0.418641" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="world/maps/{name}/audio/{name}_musictrack.tpl">
\t\t\t\t<COMPONENTS NAME="MusicTrackComponent">
\t\t\t\t\t<MusicTrackComponent />
\t\t\t\t</COMPONENTS>
\t\t\t</Actor>
\t\t</ACTORS>
\t\t<ACTORS NAME="Actor">
\t\t\t<Actor RELATIVEZ="0.000001" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_sequence" MARKER="" POS2D="-0.006158 -0.006158" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="world/maps/{name}/audio/{name}_sequence.tpl">
\t\t\t\t<COMPONENTS NAME="TapeCase_Component">
\t\t\t\t\t<TapeCase_Component />
\t\t\t\t</COMPONENTS>
\t\t\t</Actor>
\t\t</ACTORS>
\t\t<sceneConfigs>
\t\t\t<SceneConfigs activeSceneConfig="0" />
\t\t</sceneConfigs>
\t</Scene>
</root>
""", encoding="utf-8")

    # _sequence.tpl.ckd
    seq_tpl = {
        "__class": "Actor_Template",
        "WIP": 0, "LOWUPDATE": 0, "UPDATE_LAYER": 0,
        "PROCEDURAL": 0, "STARTPAUSED": 0, "FORCEISENVIRONMENT": 0,
        "COMPONENTS": [{
            "__class": "TapeCase_Template",
            "TapesRack": [{
                "__class": "TapeGroup",
                "Entries": [{
                    "__class": "TapeEntry",
                    "Label": "TML_Sequence",
                    "Path": f"world/maps/{name}/audio/{name}.stape"
                }]
            }]
        }]
    }
    (cache_audio / f"{name}_sequence.tpl.ckd").write_text(
        json.dumps(seq_tpl, ensure_ascii=True), encoding="utf-8"
    )


def write_cinematics_files(paths: dict[str, Path], codename: str) -> None:
    """Write cinematics subsystem CKD files."""
    name = codename.lower()
    cache_cine = paths["cache_cinematics"]

    # _mainsequence.tape.ckd
    tape = {
        "__class": "Tape",
        "Clips": [],
        "TapeClock": 0,
        "TapeBarCount": 1,
        "FreeResourcesAfterPlay": 0,
        "MapName": codename,
    }
    (cache_cine / f"{name}_mainsequence.tape.ckd").write_text(
        json.dumps(tape, ensure_ascii=True), encoding="utf-8"
    )

    # _cine.isc.ckd
    (cache_cine / f"{name}_cine.isc.ckd").write_text(f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<root>
\t<Scene ENGINE_VERSION="{_ENGINE_VERSION}" GRIDUNIT="0.500000" DEPTH_SEPARATOR="0" NEAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" FAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" viewFamily="0">
\t\t<ACTORS NAME="Actor">
\t\t\t<Actor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_MainSequence" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="world/maps/{name}/cinematics/{name}_mainsequence.tpl">
\t\t\t\t<COMPONENTS NAME="MasterTape">
\t\t\t\t\t<MasterTape />
\t\t\t\t</COMPONENTS>
\t\t\t</Actor>
\t\t</ACTORS>
\t\t<sceneConfigs>
\t\t\t<SceneConfigs activeSceneConfig="0" />
\t\t</sceneConfigs>
\t</Scene>
</root>""", encoding="utf-8")

    # _mainsequence.tpl.ckd
    cine_tpl = {
        "__class": "Actor_Template",
        "WIP": 0, "LOWUPDATE": 0, "UPDATE_LAYER": 0,
        "PROCEDURAL": 0, "STARTPAUSED": 0, "FORCEISENVIRONMENT": 0,
        "COMPONENTS": [{
            "__class": "MasterTape_Template",
            "TapesRack": [{
                "__class": "TapeGroup",
                "Entries": [{
                    "__class": "TapeEntry",
                    "Label": "master",
                    "Path": f"world/maps/{name}/cinematics/{name}_mainsequence.tape"
                }]
            }]
        }]
    }
    (cache_cine / f"{name}_mainsequence.tpl.ckd").write_text(
        json.dumps(cine_tpl, ensure_ascii=True), encoding="utf-8"
    )


def write_graph_files(paths: dict[str, Path], codename: str) -> None:
    """Write graph subsystem ISC file."""
    name = codename.lower()
    (paths["cache_graph"] / f"{name}_graph.isc.ckd").write_text(f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<root>
\t<Scene ENGINE_VERSION="{_ENGINE_VERSION}" GRIDUNIT="0.500000" DEPTH_SEPARATOR="0" NEAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" FAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" viewFamily="0">
\t\t<ACTORS NAME="Actor">
\t\t\t<Actor RELATIVEZ="10.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="Camera_JD_Dummy" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="enginedata/actortemplates/tpl_emptyactor.tpl" />
\t\t</ACTORS>
\t\t<sceneConfigs>
\t\t\t<SceneConfigs activeSceneConfig="0" />
\t\t</sceneConfigs>
\t</Scene>
</root>""", encoding="utf-8")


def _build_menuart_actor_block(codename: str, art_name: str,
                                scale: str = "0.300000 0.300000",
                                pos2d: str = "0.000000 0.000000",
                                anchor_sel: str = "1",
                                disable_shadow: str = "4294967295") -> str:
    """Build a single MenuArt actor XML block for a texture asset."""
    name = codename.lower()
    return f"""\t\t<ACTORS NAME="Actor">
\t\t\t<Actor RELATIVEZ="0.000000" SCALE="{scale}" xFLIPPED="0" USERFRIENDLY="{codename}_{art_name}" MARKER="" POS2D="{pos2d}" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="enginedata/actortemplates/tpl_materialgraphiccomponent2d.tpl">
\t\t\t\t<COMPONENTS NAME="MaterialGraphicComponent">
\t\t\t\t\t<MaterialGraphicComponent colorComputerTagId="0" renderInTarget="0" disableLight="0" disableShadow="{disable_shadow}" AtlasIndex="0" customAnchor="0.000000 0.000000" SinusAmplitude="0.000000 0.000000 0.000000" SinusSpeed="1.000000" AngleX="0.000000" AngleY="0.000000">
\t\t\t\t\t\t<PrimitiveParameters>
\t\t\t\t\t\t\t<GFXPrimitiveParam colorFactor="1.000000 1.000000 1.000000 1.000000">
\t\t\t\t\t\t\t\t<ENUM NAME="gfxOccludeInfo" SEL="0" />
\t\t\t\t\t\t\t</GFXPrimitiveParam>
\t\t\t\t\t\t</PrimitiveParameters>
\t\t\t\t\t\t<ENUM NAME="anchor" SEL="{anchor_sel}" />
\t\t\t\t\t\t<material>
\t\t\t\t\t\t\t<GFXMaterialSerializable ATL_Channel="0" ATL_Path="" shaderPath="world/_common/matshader/multitexture_1layer.msh" stencilTest="0" alphaTest="4294967295" alphaRef="4294967295">
\t\t\t\t\t\t\t\t<textureSet>
\t\t\t\t\t\t\t\t\t<GFXMaterialTexturePathSet diffuse="world/maps/{name}/menuart/textures/{name}_{art_name}.tga" back_light="" normal="" separateAlpha="" diffuse_2="" back_light_2="" anim_impostor="" diffuse_3="" diffuse_4="" />
\t\t\t\t\t\t\t\t</textureSet>
\t\t\t\t\t\t\t\t<materialParams>
\t\t\t\t\t\t\t\t\t<GFXMaterialSerializableParam Reflector_factor="0.000000" />
\t\t\t\t\t\t\t\t</materialParams>
\t\t\t\t\t\t\t</GFXMaterialSerializable>
\t\t\t\t\t\t</material>
\t\t\t\t\t\t<ENUM NAME="oldAnchor" SEL="{anchor_sel}" />
\t\t\t\t\t</MaterialGraphicComponent>
\t\t\t\t</COMPONENTS>
\t\t\t</Actor>
\t\t</ACTORS>"""


def write_menuart_isc(paths: dict[str, Path], codename: str, num_coach: int) -> None:
    """Write the menuart ISC file with actors for all required textures."""
    name = codename.lower()
    actors = []

    # Cover generic
    actors.append(_build_menuart_actor_block(
        codename, "cover_generic", pos2d="266.087555 197.629959"))
    # Cover online
    actors.append(_build_menuart_actor_block(
        codename, "cover_online", pos2d="-150.000000 0.000000"))
    # Album coach
    actors.append(_build_menuart_actor_block(
        codename, "cover_albumcoach", pos2d="738.106323 359.612030", anchor_sel="6"))
    # Album background (single 'b' spelling as per guide.md)
    actors.append(_build_menuart_actor_block(
        codename, "cover_albumbkg", pos2d="1067.972168 201.986328"))
    # Coach textures
    for i in range(1, num_coach + 1):
        actors.append(_build_menuart_actor_block(
            codename, f"coach_{i}",
            scale="0.290211 0.290211", pos2d="212.784500 663.680176", anchor_sel="6"))
    # Banner background
    actors.append(_build_menuart_actor_block(
        codename, "banner_bkg",
        scale="256.000000 128.000000", pos2d="1487.410156 -32.732918",
        anchor_sel="1", disable_shadow="1"))

    actors_xml = "\n".join(actors)

    (paths["cache_menuart"] / f"{name}_menuart.isc.ckd").write_text(f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<root>
\t<Scene ENGINE_VERSION="{_ENGINE_VERSION}" GRIDUNIT="0.500000" DEPTH_SEPARATOR="0" NEAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" FAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" viewFamily="1">
{actors_xml}
\t\t<sceneConfigs>
\t\t\t<SceneConfigs activeSceneConfig="0" />
\t\t</sceneConfigs>
\t</Scene>
</root>""", encoding="utf-8")



def write_timeline_isc(paths: dict[str, Path], codename: str) -> None:
    """Write timeline ISC and TPL CKD files."""
    name = codename.lower()
    cache_tml = paths["cache_timeline"]

    # TML Dance TPL
    dance_tpl = {
        "__class": "Actor_Template",
        "WIP": 0, "LOWUPDATE": 0, "UPDATE_LAYER": 0,
        "PROCEDURAL": 0, "STARTPAUSED": 0, "FORCEISENVIRONMENT": 0,
        "COMPONENTS": [{
            "__class": "TapeCase_Template",
            "TapesRack": [{
                "__class": "TapeGroup",
                "Entries": [{
                    "__class": "TapeEntry",
                    "Label": "TML_Motion",
                    "Path": f"world/maps/{name}/timeline/{name}_tml_dance.dtape"
                }]
            }]
        }]
    }
    (cache_tml / f"{name}_tml_dance.tpl.ckd").write_text(
        json.dumps(dance_tpl, ensure_ascii=True), encoding="utf-8"
    )

    # TML Karaoke TPL
    karaoke_tpl = {
        "__class": "Actor_Template",
        "WIP": 0, "LOWUPDATE": 0, "UPDATE_LAYER": 0,
        "PROCEDURAL": 0, "STARTPAUSED": 0, "FORCEISENVIRONMENT": 0,
        "COMPONENTS": [{
            "__class": "TapeCase_Template",
            "TapesRack": [{
                "__class": "TapeGroup",
                "Entries": [{
                    "__class": "TapeEntry",
                    "Label": "TML_Karaoke",
                    "Path": f"world/maps/{name}/timeline/{name}_tml_karaoke.ktape"
                }]
            }]
        }]
    }
    (cache_tml / f"{name}_tml_karaoke.tpl.ckd").write_text(
        json.dumps(karaoke_tpl, ensure_ascii=True), encoding="utf-8"
    )

    # TML ISC
    (cache_tml / f"{name}_tml.isc.ckd").write_text(f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<root>
\t<Scene ENGINE_VERSION="{_ENGINE_VERSION}" GRIDUNIT="0.500000" DEPTH_SEPARATOR="0" NEAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" FAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" viewFamily="0">
\t\t<ACTORS NAME="Actor">
\t\t\t<Actor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_TML_Dance" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="world/maps/{name}/timeline/{name}_tml_dance.tpl">
\t\t\t\t<COMPONENTS NAME="TapeCase_Component">
\t\t\t\t\t<TapeCase_Component />
\t\t\t\t</COMPONENTS>
\t\t\t</Actor>
\t\t</ACTORS>
\t\t<ACTORS NAME="Actor">
\t\t\t<Actor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_TML_Karaoke" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="world/maps/{name}/timeline/{name}_tml_karaoke.tpl">
\t\t\t\t<COMPONENTS NAME="TapeCase_Component">
\t\t\t\t\t<TapeCase_Component />
\t\t\t\t</COMPONENTS>
\t\t\t</Actor>
\t\t</ACTORS>
\t\t<sceneConfigs>
\t\t\t<SceneConfigs activeSceneConfig="0" />
\t\t</sceneConfigs>
\t</Scene>
</root>""", encoding="utf-8")


def write_videoscoach_files(paths: dict[str, Path], codename: str) -> None:
    """Write videoscoach ISC and MPD CKD files."""
    name = codename.lower()
    cache_vc = paths["cache_videoscoach"]

    # Video ISC
    (cache_vc / f"{name}_video.isc.ckd").write_text(f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<root>
\t<Scene ENGINE_VERSION="{_ENGINE_VERSION}" GRIDUNIT="0.500000" DEPTH_SEPARATOR="0" NEAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" FAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" viewFamily="0">
\t\t<ACTORS NAME="Actor">
\t\t\t<Actor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_VideoCoach" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="world/maps/{name}/videoscoach/{name}_videoscoach.tpl">
\t\t\t\t<COMPONENTS NAME="PleoComponent">
\t\t\t\t\t<PleoComponent />
\t\t\t\t</COMPONENTS>
\t\t\t</Actor>
\t\t</ACTORS>
\t\t<sceneConfigs>
\t\t\t<SceneConfigs activeSceneConfig="0" />
\t\t</sceneConfigs>
\t</Scene>
</root>""", encoding="utf-8")

    # Video TPL
    video_tpl = {
        "__class": "Actor_Template",
        "WIP": 0, "LOWUPDATE": 0, "UPDATE_LAYER": 0,
        "PROCEDURAL": 0, "STARTPAUSED": 0, "FORCEISENVIRONMENT": 0,
        "COMPONENTS": [{
            "__class": "PleoComponent_Template",
            "video": f"world/maps/{name}/videoscoach/{name}.vp8",
            "dashMPD": f"world/maps/{name}/videoscoach/{name}.mpd",
            "channelID": ""
        }]
    }
    (cache_vc / f"{name}_videoscoach.tpl.ckd").write_text(
        json.dumps(video_tpl, ensure_ascii=True), encoding="utf-8"
    )

    # MPD CKD (binary DASH descriptor)
    write_mpd_ckd(codename, cache_vc / f"{name}.mpd.ckd")


def write_autodance_files(paths: dict[str, Path], codename: str) -> None:
    """Write autodance subsystem CKD files."""
    name = codename.lower()
    cache_ad = paths["cache_autodance"]

    # Autodance ISC
    (cache_ad / f"{name}_autodance.isc.ckd").write_text(f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<root>
\t<Scene ENGINE_VERSION="{_ENGINE_VERSION}" GRIDUNIT="0.500000" DEPTH_SEPARATOR="0" NEAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" FAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" viewFamily="0">
\t\t<ACTORS NAME="Actor">
\t\t\t<Actor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_autodance" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="world/maps/{name}/autodance/{name}_autodance.tpl">
\t\t\t\t<COMPONENTS NAME="JD_AutodanceComponent">
\t\t\t\t\t<JD_AutodanceComponent />
\t\t\t\t</COMPONENTS>
\t\t\t</Actor>
\t\t</ACTORS>
\t\t<sceneConfigs>
\t\t\t<SceneConfigs activeSceneConfig="0" />
\t\t</sceneConfigs>
\t</Scene>
</root>""", encoding="utf-8")


def write_main_scene_isc(paths: dict[str, Path], codename: str) -> None:
    """Write the root main scene ISC file that ties all subsystems together."""
    name = codename.lower()
    cache_root = paths["cache_root"]

    (cache_root / f"{name}_main_scene.isc.ckd").write_text(f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<root>
\t<Scene ENGINE_VERSION="{_ENGINE_VERSION}" GRIDUNIT="2.000000" DEPTH_SEPARATOR="0" NEAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" FAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" viewFamily="0">
\t\t<ACTORS NAME="SubSceneActor">
\t\t\t<SubSceneActor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_AUDIO" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="enginedata/actortemplates/subscene.tpl" RELATIVEPATH="world/maps/{name}/audio/{name}_audio.isc" EMBED_SCENE="0" IS_SINGLE_PIECE="0" ZFORCED="1" DIRECT_PICKING="1" />
\t\t</ACTORS>
\t\t<ACTORS NAME="SubSceneActor">
\t\t\t<SubSceneActor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_CINE" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="enginedata/actortemplates/subscene.tpl" RELATIVEPATH="world/maps/{name}/cinematics/{name}_cine.isc" EMBED_SCENE="0" IS_SINGLE_PIECE="0" ZFORCED="1" DIRECT_PICKING="1" />
\t\t</ACTORS>
\t\t<ACTORS NAME="SubSceneActor">
\t\t\t<SubSceneActor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_GRAPH" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="enginedata/actortemplates/subscene.tpl" RELATIVEPATH="world/maps/{name}/graph/{name}_graph.isc" EMBED_SCENE="0" IS_SINGLE_PIECE="0" ZFORCED="1" DIRECT_PICKING="1" />
\t\t</ACTORS>
\t\t<ACTORS NAME="SubSceneActor">
\t\t\t<SubSceneActor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_TML" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="enginedata/actortemplates/subscene.tpl" RELATIVEPATH="world/maps/{name}/timeline/{name}_tml.isc" EMBED_SCENE="0" IS_SINGLE_PIECE="0" ZFORCED="1" DIRECT_PICKING="1" />
\t\t</ACTORS>
\t\t<ACTORS NAME="SubSceneActor">
\t\t\t<SubSceneActor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_VIDEO" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="enginedata/actortemplates/subscene.tpl" RELATIVEPATH="world/maps/{name}/videoscoach/{name}_video.isc" EMBED_SCENE="0" IS_SINGLE_PIECE="0" ZFORCED="1" DIRECT_PICKING="1" />
\t\t</ACTORS>
\t\t<ACTORS NAME="SubSceneActor">
\t\t\t<SubSceneActor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_AUTODANCE" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="enginedata/actortemplates/subscene.tpl" RELATIVEPATH="world/maps/{name}/autodance/{name}_autodance.isc" EMBED_SCENE="0" IS_SINGLE_PIECE="0" ZFORCED="1" DIRECT_PICKING="1" />
\t\t</ACTORS>
\t\t<ACTORS NAME="SubSceneActor">
\t\t\t<SubSceneActor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_MENUART" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="enginedata/actortemplates/subscene.tpl" RELATIVEPATH="world/maps/{name}/menuart/{name}_menuart.isc" EMBED_SCENE="0" IS_SINGLE_PIECE="0" ZFORCED="1" DIRECT_PICKING="1" />
\t\t</ACTORS>
\t\t<ACTORS NAME="Actor">
\t\t\t<Actor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}_SongDesc" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="world/maps/{name}/songdesc.tpl">
\t\t\t\t<COMPONENTS NAME="JD_SongDescComponent">
\t\t\t\t\t<JD_SongDescComponent />
\t\t\t\t</COMPONENTS>
\t\t\t</Actor>
\t\t</ACTORS>
\t\t<sceneConfigs>
\t\t\t<SceneConfigs activeSceneConfig="0" />
\t\t</sceneConfigs>
\t</Scene>
</root>""", encoding="utf-8")

    (cache_root / f"{name}_main_scene.sgs.ckd").write_text(
        'S{"settings":{"__class":"JD_MapSceneConfig","Pause_Level":6,"name":"","type":1,"musicscore":2,"soundContext":"","hud":0,"phoneTitleLocId":4294967295,"phoneImage":""}}',
        encoding="utf-8"
    )

def write_game_files(*args, **kwargs): pass
def clean_orphaned_map_files(*args, **kwargs): pass
def is_map_installed(*args, **kwargs): return False
def uninstall_map(*args, **kwargs): pass


def generate_all_scenes(output_root: Path, codename: str, num_coach: int = 1) -> dict[str, Path]:
    """Generate the complete PC MainScene directory tree for a map.

    This is the main entry point for scene generation, equivalent to
    running PC_MainScene_Maker_by_AugustoDoidin.py.

    Args:
        output_root: Root output directory.
        codename: Map codename (mixed case preserved for USERFRIENDLY fields).
        num_coach: Number of coaches (1-4).

    Returns:
        Dictionary of created directory paths.
    """
    logger.info("Generating PC MainScene for '%s' (%d coaches)", codename, num_coach)

    paths = setup_dirs(output_root, codename)

    write_audio_files(paths, codename)
    write_cinematics_files(paths, codename)
    write_graph_files(paths, codename)
    write_timeline_isc(paths, codename)
    write_videoscoach_files(paths, codename)
    write_autodance_files(paths, codename)
    write_menuart_isc(paths, codename, num_coach)
    write_main_scene_isc(paths, codename)

    logger.info("PC MainScene generation complete for '%s'", codename)
    return paths
