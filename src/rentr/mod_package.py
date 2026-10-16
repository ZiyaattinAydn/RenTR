"""Deterministic translation packages with guarded install and rollback."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any


class TranslationPackageError(ValueError):
    """Raised when a package cannot be built, verified, installed, or rolled back."""


MANIFEST_PATH = "rentr-manifest.json"
PACKAGE_SCHEMA_VERSION = 1
MAX_PACKAGE_FILES = 10_000
MAX_PACKAGE_BYTES = 128 * 1024 * 1024
ACTIVATION_PATH = "game/rentr_turkish.rpy"
ACTIVATION_CONTENT = (
    "# RenTR tarafından üretildi. Kaldırmak için RenTR geri alma işlemini kullanın.\n"
    "# Ren'Py'nin belgelenmiş varsayılan dil ayarıdır.\n"
    'define config.default_language = "turkish"\n'
).encode()
_PACKAGE_ID = re.compile(r"rentr-tr-[0-9a-f]{20}")


def _digest(content: bytes) -> str:
    return sha256(content).hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise TranslationPackageError(f"Güvensiz paket yolu: {value!r}")
    normalized = path.as_posix()
    allowed_translation = (
        normalized.startswith("game/tl/turkish/") and normalized.endswith(".rpy")
    )
    if not allowed_translation and normalized != ACTIVATION_PATH:
        raise TranslationPackageError(f"Paket yalnız Türkçe .rpy dosyaları içerebilir: {value}")
    return path


def _ensure_no_symlink(path: Path, root: Path) -> None:
    resolved_root = root.resolve()
    candidate = path
    while candidate != resolved_root:
        if candidate.is_symlink():
            raise TranslationPackageError(f"Sembolik bağlantı kullanılamaz: {candidate}")
        if resolved_root not in candidate.parents:
            raise TranslationPackageError("Hedef klasör sınırının dışına çıkılamaz")
        candidate = candidate.parent


@dataclass(frozen=True, slots=True)
class PackageFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PackageManifest:
    schema_version: int
    package_id: str
    language: str
    activation: str
    files: tuple[PackageFile, ...]


@dataclass(frozen=True, slots=True)
class BuiltPackage:
    package_path: Path
    package_hash: str
    manifest: PackageManifest


@dataclass(frozen=True, slots=True)
class VerifiedPackage:
    package_path: Path
    package_hash: str
    manifest: PackageManifest
    payloads: tuple[tuple[PackageFile, bytes], ...]


@dataclass(frozen=True, slots=True)
class InstallTarget:
    relative_path: str
    output_path: Path
    content: bytes
    content_hash: str
    original_exists: bool
    original_hash: str | None


@dataclass(frozen=True, slots=True)
class InstallPlan:
    game_root: Path
    package_path: Path
    package_hash: str
    package_id: str
    targets: tuple[InstallTarget, ...]
    replace_existing: bool
    receipt_path: Path

    @property
    def collisions(self) -> tuple[str, ...]:
        return tuple(target.relative_path for target in self.targets if target.original_exists)


@dataclass(frozen=True, slots=True)
class InstalledFile:
    relative_path: str
    installed_hash: str
    backup_path: Path | None
    created_new_file: bool


@dataclass(frozen=True, slots=True)
class InstallReceipt:
    game_root: Path
    package_id: str
    package_hash: str
    receipt_path: Path
    installed_at: str
    files: tuple[InstalledFile, ...]


def _manifest_payload(
    files: tuple[PackageFile, ...],
    *,
    package_id: str,
    activation: str,
) -> bytes:
    record = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_id": package_id,
        "language": "turkish",
        "activation": activation,
        "files": [
            {"path": item.path, "size": item.size, "sha256": item.sha256}
            for item in files
        ],
    }
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def _package_identity(files: tuple[PackageFile, ...], activation: str) -> str:
    identity = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "language": "turkish",
        "activation": activation,
        "files": [
            {"path": item.path, "size": item.size, "sha256": item.sha256}
            for item in files
        ],
    }
    digest = _digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    return f"rentr-tr-{digest[:20]}"


def _translation_payloads(
    workspace_root: Path,
    *,
    activate_turkish: bool,
) -> tuple[tuple[str, bytes], ...]:
    workspace = workspace_root.expanduser().resolve()
    if not workspace.is_dir():
        raise TranslationPackageError(f"İzole çalışma alanı bulunamadı: {workspace}")
    translation_root = workspace / "game" / "tl" / "turkish"
    if not translation_root.is_dir():
        raise TranslationPackageError("Türkçe çeviri klasörü bulunamadı")
    _ensure_no_symlink(translation_root, workspace)
    payloads: list[tuple[str, bytes]] = []
    for source in sorted(translation_root.rglob("*.rpy")):
        _ensure_no_symlink(source, workspace)
        if not source.is_file():
            continue
        relative = source.relative_to(workspace).as_posix()
        _safe_relative_path(relative)
        payloads.append((relative, source.read_bytes()))
    if not payloads:
        raise TranslationPackageError("Paketlenecek Türkçe .rpy dosyası bulunamadı")
    if activate_turkish:
        payloads.append((ACTIVATION_PATH, ACTIVATION_CONTENT))
    if len(payloads) > MAX_PACKAGE_FILES:
        raise TranslationPackageError("Paket dosya sayısı güvenlik sınırını aşıyor")
    if sum(len(content) for _, content in payloads) > MAX_PACKAGE_BYTES:
        raise TranslationPackageError("Paket boyutu güvenlik sınırını aşıyor")
    lowered = [name.casefold() for name, _ in payloads]
    if len(lowered) != len(set(lowered)):
        raise TranslationPackageError("Büyük/küçük harf çakışan paket yolları bulundu")
    return tuple(sorted(payloads))


def build_translation_package(
    workspace_root: Path,
    output_path: Path | None = None,
    *,
    activate_turkish: bool = True,
) -> BuiltPackage:
    """Build a reproducible ZIP from verified Turkish scripts in the workspace."""
    workspace = workspace_root.expanduser().resolve()
    payloads = _translation_payloads(workspace, activate_turkish=activate_turkish)
    files = tuple(
        PackageFile(path=name, size=len(content), sha256=_digest(content))
        for name, content in payloads
    )
    activation = "default_language" if activate_turkish else "manual"
    package_id = _package_identity(files, activation)
    destination = (
        output_path.expanduser().resolve()
        if output_path is not None
        else workspace / ".rentr" / "packages" / f"{package_id}.zip"
    )
    if not _is_within(destination, workspace):
        raise TranslationPackageError("Çeviri paketi izole çalışma alanı dışında oluşturulamaz")
    _ensure_no_symlink(destination, workspace)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.rentr-partial")
    if partial.exists():
        raise TranslationPackageError(f"Eski yarım paket temizlenmeli: {partial}")
    try:
        with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in (*payloads, (MANIFEST_PATH, _manifest_payload(
                files,
                package_id=package_id,
                activation=activation,
            ))):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content)
        package_bytes = partial.read_bytes()
        if destination.exists():
            if not destination.is_file() or destination.read_bytes() != package_bytes:
                raise TranslationPackageError(f"Farklı içerikli paket zaten var: {destination}")
            partial.unlink()
        else:
            partial.replace(destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    verified = verify_translation_package(destination)
    return BuiltPackage(destination, verified.package_hash, verified.manifest)


def _parse_manifest(content: bytes) -> PackageManifest:
    try:
        raw: Any = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise TranslationPackageError(f"Paket manifesti okunamadı: {error}") from error
    if not isinstance(raw, dict):
        raise TranslationPackageError("Paket manifesti JSON nesnesi olmalı")
    if raw.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        raise TranslationPackageError("Desteklenmeyen paket manifesti sürümü")
    package_id = raw.get("package_id")
    language = raw.get("language")
    activation = raw.get("activation")
    raw_files = raw.get("files")
    if (
        not isinstance(package_id, str)
        or _PACKAGE_ID.fullmatch(package_id) is None
        or language != "turkish"
        or activation not in {"default_language", "manual"}
        or not isinstance(raw_files, list)
    ):
        raise TranslationPackageError("Paket manifesti alanları geçersiz")
    files: list[PackageFile] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            raise TranslationPackageError("Manifest dosya kaydı geçersiz")
        path = raw_file.get("path")
        size = raw_file.get("size")
        digest = raw_file.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise TranslationPackageError("Manifest dosya alanları geçersiz")
        _safe_relative_path(path)
        files.append(PackageFile(path, size, digest))
    if not files or len(files) > MAX_PACKAGE_FILES:
        raise TranslationPackageError("Manifest dosya sayısı geçersiz")
    lowered = [item.path.casefold() for item in files]
    if len(lowered) != len(set(lowered)):
        raise TranslationPackageError("Manifestte çakışan yollar var")
    manifest = PackageManifest(
        schema_version=PACKAGE_SCHEMA_VERSION,
        package_id=package_id,
        language=language,
        activation=activation,
        files=tuple(files),
    )
    expected_id = _package_identity(manifest.files, activation)
    if package_id != expected_id:
        raise TranslationPackageError("Paket kimliği içerikle uyuşmuyor")
    return manifest


def verify_translation_package(package_path: Path) -> VerifiedPackage:
    """Read and verify bounded package contents before any install is planned."""
    package = package_path.expanduser().resolve()
    if not package.is_file() or package.is_symlink():
        raise TranslationPackageError(f"Çeviri paketi bulunamadı: {package}")
    package_bytes = package.read_bytes()
    try:
        with zipfile.ZipFile(package) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_PACKAGE_FILES + 1:
                raise TranslationPackageError("Paket dosya sayısı güvenlik sınırını aşıyor")
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or MANIFEST_PATH not in names:
                raise TranslationPackageError("Paket yolları eksik veya tekrarlı")
            for info in infos:
                unix_mode = info.external_attr >> 16
                if info.is_dir() or stat.S_ISLNK(unix_mode):
                    raise TranslationPackageError("Paket klasör veya sembolik bağlantı içeremez")
                if info.file_size > MAX_PACKAGE_BYTES:
                    raise TranslationPackageError("Paket girdisi güvenlik sınırını aşıyor")
            if sum(info.file_size for info in infos) > MAX_PACKAGE_BYTES:
                raise TranslationPackageError("Açılmış paket boyutu güvenlik sınırını aşıyor")
            manifest = _parse_manifest(archive.read(MANIFEST_PATH))
            expected_names = {item.path for item in manifest.files} | {MANIFEST_PATH}
            if set(names) != expected_names:
                raise TranslationPackageError("Paket içeriği manifest ile uyuşmuyor")
            payloads: list[tuple[PackageFile, bytes]] = []
            for item in manifest.files:
                content = archive.read(item.path)
                if len(content) != item.size or _digest(content) != item.sha256:
                    raise TranslationPackageError(f"Paket dosyası doğrulanamadı: {item.path}")
                payloads.append((item, content))
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as error:
        raise TranslationPackageError(f"Çeviri paketi açılamadı: {error}") from error
    return VerifiedPackage(package, _digest(package_bytes), manifest, tuple(payloads))


def plan_package_install(
    package_path: Path,
    game_root: Path,
    *,
    replace_existing: bool = False,
) -> InstallPlan:
    """Create an exact-state install plan without writing to the selected game."""
    game = game_root.expanduser().resolve()
    if not game.is_dir() or not (game / "game").is_dir():
        raise TranslationPackageError(f"Ren'Py oyun klasörü bulunamadı: {game}")
    _ensure_no_symlink(game / "game", game)
    verified = verify_translation_package(package_path)
    targets: list[InstallTarget] = []
    for item, content in verified.payloads:
        relative = _safe_relative_path(item.path)
        target = game.joinpath(*relative.parts)
        _ensure_no_symlink(target, game)
        if target.exists() and not target.is_file():
            raise TranslationPackageError(f"Kurulum hedefi normal dosya değil: {target}")
        exists = target.is_file()
        original = target.read_bytes() if exists else b""
        targets.append(
            InstallTarget(
                relative_path=item.path,
                output_path=target,
                content=content,
                content_hash=item.sha256,
                original_exists=exists,
                original_hash=_digest(original) if exists else None,
            )
        )
    collisions = [target.relative_path for target in targets if target.original_exists]
    if collisions and not replace_existing:
        raise TranslationPackageError(
            "Mevcut dosyalar için --replace-existing onayı gerekli: " + ", ".join(collisions)
        )
    receipt = game / ".rentr" / "installations" / f"{verified.manifest.package_id}.json"
    _ensure_no_symlink(receipt, game)
    if receipt.exists():
        raise TranslationPackageError("Bu paket için kurulum kaydı zaten mevcut")
    return InstallPlan(
        game_root=game,
        package_path=verified.package_path,
        package_hash=verified.package_hash,
        package_id=verified.manifest.package_id,
        targets=tuple(targets),
        replace_existing=replace_existing,
        receipt_path=receipt,
    )


def _verify_install_preconditions(plan: InstallPlan) -> None:
    package = plan.package_path.read_bytes() if plan.package_path.is_file() else b""
    if _digest(package) != plan.package_hash:
        raise TranslationPackageError("Paket kurulum planından sonra değişti")
    if plan.receipt_path.exists():
        raise TranslationPackageError("Kurulum kaydı plan sonrasında oluşturuldu")
    _ensure_no_symlink(plan.receipt_path, plan.game_root)
    for target in plan.targets:
        _ensure_no_symlink(target.output_path, plan.game_root)
        if target.output_path.exists() != target.original_exists:
            raise TranslationPackageError("Oyun dosyaları plan sonrasında değişti")
        if target.original_exists and (
            not target.output_path.is_file()
            or _digest(target.output_path.read_bytes()) != target.original_hash
        ):
            raise TranslationPackageError("Oyun dosyaları plan sonrasında değişti")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.rentr-partial")
    if partial.exists():
        raise TranslationPackageError(f"Eski yarım kurulum dosyası temizlenmeli: {partial}")
    try:
        with partial.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        partial.replace(path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def _receipt_payload(receipt: InstallReceipt) -> bytes:
    record = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "game_root": str(receipt.game_root),
        "package_id": receipt.package_id,
        "package_hash": receipt.package_hash,
        "installed_at": receipt.installed_at,
        "files": [
            {
                "relative_path": item.relative_path,
                "installed_hash": item.installed_hash,
                "backup_path": str(item.backup_path) if item.backup_path else None,
                "created_new_file": item.created_new_file,
            }
            for item in receipt.files
        ],
    }
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def apply_package_install(plan: InstallPlan) -> InstallReceipt:
    """Install all files with backups and best-effort transactional recovery."""
    _verify_install_preconditions(plan)
    backup_root = plan.game_root / ".rentr" / "backups" / plan.package_id
    installed: list[InstalledFile] = []
    try:
        for target in plan.targets:
            backup: Path | None = None
            if target.original_exists:
                backup = backup_root / Path(target.relative_path)
                _ensure_no_symlink(backup, plan.game_root)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target.output_path, backup)
            installed.append(
                InstalledFile(
                    target.relative_path,
                    target.content_hash,
                    backup,
                    not target.original_exists,
                )
            )
            _atomic_write(target.output_path, target.content)
            if _digest(target.output_path.read_bytes()) != target.content_hash:
                raise TranslationPackageError(
                    f"Kurulan dosya doğrulanamadı: {target.relative_path}"
                )
        receipt = InstallReceipt(
            game_root=plan.game_root,
            package_id=plan.package_id,
            package_hash=plan.package_hash,
            receipt_path=plan.receipt_path,
            installed_at=datetime.now(UTC).isoformat(),
            files=tuple(installed),
        )
        _atomic_write(plan.receipt_path, _receipt_payload(receipt))
        return receipt
    except BaseException:
        for item in reversed(installed):
            output_path = plan.game_root / Path(item.relative_path)
            if item.created_new_file:
                output_path.unlink(missing_ok=True)
            elif item.backup_path is not None and item.backup_path.is_file():
                _atomic_write(output_path, item.backup_path.read_bytes())
        raise


def load_install_receipt(receipt_path: Path, game_root: Path) -> InstallReceipt:
    """Load a local receipt while binding every path back to the selected game."""
    game = game_root.expanduser().resolve()
    receipt_file = receipt_path.expanduser().resolve()
    expected_root = game / ".rentr" / "installations"
    if not receipt_file.is_file() or not _is_within(receipt_file, expected_root):
        raise TranslationPackageError("Kurulum kaydı seçilen oyuna ait değil")
    try:
        raw = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TranslationPackageError(f"Kurulum kaydı okunamadı: {error}") from error
    if not isinstance(raw, dict) or raw.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        raise TranslationPackageError("Kurulum kaydı sürümü geçersiz")
    package_id = raw.get("package_id")
    package_hash = raw.get("package_hash")
    installed_at = raw.get("installed_at")
    raw_files = raw.get("files")
    if (
        raw.get("game_root") != str(game)
        or not isinstance(package_id, str)
        or _PACKAGE_ID.fullmatch(package_id) is None
        or receipt_file.name != f"{package_id}.json"
        or not isinstance(package_hash, str)
        or len(package_hash) != 64
        or not isinstance(installed_at, str)
        or not isinstance(raw_files, list)
    ):
        raise TranslationPackageError("Kurulum kaydı alanları geçersiz")
    files: list[InstalledFile] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            raise TranslationPackageError("Kurulum dosya kaydı geçersiz")
        relative = raw_file.get("relative_path")
        installed_hash = raw_file.get("installed_hash")
        created = raw_file.get("created_new_file")
        backup_value = raw_file.get("backup_path")
        if (
            not isinstance(relative, str)
            or not isinstance(installed_hash, str)
            or len(installed_hash) != 64
            or not isinstance(created, bool)
            or (backup_value is not None and not isinstance(backup_value, str))
        ):
            raise TranslationPackageError("Kurulum dosya alanları geçersiz")
        _safe_relative_path(relative)
        backup = Path(backup_value).resolve() if backup_value is not None else None
        expected_backup_root = game / ".rentr" / "backups" / package_id
        if backup is not None and not _is_within(backup, expected_backup_root):
            raise TranslationPackageError("Yedek yolu seçilen oyunun dışında")
        files.append(InstalledFile(relative, installed_hash, backup, created))
    return InstallReceipt(
        game_root=game,
        package_id=package_id,
        package_hash=package_hash,
        receipt_path=receipt_file,
        installed_at=installed_at,
        files=tuple(files),
    )


def rollback_package_install(receipt: InstallReceipt) -> None:
    """Undo an install only when every installed file still matches its receipt."""
    for item in receipt.files:
        target = receipt.game_root / Path(item.relative_path)
        _ensure_no_symlink(target, receipt.game_root)
        if not target.is_file() or _digest(target.read_bytes()) != item.installed_hash:
            raise TranslationPackageError(
                f"Kurulan dosya sonradan değişti; geri alma reddedildi: {item.relative_path}"
            )
        if not item.created_new_file and (
            item.backup_path is None or not item.backup_path.is_file()
        ):
            raise TranslationPackageError(f"Geri alma yedeği eksik: {item.relative_path}")
    for item in reversed(receipt.files):
        target = receipt.game_root / Path(item.relative_path)
        if item.created_new_file:
            target.unlink()
        else:
            assert item.backup_path is not None
            _atomic_write(target, item.backup_path.read_bytes())
    receipt.receipt_path.unlink()
