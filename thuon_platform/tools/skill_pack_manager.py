# tools/skill_pack_manager.py
"""
Capability marketplace — install/remove/list versioned skill packs.

Skill packs are gzipped tarballs (.tar.gz) containing:
  SKILL.md          (required — skill definition)
  *.py              (optional — Python capability modules)

Registry protocol:
  GET REGISTRY_URL                       → list[{name, description, version, author,
                                                   size_bytes, downloads}]
  GET REGISTRY_URL/<name>/<version>.tar.gz  → tarball bytes
  GET REGISTRY_URL/<name>/<version>.sha256  → hex digest (optional; 404 = skip verify)

CLI:
  python skill_pack_manager.py install  <pack-name-or-path> [--version V]
  python skill_pack_manager.py uninstall <pack-name>
  python skill_pack_manager.py list
  python skill_pack_manager.py search   [query]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import requests

from thuon_platform.core.bundle import user_data_dir, app_root  # noqa: F401 (app_root re-exported)

# ── Constants ─────────────────────────────────────────────────────────────────

REGISTRY_URL  = "https://thuon-skills.dev/registry.json"
PACKS_DIR     = user_data_dir() / "skill_packs"
INSTALLED_DB  = user_data_dir() / "installed_packs.json"

_SKILLS_DIR       = user_data_dir() / "skills"
_CAPABILITIES_DIR = user_data_dir() / "capabilities"
_REQUEST_TIMEOUT  = 5  # seconds

_log = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ensure_dirs() -> None:
	for d in (PACKS_DIR, _SKILLS_DIR, _CAPABILITIES_DIR):
		d.mkdir(parents=True, exist_ok=True)


def _load_db() -> dict[str, Any]:
	"""Load INSTALLED_DB; return empty dict on missing / corrupt file."""
	if INSTALLED_DB.exists():
		try:
			return json.loads(INSTALLED_DB.read_text(encoding="utf-8"))
		except (json.JSONDecodeError, OSError) as exc:
			_log.warning("installed_packs.json unreadable, resetting: %s", exc)
	return {}


def _save_db(db: dict[str, Any]) -> None:
	INSTALLED_DB.parent.mkdir(parents=True, exist_ok=True)
	INSTALLED_DB.write_text(
		json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8"
	)


def _sha256_file(path: Path) -> str:
	h = hashlib.sha256()
	with path.open("rb") as fh:
		for chunk in iter(lambda: fh.read(65536), b""):
			h.update(chunk)
	return h.hexdigest()


def _registry_base(pack_name: str, version: str) -> str:
	"""Return the URL stem for pack_name/version (no extension)."""
	base = REGISTRY_URL.rstrip("/")
	if base.endswith("/registry.json"):
		base = base[: -len("/registry.json")]
	return f"{base}/{pack_name}/{version}"


def _fetch_bytes(url: str, timeout: int = _REQUEST_TIMEOUT) -> bytes:
	resp = requests.get(url, timeout=timeout)
	resp.raise_for_status()
	return resp.content


# ── SkillPackManager ──────────────────────────────────────────────────────────

class SkillPackManager:
	"""Install, uninstall, and introspect versioned Thuon skill packs."""

	# ── Read operations ───────────────────────────────────────────────────────

	def list_installed(self) -> list[dict[str, Any]]:
		"""Return [{name, version, installed_at, files}] for every installed pack."""
		return list(_load_db().values())

	def list_available(self) -> list[dict[str, Any]]:
		"""
		Fetch the remote registry and return available packs.

		Returns [] on any network or parse failure (logs a warning).
		Shape: [{name, description, version, author, size_bytes, downloads}]
		"""
		try:
			data = _fetch_bytes(REGISTRY_URL)
			packs: list[dict[str, Any]] = json.loads(data)
			if not isinstance(packs, list):
				_log.warning("Registry returned unexpected shape (not a list)")
				return []
			return packs
		except requests.exceptions.RequestException as exc:
			_log.warning("Could not reach skill registry (%s): %s", REGISTRY_URL, exc)
			return []
		except json.JSONDecodeError as exc:
			_log.warning("Registry response was not valid JSON: %s", exc)
			return []

	def check_updates(self) -> list[dict[str, Any]]:
		"""
		Compare installed pack versions against the remote registry.

		Returns [{name, installed_version, latest_version, has_update}].
		When the registry is unreachable, has_update is False for all packs.
		"""
		db       = _load_db()
		registry = {p["name"]: p for p in self.list_available() if "name" in p}
		result: list[dict[str, Any]] = []

		for name, rec in db.items():
			inst   = rec.get("version", "unknown")
			latest = registry.get(name, {}).get("version", inst)
			result.append(
				{
					"name":              name,
					"installed_version": inst,
					"latest_version":    latest,
					"has_update":        (
						latest != inst
						and latest != "unknown"
						and inst != "unknown"
					),
				}
			)
		return result

	# ── Install ───────────────────────────────────────────────────────────────

	def install(
		self,
		pack_name_or_path: str,
		version: str = "latest",
	) -> dict[str, Any]:
		"""
		Install a skill pack from a local path or the remote registry.

		Args:
			pack_name_or_path: Path to a local .tar.gz  OR  a registry pack name.
			version:           Registry version tag (ignored for local installs).

		Returns:
			{success, name, version, files_installed, message}
		"""
		_ensure_dirs()
		local = Path(pack_name_or_path)
		if local.suffix in (".gz", ".tgz") and local.exists():
			return self._install_from_file(local, version_hint=version)
		return self._install_from_registry(pack_name_or_path, version)

	def uninstall(self, pack_name: str) -> dict[str, Any]:
		"""
		Remove a previously installed pack and its extracted files.

		Returns {success, message}.
		"""
		db = _load_db()
		if pack_name not in db:
			return {"success": False, "message": f"Pack '{pack_name}' is not installed."}

		files  = db[pack_name].get("files", [])
		errors: list[str] = []

		for rel in files:
			p    = Path(rel)
			full = p if p.is_absolute() else (user_data_dir() / p)
			if full.exists():
				try:
					full.unlink()
				except OSError as exc:
					errors.append(f"{full}: {exc}")

		# remove the pack's skill subfolder wholesale
		pack_skill_dir = _SKILLS_DIR / pack_name
		if pack_skill_dir.exists():
			try:
				shutil.rmtree(pack_skill_dir)
			except OSError as exc:
				errors.append(f"{pack_skill_dir}: {exc}")

		# remove cached tarball
		for suffix in (".tar.gz", ".tgz"):
			cached = PACKS_DIR / f"{pack_name}{suffix}"
			if cached.exists():
				try:
					cached.unlink()
				except OSError:
					pass

		del db[pack_name]
		_save_db(db)

		if errors:
			return {
				"success": False,
				"message": (
					f"Pack '{pack_name}' partially removed. "
					f"Errors: {'; '.join(errors)}"
				),
			}
		return {
			"success": True,
			"message": f"Pack '{pack_name}' uninstalled ({len(files)} file(s) removed).",
		}

	# ── Internal install helpers ──────────────────────────────────────────────

	def _install_from_file(
		self,
		tarball_path: Path,
		version_hint: str = "unknown",
	) -> dict[str, Any]:
		"""Install from a local .tar.gz; verify sibling .sha256 when present."""
		sha256_path = tarball_path.with_suffix("").with_suffix(".sha256")
		if sha256_path.exists():
			expected = sha256_path.read_text(encoding="utf-8").strip().split()[0]
			actual   = _sha256_file(tarball_path)
			if actual != expected:
				name = tarball_path.stem.replace(".tar", "")
				return {
					"success":         False,
					"name":            name,
					"version":         version_hint,
					"files_installed": [],
					"message":         (
						f"SHA256 mismatch: expected {expected}, got {actual}"
					),
				}
		return self._extract_and_record(tarball_path, version=version_hint)

	def _install_from_registry(
		self,
		pack_name: str,
		version: str,
	) -> dict[str, Any]:
		"""Download pack from registry, optionally verify checksum, then install."""
		base    = _registry_base(pack_name, version)
		tar_url = f"{base}.tar.gz"
		sha_url = f"{base}.sha256"

		# download tarball
		try:
			tar_bytes = _fetch_bytes(tar_url)
		except requests.exceptions.HTTPError as exc:
			code = exc.response.status_code if exc.response is not None else "?"
			return {
				"success":         False,
				"name":            pack_name,
				"version":         version,
				"files_installed": [],
				"message":         f"HTTP {code} fetching pack '{pack_name}@{version}'.",
			}
		except requests.exceptions.RequestException as exc:
			return {
				"success":         False,
				"name":            pack_name,
				"version":         version,
				"files_installed": [],
				"message":         f"Network error: {exc}",
			}

		# verify checksum if available
		try:
			sha_bytes = _fetch_bytes(sha_url)
			expected  = sha_bytes.decode().strip().split()[0]
			actual    = hashlib.sha256(tar_bytes).hexdigest()
			if actual != expected:
				return {
					"success":         False,
					"name":            pack_name,
					"version":         version,
					"files_installed": [],
					"message":         (
						f"SHA256 mismatch: expected {expected}, got {actual}"
					),
				}
		except requests.exceptions.HTTPError as exc:
			if exc.response is not None and exc.response.status_code == 404:
				_log.debug(
					"No .sha256 for %s@%s — skipping checksum.", pack_name, version
				)
			else:
				_log.warning(
					"Could not fetch checksum for %s@%s: %s", pack_name, version, exc
				)
		except requests.exceptions.RequestException as exc:
			_log.warning(
				"Could not fetch checksum for %s@%s: %s", pack_name, version, exc
			)

		# persist tarball to cache
		_ensure_dirs()
		cached = PACKS_DIR / f"{pack_name}.tar.gz"
		cached.write_bytes(tar_bytes)

		return self._extract_and_record(cached, version=version, pack_name_hint=pack_name)

	def _extract_and_record(
		self,
		tarball_path: Path,
		version: str = "unknown",
		pack_name_hint: str | None = None,
	) -> dict[str, Any]:
		"""
		Extract a validated tarball, place files in the right dirs, update INSTALLED_DB.

		Tarball layout (flexible — handles flat or subdirected):
		  SKILL.md          → _SKILLS_DIR/<pack_name>/SKILL.md
		  *.py              → _CAPABILITIES_DIR/<file>.py
		  <dir>/SKILL.md    → same after stripping top-level dir
		"""
		if not tarfile.is_tarfile(tarball_path):
			name = pack_name_hint or tarball_path.stem.replace(".tar", "")
			return {
				"success":         False,
				"name":            name,
				"version":         version,
				"files_installed": [],
				"message":         f"{tarball_path} is not a valid tar archive.",
			}

		with tempfile.TemporaryDirectory() as tmp_str:
			tmp = Path(tmp_str)
			with tarfile.open(tarball_path, "r:gz") as tf:
				safe: list[tarfile.TarInfo] = []
				for member in tf.getmembers():
					mp = Path(member.name)
					if mp.is_absolute() or ".." in mp.parts:
						_log.warning("Skipping unsafe member: %s", member.name)
						continue
					safe.append(member)
				tf.extractall(tmp, members=safe)  # noqa: S202 — members filtered above

			# locate SKILL.md
			skill_md_candidates = list(tmp.rglob("SKILL.md"))
			if not skill_md_candidates:
				name = pack_name_hint or tarball_path.stem.replace(".tar", "")
				return {
					"success":         False,
					"name":            name,
					"version":         version,
					"files_installed": [],
					"message":         "Tarball contains no SKILL.md — invalid pack.",
				}

			skill_md_src = skill_md_candidates[0]

			# infer pack name
			if pack_name_hint:
				pack_name = pack_name_hint
			elif skill_md_src.parent != tmp:
				pack_name = skill_md_src.parent.name
			else:
				pack_name = tarball_path.stem.replace(".tar", "")

			pack_skill_dir = _SKILLS_DIR / pack_name
			pack_skill_dir.mkdir(parents=True, exist_ok=True)

			files_installed: list[str] = []

			# install SKILL.md
			dest_skill_md = pack_skill_dir / "SKILL.md"
			shutil.copy2(skill_md_src, dest_skill_md)
			files_installed.append(str(dest_skill_md))

			# install sibling files from SKILL.md's directory
			for src_file in skill_md_src.parent.iterdir():
				if src_file.name == "SKILL.md" or not src_file.is_file():
					continue
				dest = (
					_CAPABILITIES_DIR / src_file.name
					if src_file.suffix == ".py"
					else pack_skill_dir / src_file.name
				)
				shutil.copy2(src_file, dest)
				files_installed.append(str(dest))

			# install any .py files elsewhere in the tarball
			seen = set(files_installed)
			for py_file in tmp.rglob("*.py"):
				dest = _CAPABILITIES_DIR / py_file.name
				if str(dest) in seen:
					continue
				shutil.copy2(py_file, dest)
				files_installed.append(str(dest))
				seen.add(str(dest))

		# persist to INSTALLED_DB
		db = _load_db()
		db[pack_name] = {
			"name":         pack_name,
			"version":      version,
			"installed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
			"files":        files_installed,
		}
		_save_db(db)

		return {
			"success":         True,
			"name":            pack_name,
			"version":         version,
			"files_installed": files_installed,
			"message":         (
				f"Pack '{pack_name}' v{version} installed "
				f"({len(files_installed)} file(s))."
			),
		}


# ── Singleton ─────────────────────────────────────────────────────────────────

_manager: SkillPackManager | None = None


def get_pack_manager() -> SkillPackManager:
	"""Return the process-wide SkillPackManager singleton."""
	global _manager
	if _manager is None:
		_manager = SkillPackManager()
	return _manager


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli_install(args: argparse.Namespace) -> None:
	result = get_pack_manager().install(args.pack, version=args.version)
	if result["success"]:
		print(result["message"])
		for f in result.get("files_installed", []):
			print(f"  + {f}")
	else:
		print(f"ERROR: {result['message']}", file=sys.stderr)
		sys.exit(1)


def _cli_uninstall(args: argparse.Namespace) -> None:
	result = get_pack_manager().uninstall(args.pack)
	if result["success"]:
		print(result["message"])
	else:
		print(f"ERROR: {result['message']}", file=sys.stderr)
		sys.exit(1)


def _cli_list(args: argparse.Namespace) -> None:  # noqa: ARG001
	mgr     = get_pack_manager()
	packs   = mgr.list_installed()
	updates = {u["name"]: u for u in mgr.check_updates()}
	if not packs:
		print("No skill packs installed.")
		return
	print(f"{'Name':<28} {'Version':<12} {'Installed At':<28} Update")
	print("-" * 82)
	for p in sorted(packs, key=lambda x: x.get("name", "")):
		name = p.get("name", "?")
		ver  = p.get("version", "?")
		ts   = p.get("installed_at", "?")
		upd  = updates.get(name, {})
		tag  = f"-> {upd['latest_version']}" if upd.get("has_update") else ""
		print(f"{name:<28} {ver:<12} {ts:<28} {tag}")


def _cli_search(args: argparse.Namespace) -> None:
	packs = get_pack_manager().list_available()
	if not packs:
		print("Registry unavailable or empty.", file=sys.stderr)
		return
	query = (args.query or "").lower()
	hits  = (
		[
			p for p in packs
			if query in p.get("name", "").lower()
			or query in p.get("description", "").lower()
		]
		if query
		else packs
	)
	if not hits:
		print(f"No packs matching '{args.query}'.")
		return
	print(f"{'Name':<28} {'Version':<12} {'Author':<20} Description")
	print("-" * 90)
	for p in hits:
		print(
			f"{p.get('name', ''):<28} "
			f"{p.get('version', ''):<12} "
			f"{p.get('author', ''):<20} "
			f"{p.get('description', '')}"
		)


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		prog="skill_pack_manager",
		description="Thuon skill pack marketplace — install/remove/list capability packs.",
	)
	sub = parser.add_subparsers(dest="command", required=True)

	p = sub.add_parser("install", help="Install a skill pack.")
	p.add_argument("pack", help="Registry pack name or path to a local .tar.gz file.")
	p.add_argument("--version", default="latest", help="Registry version tag (default: latest).")
	p.set_defaults(func=_cli_install)

	p = sub.add_parser("uninstall", help="Remove an installed skill pack.")
	p.add_argument("pack", help="Pack name to remove.")
	p.set_defaults(func=_cli_uninstall)

	p = sub.add_parser("list", help="List installed skill packs.")
	p.set_defaults(func=_cli_list)

	p = sub.add_parser("search", help="Search the remote registry.")
	p.add_argument("query", nargs="?", default="", help="Search term (optional).")
	p.set_defaults(func=_cli_search)

	return parser


if __name__ == "__main__":
	logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
	args = _build_parser().parse_args()
	args.func(args)
