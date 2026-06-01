"""Binary generator utilities for JD2017 PC.

Generates binary actor (.act.ckd) files and DASH MPD (.mpd.ckd) descriptors
using exact structural formulas from the UbiArt engine format.
"""

from __future__ import annotations

import logging
from pathlib import Path
from jd2017_installer.installers.ipk_packer import string_id_bytes

logger = logging.getLogger("jd2017.installers.binary_generators")


def generate_actor_ckd(codename: str, texture_name: str) -> bytes:
    """Generate the binary payload of a UbiArt texture actor (.act.ckd) for PC.

    Args:
        codename: The lowercase map name (e.g. 'dontwannaknow').
        texture_name: The texture file basename (e.g. 'dontwannaknow_cover_generic').

    Returns:
        The complete binary content of the .act.ckd file.
    """
    prefix = (
        b'\x00\x00\x00\x01\x00\x00\x00\x00\x3F\x80\x00\x00\x3F\x80\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\xFF\xFF\xFF\xFF\x00\x00\x00\x00\x00\x00\x00\x22\x74\x70\x6C\x5F'
        b'\x6D\x61\x74\x65\x72\x69\x61\x6C\x67\x72\x61\x70\x68\x69\x63\x63'
        b'\x6F\x6D\x70\x6F\x6E\x65\x6E\x74\x32\x64\x2E\x74\x70\x6C\x00\x00'
        b'\x00\x1A\x65\x6E\x67\x69\x6E\x65\x64\x61\x74\x61\x2F\x61\x63\x74'
        b'\x6F\x72\x74\x65\x6D\x70\x6C\x61\x74\x65\x73\x2F\xB4\xA8\x17\xA8'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x72\xB6\x1F\xC5'
        b'\x3F\x80\x00\x00\x3F\x80\x00\x00\x3F\x80\x00\x00\x3F\x80\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\xFF\xFF\xFF\xFF\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00'
        b'\x00\x00\x00\x00'
    )

    tga_filename = f"{texture_name}.tga".encode()
    tga_len = len(tga_filename).to_bytes(4, "big")

    tex_path = f"world/maps/{codename.lower()}/menuart/textures/".encode()
    path_len = len(tex_path).to_bytes(4, "big")

    file_hash = string_id_bytes((tex_path + tga_filename).decode("utf-8"))

    suffix = (
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\xFF\xFF\xFF\xFF\x00\x00\x00\x00\x00\x00\x00\x17\x6D\x75\x6C\x74'
        b'\x69\x74\x65\x78\x74\x75\x72\x65\x5F\x31\x6C\x61\x79\x65\x72\x2E'
        b'\x6D\x73\x68\x00\x00\x00\x18\x77\x6F\x72\x6C\x64\x2F\x5F\x63\x6F'
        b'\x6D\x6D\x6F\x6E\x2F\x6D\x61\x74\x73\x68\x61\x64\x65\x72\x2F\xD7'
        b'\xE7\xD9\xC7\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF'
        b'\xFF\xFF\xFF\xFF\xFF\xFF\xFF\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x3F\x80\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x01'
    )

    return prefix + tga_len + tga_filename + path_len + tex_path + file_hash + suffix


def write_actor_ckd(codename: str, texture_name: str, output_path: Path) -> None:
    """Generate and write a binary actor .act.ckd file.

    Args:
        codename: The lowercase map codename.
        texture_name: The texture file basename (without extension).
        output_path: Output file path.
    """
    data = generate_actor_ckd(codename, texture_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    logger.debug("Generated actor CKD: %s (%d bytes)", output_path.name, len(data))


def generate_autodance_act_ckd(codename: str) -> bytes:
    """Generate the binary payload of a UbiArt autodance actor (.act.ckd) for PC.

    Args:
        codename: The lowercase map name (e.g. 'dontwannaknow').

    Returns:
        The complete binary content of the .act.ckd file.
    """
    prefix = (
        b'\x00\x00\x00\x01\x00\x00\x00\x00\x3F\x80\x00\x00\x3F\x80\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00'
    )
    tpl_filename = f"{codename.lower()}_autodance.tpl".encode()
    tpl_len = len(tpl_filename).to_bytes(4, "big")

    path_str = f"world/maps/{codename.lower()}/autodance/".encode()
    path_len = len(path_str).to_bytes(4, "big")

    file_hash = string_id_bytes((path_str + tpl_filename).decode("utf-8"))
    suffix = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x67\xB8\xBB\x77'

    return prefix + tpl_len + tpl_filename + path_len + path_str + file_hash + suffix


def write_autodance_act_ckd(codename: str, output_path: Path) -> None:
    """Generate and write the autodance actor .act.ckd file.

    Args:
        codename: The lowercase map codename.
        output_path: Output file path.
    """
    data = generate_autodance_act_ckd(codename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    logger.debug("Generated autodance actor CKD: %s (%d bytes)", output_path.name, len(data))


def generate_dance_act_ckd(codename: str) -> bytes:
    """Generate the binary payload of a UbiArt dance timeline actor (.act.ckd) for PC.

    Args:
        codename: The lowercase map name (e.g. 'dontwannaknow').

    Returns:
        The complete binary content of the .act.ckd file.
    """
    prefix = (
        b'\x00\x00\x00\x01\x00\x00\x00\x00\x3F\x80\x00\x00\x3F\x80\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00'
    )
    tpl_filename = f"{codename.lower()}_tml_dance.tpl".encode()
    tpl_len = len(tpl_filename).to_bytes(4, "big")

    path_str = f"world/maps/{codename.lower()}/timeline/".encode()
    path_len = len(path_str).to_bytes(4, "big")

    file_hash = string_id_bytes((path_str + tpl_filename).decode("utf-8"))
    suffix = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x23\x1F\x27\xDE'

    return prefix + tpl_len + tpl_filename + path_len + path_str + file_hash + suffix


def write_dance_act_ckd(codename: str, output_path: Path) -> None:
    """Generate and write the timeline dance actor .act.ckd file.

    Args:
        codename: The lowercase map codename.
        output_path: Output file path.
    """
    data = generate_dance_act_ckd(codename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    logger.debug("Generated timeline dance actor CKD: %s (%d bytes)", output_path.name, len(data))


def generate_karaoke_act_ckd(codename: str) -> bytes:
    """Generate the binary payload of a UbiArt karaoke timeline actor (.act.ckd) for PC.

    Args:
        codename: The lowercase map name (e.g. 'dontwannaknow').

    Returns:
        The complete binary content of the .act.ckd file.
    """
    prefix = (
        b'\x00\x00\x00\x01\x00\x00\x00\x00\x3F\x80\x00\x00\x3F\x80\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00'
    )
    tpl_filename = f"{codename.lower()}_tml_karaoke.tpl".encode()
    tpl_len = len(tpl_filename).to_bytes(4, "big")

    path_str = f"world/maps/{codename.lower()}/timeline/".encode()
    path_len = len(path_str).to_bytes(4, "big")

    file_hash = string_id_bytes((path_str + tpl_filename).decode("utf-8"))
    suffix = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x23\x1F\x27\xDE'

    return prefix + tpl_len + tpl_filename + path_len + path_str + file_hash + suffix


def write_karaoke_act_ckd(codename: str, output_path: Path) -> None:
    """Generate and write the timeline karaoke actor .act.ckd file.

    Args:
        codename: The lowercase map codename.
        output_path: Output file path.
    """
    data = generate_karaoke_act_ckd(codename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    logger.debug("Generated timeline karaoke actor CKD: %s (%d bytes)", output_path.name, len(data))


def generate_videoscoach_act_ckd(codename: str) -> bytes:
    """Generate the binary payload of a UbiArt videoscoach actor (.act.ckd) for PC.

    Args:
        codename: The lowercase map name.

    Returns:
        The complete binary content of the .act.ckd file.
    """
    prefix = (
        b'\x00\x00\x00\x01\x00\x00\x00\x00\x3F\x80\x00\x00\x3F\x80\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'
        b'\x00\x00\x00\x00\x00\x00\x00\x15\x76\x69\x64\x65\x6F\x5F\x70\x6C'
        b'\x61\x79\x65\x72\x5F\x6D\x61\x69\x6E\x2E\x74\x70\x6C\x00\x00\x00'
        b'\x1A\x77\x6F\x72\x6C\x64\x2F\x5F\x63\x6F\x6D\x6D\x6F\x6E\x2F\x76'
        b'\x69\x64\x65\x6F\x73\x63\x72\x65\x65\x6E\x2F\xF5\xD5\xE8\xF2\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x12\x63\xDA\xD9'
    )

    webm_filename = f"{codename.lower()}.webm".encode()
    webm_len = len(webm_filename).to_bytes(4, "big")

    mpd_filename = f"{codename.lower()}.mpd".encode()
    mpd_len = len(mpd_filename).to_bytes(4, "big")

    path_str = f"world/maps/{codename.lower()}/videoscoach/".encode()
    path_len = len(path_str).to_bytes(4, "big")

    file_hash1 = string_id_bytes((path_str + webm_filename).decode("utf-8"))
    file_hash2 = string_id_bytes((path_str + mpd_filename).decode("utf-8"))

    return (
        prefix
        + webm_len + webm_filename
        + path_len + path_str
        + file_hash1
        + b'\x00\x00\x00\x00'
        + mpd_len + mpd_filename
        + path_len + path_str
        + file_hash2
        + b'\x00\x00\x00\x00\x00\x00\x00\x00'
    )


def write_videoscoach_act_ckd(codename: str, output_path: Path) -> None:
    """Generate and write the videoscoach actor .act.ckd file.

    Args:
        codename: The lowercase map codename.
        output_path: Output file path.
    """
    data = generate_videoscoach_act_ckd(codename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    logger.debug("Generated videoscoach actor CKD: %s (%d bytes)", output_path.name, len(data))


def generate_songdesc_act_ckd(codename: str) -> bytes:
    """Generate the binary payload of a UbiArt songdesc actor (.act.ckd) for PC.

    Args:
        codename: The lowercase map name (e.g. 'dontwannaknow').

    Returns:
        The complete binary content of the .act.ckd file.
    """
    prefix = (
        b'\x00\x00\x00\x01\x00\x00\x00\x00\x3F\x80\x00\x00\x3F\x80\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF\x00\x00\x00\x00\x00\x00'
        b'\x00\x0C\x73\x6F\x6E\x67\x64\x65\x73\x63\x2E\x74\x70\x6C'
    )

    path_str = f"world/maps/{codename.lower()}/".encode()
    path_len = len(path_str).to_bytes(4, "big")

    file_hash = string_id_bytes((path_str + b"songdesc.tpl").decode("utf-8"))
    suffix = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\xE0\x7F\xCC\x3F'

    return prefix + path_len + path_str + file_hash + suffix


def write_songdesc_act_ckd(codename: str, output_path: Path) -> None:
    """Generate and write the songdesc actor .act.ckd file.

    Args:
        codename: The lowercase map codename.
        output_path: Output file path.
    """
    data = generate_songdesc_act_ckd(codename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    logger.debug("Generated songdesc actor CKD: %s (%d bytes)", output_path.name, len(data))



def generate_mpd_ckd(codename: str) -> bytes:
    """Generate the binary playback DASH descriptor (.mpd.ckd) for PC.

    Args:
        codename: The map codename (case as used in JMCS URIs).

    Returns:
        The complete binary content of the .mpd.ckd file.
    """
    prefix = (
        b'\x00\x00\x00\x01\x00\x43\x29\x47\xAE\x3F\x80\x00\x00\x00\x00\x00'
        b'\x01\x00\x00\x00\x00\x00\x00\x00\x00\x43\x29\x47\xAE\x00\x00\x00'
        b'\x01\x00\x00\x00\x00\x00\x00\x00\x0A\x76\x69\x64\x65\x6F\x2F\x77'
        b'\x65\x62\x6D\x00\x00\x00\x03\x76\x70\x38\x00\x00\x04\xC0\x00\x00'
        b'\x02\xD0\x00\x00\x00\x00\x00\x00\x00\x01\x01\x01\x00\x00\x00\x04'
        b'\x00\x00\x00\x00\x00\x07\x39\x64'
    )

    def get_quality_bytes(quality: str) -> bytes:
        uri = f"jmcs://jd-contents/{codename}/{codename}_{quality}.webm".encode()
        return len(uri).to_bytes(4, "big") + uri

    low = get_quality_bytes("LOW")
    mid = get_quality_bytes("MID")
    high = get_quality_bytes("HIGH")
    ultra = get_quality_bytes("ULTRA")

    body = (
        prefix
        + low + b'\x00\x00\x00\x00\x00\x00\x02\x4B\x00\x00\x02\x4B\x00\x00\x0D\x5B\x00\x00\x00\x01\x00\x1C\x76\x0E'
        + mid + b'\x00\x00\x00\x00\x00\x00\x02\x4B\x00\x00\x02\x4B\x00\x00\x0D\xBF\x00\x00\x00\x02\x00\x38\xFF\x8E'
        + high + b'\x00\x00\x00\x00\x00\x00\x02\x4B\x00\x00\x02\x4B\x00\x00\x0D\xE1\x00\x00\x00\x03\x00\x70\x94\x6D'
        + ultra + b'\x00\x00\x00\x00\x00\x00\x02\x4B\x00\x00\x02\x4B\x00\x00\x0D\xF2'
    )
    return body


def write_mpd_ckd(codename: str, output_path: Path) -> None:
    """Generate and write a DASH MPD descriptor .mpd.ckd file.

    Args:
        codename: The map codename.
        output_path: Output file path.
    """
    data = generate_mpd_ckd(codename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    logger.debug("Generated MPD CKD: %s (%d bytes)", output_path.name, len(data))
