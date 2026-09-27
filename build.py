#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py — Empaquete le projet "House of Laura" dans un ZIP propre,
en verifiant au prealable qu'il ne manque rien.

Utilisation
-----------
    py build.py              construit le ZIP dans archive/
    py build.py --check      verifie l'integrite du projet, ne cree aucun ZIP
    py build.py --no-source  exclut le code source du jeu (ZIP plus leger)
    py build.py --site-only  verifie uniquement le site, en ignorant les builds
                             (utilisable dans le dossier de publication GitHub,
                              qui ne contient volontairement pas les .exe)

Ce que fait le script
---------------------
1. Renomme automatiquement un build mal nomme
   (HouseOfLaura-EP1.exe -> HouseOfLaura-EP1-v1.2.0.exe).
2. Verifie que chaque page et chaque ressource declaree dans project.json
   existe et n'est pas vide, et qu'un build n'a pas ete telecharge a moitie.
3. Verifie que chaque lien de telechargement declare dans project.json est
   bien present dans une page du site (evite de publier un bouton casse).
4. Ecrit un MANIFEST.txt a la racine du ZIP (inventaire + tailles).
5. Compresse en ZIP_DEFLATED niveau 9.

Nommage des builds
------------------
    builds/episode-01/HouseOfLaura-EP1-v1.2.0.exe
    builds/episode-02/HouseOfLaura-EP2-v1.0.0.exe
Le numero d'episode et la version sont toujours dans le NOM DU FICHIER,
jamais dans un suffixe du type "-FINAL" ou "-v2_definitive".
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# --- Constantes ------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent
PROJECT_JSON = ROOT / "project.json"
ARCHIVE_DIR = ROOT / "archive"
MANIFEST_NAME = "MANIFEST.txt"
LINE = "-" * 66

# Fichiers de configuration places a la racine du ZIP.
ROOT_FILES = ("build.py", "README.md", "project.json", ".gitignore")


# --- Affichage -------------------------------------------------------------- #
def info(msg: str) -> None:
    print(f"[i] {msg}")


def ok(msg: str) -> None:
    print(f"[OK] {msg}")


def warn(msg: str) -> None:
    print(f"[!!] {msg}")


def err(msg: str) -> None:
    print(f"[XX] {msg}", file=sys.stderr)


def human_size(n: float) -> str:
    """Octets -> chaine lisible."""
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or unit == "Go":
            return f"{n:.1f} {unit}" if unit != "o" else f"{int(n)} o"
        n /= 1024.0
    return f"{n:.1f} Go"


# --- Chargement du manifeste ------------------------------------------------ #
def load_project() -> dict:
    if not PROJECT_JSON.is_file():
        err(f"project.json introuvable a la racine du projet :\n     {PROJECT_JSON}")
        sys.exit(1)
    try:
        with open(PROJECT_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        err(f"project.json contient du JSON invalide :\n     {exc}")
        sys.exit(1)


# --- Normalisation des noms de builds ---------------------------------------- #
def normalize_build_names(project: dict) -> list[str]:
    """
    Si project.json declare "HouseOfLaura-EP1-v1.2.0.exe" mais que le fichier
    sur disque s'appelle "HouseOfLaura-EP1.exe", on le renomme.
    """
    renames: list[str] = []
    for ep in project.get("episodes", []):
        target = ROOT / str(ep.get("build", ""))
        if target.suffix.lower() != ".exe":
            continue

        version = ep.get("version")
        if target.is_file() and (not version or f"-v{version}" in target.name):
            continue  # deja conforme, rien a faire

        # Nom attendu sans le suffixe de version :
        #   "HouseOfLaura-EP1-v1.2.0"  ->  "HouseOfLaura-EP1"
        base_stem = re.sub(r"-v\d+(?:\.\d+)*$", "", target.stem)

        for candidate in sorted(target.parent.glob(f"{base_stem}.exe")):
            if candidate.resolve() == target.resolve():
                continue
            if target.exists():
                target.unlink()  # remplace une version plus ancienne
            candidate.rename(target)
            renames.append(f"{candidate.name}  ->  {target.name}")
            break
    return renames


# --- Verification ----------------------------------------------------------- #
def verify(project: dict, site_only: bool = False) -> list[str]:
    """
    Verifie l'integrite du projet.
    Retourne la liste des problemes : liste vide = tout est bon.

    site_only=True ignore les builds : pratique dans le dossier de publication
    GitHub, qui ne contient volontairement aucun .exe.
    """
    problems: list[str] = []
    site = project.get("site", {})

    # 1) Pages et ressources requises, plus les images declarees.
    for rel in list(site.get("required", [])) + list(site.get("images", [])):
        p = ROOT / rel
        if not p.is_file():
            problems.append(f"site      : fichier manquant -> {rel}")
        elif p.stat().st_size == 0:
            problems.append(f"site      : fichier vide (0 octet) -> {rel}")

    entry = site.get("entry")
    if entry and not (ROOT / entry).is_file():
        problems.append(f"site      : page d'entree manquante -> {entry}")

    # 2) Chaque page incluse doit exister, et chaque lien interne doit
    #    pointer vers une page reellement presente.
    pages = [p for p in site.get("include", []) if p.endswith(".html")]
    existing = {p for p in pages if (ROOT / p).is_file()}
    for page in sorted(existing):
        html = (ROOT / page).read_text(encoding="utf-8", errors="replace")
        for target in re.findall(r'href="([^"#][^"]*?\.html)"', html):
            if target.startswith(("http://", "https://", "//", "mailto:")):
                continue
            # Une page 404 doit employer des chemins absolus ("/index.html") :
            # elle est servie a n'importe quelle profondeur d'URL, ou des
            # chemins relatifs casseraient. On normalise donc le "/" initial.
            normalized = target.lstrip("/")
            if normalized not in existing:
                problems.append(
                    f"lien      : {page} pointe vers '{target}', "
                    f"qui n'est pas declare dans project.json (site.include)"
                )

    # 3) Builds des episodes.
    declared_ids: set[str] = set()
    for ep in project.get("episodes", []):
        ep_id = str(ep.get("id", "?"))
        declared_ids.add(ep_id)
        if site_only:
            continue  # le dossier de publication ne contient pas les .exe
        rel = ep.get("build")
        if not rel:
            problems.append(f"episode {ep_id} : aucun champ 'build' declare dans project.json")
            continue
        p = ROOT / rel
        if not p.is_file():
            problems.append(
                f"episode {ep_id} : BUILD MANQUANT -> {rel}\n"
                f"            -> place le fichier dans builds/{ep_id}/ avec ce nom exact."
            )
            continue
        size = p.stat().st_size
        if size == 0:
            problems.append(f"episode {ep_id} : BUILD VIDE (0 octet) -> {rel}")
            continue
        min_mb = ep.get("size_min_mb")
        if min_mb and size / (1024 * 1024) < min_mb:
            problems.append(
                f"episode {ep_id} : BUILD SUSPECT -> {rel} ne fait que "
                f"{size / (1024 * 1024):.1f} Mo (minimum attendu : {min_mb} Mo).\n"
                f"            -> telechargement interrompu, recommence le telechargement."
            )

    # 4) Coherence dossiers de builds <-> project.json.
    builds_root = ROOT / "builds"
    if builds_root.is_dir():
        for d in sorted(builds_root.iterdir()):
            if d.is_dir() and d.name not in declared_ids:
                warn(f"le dossier builds/{d.name}/ n'est pas declare dans project.json")

    # 5) Le bouton de telechargement pointe-t-il quelque part ?
    #    Avec un site multi-pages, l'URL peut se trouver dans n'importe
    #    quelle page : on concatene toutes les pages avant de chercher.
    downloads = project.get("downloads", {})
    if existing:
        joined = "\n".join(
            (ROOT / p).read_text(encoding="utf-8", errors="replace") for p in sorted(existing)
        )
        for ep_id, url in downloads.items():
            # Un placeholder n'est pas une erreur : on previent et on continue.
            # Tant que la page itch.io n'existe pas, c'est normal.
            if not url or url.startswith(("REMPLACEZ", "DOWNLOAD_", "VOTRE", "http://exemple")):
                warn(f"lien {ep_id} : download_url est encore un placeholder "
                     f"({url!r}) — pense a le remplacer par ton lien reel.")
                continue
            # En revanche une vraie URL absente du site = bouton casse = erreur.
            if url not in joined:
                problems.append(
                    f"lien {ep_id} : cette URL est declaree dans project.json mais "
                    f"n'apparait dans aucune page du site :\n            {url}\n"
                    f"            -> le bouton de telechargement est casse."
                )
    return problems


# --- Collecte des fichiers -------------------------------------------------- #
def is_excluded(rel: Path, patterns: list[str]) -> bool:
    """Teste un chemin relatif (posix) contre les motifs d'exclusion."""
    posix = rel.as_posix()
    for pattern in patterns:
        if fnmatch.fnmatch(posix, pattern):
            return True
        if fnmatch.fnmatch(posix, pattern.rstrip("/") + "/*"):
            return True
    return False


def matches_any(rel: Path, patterns: list[str]) -> bool:
    """Un chemin correspond-il a au moins un motif d'inclusion ?"""
    posix = rel.as_posix()
    for pattern in patterns:
        if fnmatch.fnmatch(posix, pattern):
            return True
        # "assets" doit inclure "assets/..." et "dossier/assets/...".
        if fnmatch.fnmatch(posix, pattern.rstrip("/") + "/*"):
            return True
    return False


def collect_files(project: dict, include_source: bool) -> list[Path]:
    """Rassemble les fichiers a compresser, sans doublon, dans un ordre lisible."""
    patterns = project.get("exclude", [])
    site = project.get("site", {})
    include = site.get("include", [])
    site_dir = site.get("dir", ".")
    picked: list[Path] = []

    # Repertoires a ne jamais parcourir lors du balayage du site.
    # "builds" et "source" sont ajoutes explicitement plus bas.
    PRUNE = {".git", "archive", "builds", "source", "node_modules", "dist", ".idea", ".vscode"}

    def add(p: Path) -> None:
        if p.is_file() and not is_excluded(p.relative_to(ROOT), patterns):
            picked.append(p)

    # 1) Fichiers de configuration a la racine.
    for name in ROOT_FILES:
        add(ROOT / name)

    # 2) Le site, selectionne par les motifs "site.include".
    base = ROOT / site_dir
    scan_root = base if base.is_dir() else ROOT
    for p in scan_root.rglob("*"):
        if set(p.relative_to(ROOT).parts) & PRUNE:
            continue
        rel = p.relative_to(ROOT)
        if matches_any(rel, include) or matches_any(Path(p.name), include):
            add(p)

    # 3) La documentation, embarquee dans l'archive.
    docs = project.get("docs", {})
    if docs.get("dir"):
        docs_dir = ROOT / docs["dir"]
        docs_include = docs.get("include", ["**/*"])
        if docs_dir.is_dir():
            for p in docs_dir.rglob("*"):
                if matches_any(p.relative_to(ROOT), docs_include):
                    add(p)

    # 4) Les builds declares, un par episode.
    for ep in project.get("episodes", []):
        add(ROOT / str(ep.get("build", "")))

    # 5) Le code source (optionnel).
    src = project.get("source", {})
    if include_source and src.get("enabled", False):
        src_dir = ROOT / src.get("dir", "source")
        if src_dir.is_dir():
            for p in src_dir.rglob("*"):
                add(p)

    # Deduplication en preservant l'ordre.
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in picked:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return sorted(unique, key=lambda x: x.relative_to(ROOT).as_posix())


# --- MANIFEST.txt ----------------------------------------------------------- #
def build_manifest(project: dict, files: list[Path], include_source: bool) -> str:
    name = project.get("project", "Projet")
    version = project.get("version", "0.0.0")
    author = project.get("author", "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    out: list[str] = [
        "=" * 66,
        f"  {name} - Archive de distribution",
        f"  Version globale : v{version}",
    ]
    if author:
        out.append(f"  Cree par        : {author}")
    out += [
        f"  Generee le      : {now}",
        "=" * 66,
        "",
        "MISE EN LIGNE (2 minutes)",
        "-" * 66,
        "  1. Cree un depot vide nomme  house-of-laura  sur github.com",
        "  2. En ligne de commande, dans ce dossier :",
        "",
        "       git init && git branch -M main && git add .",
        "       git commit -m \"House of Laura v1.2.0\"",
        "       git remote add origin https://github.com/TON-PSEUDO/house-of-laura.git",
        "       git push -u origin main",
        "",
        "  3. Settings > Pages > Source : branche  main , dossier  /  (racine)",
        "  4. Le site est en ligne sur :",
        "       https://TON-PSEUDO.github.io/house-of-laura/",
        "",
        "  ATTENTION : n'upload PAS le dossier builds/ depuis le site web de",
        "  GitHub, il contient des .exe de 100 Mo et le push sera refuse.",
        "  Utilise la ligne de commande ci-dessus : .gitignore fait le tri.",
        "",
        "LE SITE (multi-pages)",
        "-" * 66,
        "  index.html          Accueil",
        "  episode-1.html      Le Signal Perdu",
        "  episode-2.html      En preparation",
        "  telechargement.html Le seul bouton de telechargement du site",
        "  assets/             CSS, JS et images, partages par toutes les pages",
        "",
        "  Si tu ajoutes une page, declare-la dans project.json",
        "  (site.include et site.required), sinon build.py ne l'embarque pas.",
        "",
        "CONTENU DE CETTE ARCHIVE",
        "-" * 66,
        "  pages HTML  le site, a la racine : c'est ce que GitHub Pages sert.",
        "  assets/     Images et ressources du site.",
        "  builds/     Les executables des episodes (Windows 10/11).",
    ]
    if include_source:
        out.append("  source/     Le code source du jeu (JavaScript, audio).")
    out += [
        "  docs/       La documentation (nom du depot, ajout d'un episode).",
        "  build.py    Le script qui a genere cette archive.",
        "",
        "EPISODES INCLUS",
        "-" * 66,
    ]
    for ep in project.get("episodes", []):
        rel = str(ep.get("build", "?"))
        p = ROOT / rel
        mark = "OK" if p.is_file() else "MANQUANT"
        size_txt = human_size(p.stat().st_size) if p.is_file() else "-"
        out += [
            f"  [{mark:>7}] Episode {ep.get('number', '?')} - {ep.get('title', '?')}",
            f"            version : v{ep.get('version', '?')}   ({size_txt})",
            f"            fichier : {rel}",
            "",
        ]
    out += ["INVENTAIRE DES FICHIERS", "-" * 66]
    total = 0
    for p in files:
        size = p.stat().st_size
        total += size
        out.append(f"  {human_size(size):>10}  {p.relative_to(ROOT).as_posix()}")
    out += [
        "-" * 66,
        f"  {human_size(total):>10}  TOTAL ({len(files)} fichiers, avant compression)",
        "",
        "Note : les executables necessitent Windows 10 ou 11.",
        "",
    ]
    return "\n".join(out)


# --- Creation du ZIP -------------------------------------------------------- #
def make_zip(project: dict, files: list[Path], include_source: bool) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    # Le nom reprend celui du depot GitHub (champ "repo"), pour que
    # l'archive et le depot portent exactement le meme nom.
    slug = project.get("repo") or "".join(
        c if c.isalnum() else "" for c in project.get("project", "projet")
    )
    zip_name = f"{slug}-v{project.get('version', '0.0.0')}.zip"
    zip_path = ARCHIVE_DIR / zip_name
    if zip_path.exists():
        zip_path.unlink()

    info(f"Compression vers {zip_path.relative_to(ROOT)} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr(MANIFEST_NAME, build_manifest(project, files, include_source).encode("utf-8"))
        for p in files:
            zf.write(p, p.relative_to(ROOT).as_posix())
    return zip_path


# --- Point d'entree --------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Empaqueter le projet House of Laura dans un ZIP propre."
    )
    parser.add_argument("--check", action="store_true",
                        help="verifie l'integrite du projet sans creer de ZIP")
    parser.add_argument("--no-source", action="store_true",
                        help="exclut le code source du jeu du ZIP")
    parser.add_argument("--site-only", action="store_true",
                        help="verifie seulement le site, en ignorant les builds")
    args = parser.parse_args()
    include_source = not args.no_source

    project = load_project()
    info(f"Projet : {project.get('project')} v{project.get('version')}")
    print(LINE)

    # 1) Noms de builds conformes a project.json.
    for line in normalize_build_names(project):
        ok(f"Build renomme : {line}")

    # 2) Verification.
    problems = verify(project, site_only=args.site_only)
    if problems:
        err("VERIFICATION ECHOUEE :")
        for pb in problems:
            print(f"     - {pb}")
        print(LINE)
        err("Corrige les points ci-dessus, puis relance :  py build.py")
        return 2
    ok("Verification reussie : tous les fichiers requis sont presents et valides.")

    if args.site_only:
        ok("Mode --site-only : les builds n'ont pas ete verifies.")
        if not args.check:
            warn("--site-only ne construit pas d'archive, uniquement une verification.")
            return 0

    if args.check:
        info("Mode --check : aucune archive creee.")
        return 0

    # 3) Collecte.
    files = collect_files(project, include_source)
    if not files:
        err("Aucun fichier a compresser. Verifie les chemins dans project.json.")
        return 3
    raw = sum(p.stat().st_size for p in files)
    ok(f"{len(files)} fichiers a compresser ({human_size(raw)} non compresses).")
    if not include_source:
        info("Code source exclu (--no-source).")
    print(LINE)

    # 4) Compression.
    zip_path = make_zip(project, files, include_source)
    zsize = zip_path.stat().st_size
    ratio = (zsize / raw * 100) if raw else 0.0
    ok(f"Archive creee : {zip_path}")
    ok(f"Taille finale : {human_size(zsize)}  (~{ratio:.0f} % de l'original)")
    print(LINE)
    info("Termine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
