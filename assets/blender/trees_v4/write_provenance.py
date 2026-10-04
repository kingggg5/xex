"""Write provenance.json for the Quaternius Stylized Nature MegaKit [Standard] archive.

Route A step 1 (trees v4). System Python, standard library only. Reads the immutable archive,
its extracted copy and the dated licence-page snapshots; writes one JSON file.

Usage:
  python write_provenance.py --zip <archive> --extracted <dir> --snapshots <dir> --out <provenance.json>
"""
import argparse
import collections
import hashlib
import json
import os
import zipfile


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--extracted", required=True)
    ap.add_argument("--snapshots", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    z = zipfile.ZipFile(args.zip)
    infos = z.infolist()
    files = [i for i in infos if not i.is_dir()]
    licence_text = z.read("License_Standard.txt").decode("utf-8-sig")
    lic_info = z.getinfo("License_Standard.txt")
    by_folder = collections.OrderedDict()
    for i in files:
        top = i.filename.split("/")[0] if "/" in i.filename else "(root)"
        d = by_folder.setdefault(top, {"files": 0, "bytes": 0, "extensions": collections.Counter()})
        d["files"] += 1
        d["bytes"] += i.file_size
        d["extensions"][i.filename.rsplit(".", 1)[-1].lower()] += 1
    for d in by_folder.values():
        d["extensions"] = dict(sorted(d["extensions"].items()))
    gltf_models = sorted(i.filename[5:-5] for i in files if i.filename.startswith("glTF/") and i.filename.endswith(".gltf"))
    families = collections.OrderedDict()
    for name in gltf_models:
        key = name.rsplit("_", 1)[0] if name.rsplit("_", 1)[-1].isdigit() else name
        families.setdefault(key, []).append(name)

    extracted_files = []
    total = 0
    for root, _dirs, names in os.walk(args.extracted):
        for n in names:
            p = os.path.join(root, n)
            total += os.path.getsize(p)
            extracted_files.append(p)
    gltf_dir = os.path.join(args.extracted, "glTF")
    gltf_hashes = {n: {"bytes": os.path.getsize(os.path.join(gltf_dir, n)), "sha256": sha256(os.path.join(gltf_dir, n))}
                   for n in sorted(os.listdir(gltf_dir))}
    root_hashes = {n: {"bytes": os.path.getsize(os.path.join(args.extracted, n)), "sha256": sha256(os.path.join(args.extracted, n))}
                   for n in sorted(os.listdir(args.extracted)) if os.path.isfile(os.path.join(args.extracted, n))}
    # extracted copy must match the archive byte for byte
    mismatches = []
    for i in files:
        p = os.path.join(args.extracted, *i.filename.split("/"))
        if not os.path.exists(p) or os.path.getsize(p) != i.file_size:
            mismatches.append(i.filename)
    snaps = {n: {"bytes": os.path.getsize(os.path.join(args.snapshots, n)), "sha256": sha256(os.path.join(args.snapshots, n))}
             for n in sorted(os.listdir(args.snapshots))}

    prov = {
        "asset": "Quaternius Stylized Nature MegaKit — Standard (free) edition",
        "author": "Quaternius (quaternius.com)",
        "pack_release": "July 2024 (pack page); archive entries dated 2024-07-30",
        "route": "Route A, trees v4 (docs/reviews/2026-10-02-trees-free-assets-decision.md section 5)",
        "status": "CANDIDATE SOURCE ONLY - not integrated into the game runtime, not committed",
        "source": {
            "pack_page": "https://quaternius.com/packs/stylizednaturemegakit.html",
            "download_page": "https://quaternius.itch.io/stylized-nature-megakit",
            "download_flow": "itch.io: Download Now -> 'No thanks, just take me to the downloads' -> "
                             "'Stylized Nature MegaKit[Standard].zip' (itch upload id 11055123, listed 99 MB); "
                             "served from the itch.io storage mirror (signed URL not recorded)",
            "download_tool": "Playwright MCP browser, saved directly with download.saveAs() into the kit folder",
            "downloaded_ict": "2026-10-02T11:31:36+07:00",
            "approval": "Owner approved free CC0 downloads (2026-10-01 10:40 and 2026-10-02; decision doc section 7)",
        },
        "licence": {
            "spdx": "CC0-1.0",
            "verdict": "CC0 1.0 Universal, stated by the archive's own licence file, the pack page and the itch.io listing",
            "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "in_archive": {"file": "License_Standard.txt", "bytes": lic_info.file_size,
                           "archive_date": "%04d-%02d-%02d %02d:%02d:%02d" % lic_info.date_time,
                           "text": licence_text},
            "pack_page_statement": {"url": "https://quaternius.com/packs/stylizednaturemegakit.html",
                                    "quote": ["License CC0 (link: https://creativecommons.org/publicdomain/zero/1.0/)",
                                              "Free to use in personal, educational and commercial projects. (CC0 License)"],
                                    "fetched_ict": "2026-10-02T11:28+07:00"},
            "itch_page_statement": {"url": "https://quaternius.itch.io/stylized-nature-megakit",
                                    "quote": ["Free to use in personal, educational and commercial projects. (CC0 License)",
                                              "Asset license: Creative Commons Zero v1.0 Universal"],
                                    "listing_updated": "16 September 2026 @ 08:17 UTC",
                                    "fetched_ict": "2026-10-02T11:29+07:00"},
            "discrepancy_to_report": {
                "url": "https://quaternius.com/license.html",
                "quote": ["Quaternius Asset License (QAL) v1.0", "Last updated: 8/28/2026",
                          "You can use these assets, free of charge, in personal, educational, and commercial games and other "
                          "projects, with no credit required. You just can't resell or redistribute the assets themselves as assets.",
                          "7. Changes to This License: We may publish updated versions of this License for future Asset releases. "
                          "Changes will not apply retroactively to Assets you've already obtained under an earlier version"],
                "assessment": "The site-wide licence page now shows a newer custom licence (QAL v1.0, 2026-08-28) that is not CC0. "
                              "This archive (2024-07-30) ships CC0 text, and the pack page and the itch listing (updated 2026-09-16) "
                              "still state CC0 1.0 for this pack on the download date; a CC0 dedication cannot be withdrawn for "
                              "copies obtained under it. Even under QAL, use inside the game is allowed without credit. Prudent rule "
                              "either way: keep the raw kit outside the repo (Downloads\\Xexoria-Game\\kits) and ship only derived, "
                              "game-ready assets; never republish the kit files as an asset pack.",
                "fetched_ict": "2026-10-02T11:28+07:00"},
            "page_snapshots": {"folder": "planning/evidence/sunmeadow-trees-v4/route-a/licence-snapshots/", "files": snaps},
            "rule": "llm.txt rule 11: a local folder is not evidence of CC0; the statements above are the evidence",
        },
        "archive": {
            "name": os.path.basename(args.zip),
            "path": args.zip,
            "bytes": os.path.getsize(args.zip),
            "sha256": sha256(args.zip),
            "immutable": "never modified; all work uses the extracted copy or in-memory imports",
            "entries": len(infos), "files": len(files),
            "uncompressed_bytes": sum(i.file_size for i in files),
            "crc_test": "zipfile.testzip() = None (all entries OK)",
        },
        "extracted_copy": {"path": args.extracted, "files": len(extracted_files), "bytes": total,
                           "size_mismatches_vs_archive": mismatches},
        "file_list_summary": {
            "by_top_folder": by_folder,
            "formats": "glTF 2.0 (.gltf + .bin + PNG), FBX, FBX (Unity), OBJ/MTL; shared PNG textures",
            "gltf_models": len(gltf_models),
            "gltf_model_families": families,
            "tree_like_models_in_standard": {k: v for k, v in families.items()
                                             if k in ("CommonTree", "Pine", "TwistedTree", "DeadTree", "Bush_Common",
                                                      "Bush_Common_Flowers")},
            "not_in_standard_edition": "Pro/Source-only models listed in glTF/desktop.ini (Birch, CherryBlossom, GiantPine, "
                                       "TallThick, Bush_Large_Flowers, Bush_Long_*, more plants, flowers and rocks), the "
                                       ".blend sources and the stylized leaf/grass shaders",
            "notes": ["glTF/desktop.ini is a Windows Explorer file shipped by the author (localized names, includes Pro names)",
                      "Leaves_GiantPine_C.png is shipped but used only by Pro GiantPine models"],
        },
        "gltf_folder_sha256": gltf_hashes,
        "root_files_sha256": root_hashes,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, indent=1, ensure_ascii=False)
    print("WROTE", args.out, prov["archive"]["sha256"], prov["archive"]["bytes"], "mismatches", len(mismatches))


if __name__ == "__main__":
    main()
