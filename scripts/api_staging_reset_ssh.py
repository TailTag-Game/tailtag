"""Run the guarded Staging reset through the one pinned Railway instance."""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Final, NoReturn, cast

__all__ = [
    "_BOOTSTRAP",
    "_build_bundle",
    "_execute_remote",
    "_read_configuration",
    "main",
]

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
_TARGET: Final = "https://staging.tailtag.app"
REPLACEMENT_RESET_CONFIG_PATH: Final = (
    Path.home() / ".config/tailtag/staging-reset-replacement.env"
)
_TIMEOUT_SECONDS: Final = 30
_BUILD_IDENTITY_PATH: Final = Path("/opt/tailtag/build-identity.json")
_CONFIGURATION_NAMES: Final = frozenset(
    {
        "TAILTAG_STAGING_RESET_ENABLED",
        "TAILTAG_STAGING_RESET_ID",
        "TAILTAG_STAGING_DATABASE_SYSTEM_ID",
        "TAILTAG_STAGING_DATABASE_HOST",
        "TAILTAG_STAGING_DATABASE_PORT",
        "TAILTAG_STAGING_DATABASE_NAME",
        "TAILTAG_STAGING_RESET_OWNER_CLERK_ID",
        "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID",
        "TAILTAG_STAGING_RESET_MEDIA_KEY",
    }
)
_SOURCE_SHA = re.compile(r"[0-9a-f]{40}")
_HASH = re.compile(r"[0-9a-f]{64}")
_CONFIGURATION_VALUE = re.compile(r"[A-Za-z0-9._:/@+-]+")
_PACKAGES: Final = (
    "accounts",
    "authentication",
    "catches",
    "config",
    "conventions",
    "fursuits",
    "health",
    "media",
    "operator_audit",
    "profiles",
    "rehearsal",
)
_ROOT_HELPERS: Final = (
    "scripts/api_staging_reset.py",
    "scripts/api_staging_preflight.py",
    "scripts/api_staging_reset_ssh.py",
)
_ACTIVE_QUERY: Final = """query StagingResetActive($serviceId: String!, $environmentId: String!) {
  serviceInstance(serviceId: $serviceId, environmentId: $environmentId) {
    serviceId environmentId activeDeployments { id projectId serviceId environmentId status instances { id status } }
  }
}"""
_CONFIG_QUERY: Final = """query StagingResetConfiguration($serviceId: String!, $environmentId: String!) {
  serviceInstance(serviceId: $serviceId, environmentId: $environmentId) {
    serviceId environmentId service { id } variables { name value } }
  environment(id: $environmentId) { id variables { name value } }
}"""
_CORE_FAILURES: Final = frozenset(
    {
        "FAIL staging reset confirmation",
        "FAIL staging reset configuration",
        "FAIL staging reset preflight",
        "FAIL staging reset provision",
        "FAIL staging reset maintenance retained",
        "FAIL staging reset committed maintenance retained",
        "FAIL staging reset maintenance unknown",
    }
)
_EXPECTED_COUNTS: Final = {
    "profiles": 2,
    "conventions": 1,
    "fursuits": 2,
    "enrollments": 2,
    "activations": 2,
    "catches": 0,
    "sessions": 0,
    "credentials": 0,
}


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("arguments invalid")


def _target_ids() -> tuple[str, str, str, str]:
    """Read the owner-only replacement selectors and require their code pins."""
    api_root = _REPOSITORY_ROOT / "services" / "api"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))
    from config.replacement_target_binding import (
        _MANIFEST_PATH,  # pyright: ignore[reportPrivateUsage]
        load_local_manifest,
        validate_selectors,
    )

    selectors = load_local_manifest(_MANIFEST_PATH)
    validate_selectors(selectors)
    return (
        selectors["rebuild_railway_project_id"],
        selectors["rebuild_staging_environment_id"],
        selectors["rebuild_api_service_id"],
        selectors["rebuild_postgres_service_id"],
    )


def _run(
    arguments: list[str], *, input: str | None = None, timeout: int = _TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        timeout=timeout,
        input=input,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json_loads(value: str) -> object:
    return json.loads(value, object_pairs_hook=_reject_duplicate_keys)


def _fail(phase: str) -> int:
    print(f"FAIL staging reset {phase}", file=sys.stderr)
    return 1


def _json_command(
    arguments: list[str], *, input: str | None = None
) -> dict[str, object]:
    result = _run(arguments, input=input)
    if result.returncode != 0:
        raise TypeError("external operation failed")
    value = _json_loads(result.stdout)
    if not isinstance(value, dict):
        raise TypeError("external operation failed")
    response = cast(dict[str, object], value)
    if response.get("errors"):
        raise ValueError("external operation failed")
    return response


def _mapping(value: object) -> dict[str, object] | None:
    return (
        dict(cast(Mapping[str, object], value)) if isinstance(value, Mapping) else None
    )


def _railway_identity() -> None:
    response = _json_command(["railway", "whoami", "--json"])
    if (
        response.get("name") != "Finn the Panther"
        or response.get("email") != "finn@finnthepanther.com"
    ):
        raise ValueError("railway identity unavailable")


def _railway(query: str, variables: Mapping[str, str]) -> dict[str, object]:
    return _json_command(
        [
            "railway",
            "api",
            query,
            "--variables",
            json.dumps(dict(variables), separators=(",", ":")),
        ]
    )


def _data(response: Mapping[str, object], key: str) -> dict[str, object]:
    data = _mapping(response.get("data"))
    value = _mapping(data.get(key)) if data is not None else None
    if value is None:
        raise ValueError("provider observation invalid")
    return value


def _uuid(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return value if str(uuid.UUID(value)) == value else None
    except ValueError:
        return None


def _preflight() -> dict[str, str]:
    from scripts.api_staging_preflight import validate_target

    observed = validate_target(_TARGET)
    if set(observed) != {"source_sha", "deployment_id", "environment"}:
        raise ValueError("preflight unavailable")
    if (
        _SOURCE_SHA.fullmatch(observed["source_sha"]) is None
        or _uuid(observed["deployment_id"]) is None
        or observed["environment"] != "staging"
    ):
        raise ValueError("preflight unavailable")
    return {
        "source_sha": observed["source_sha"],
        "deployment_id": observed["deployment_id"],
        "environment": observed["environment"],
    }


def _approved_receipt(identity: dict[str, str], root: Path | None = None) -> None:
    """Require retained approval for the exact currently serving deployment."""
    receipt_path = (
        (root or _REPOSITORY_ROOT)
        / "docs/development/staging-deployments"
        / (identity["deployment_id"] + ".json")
    )
    receipt = json.loads(receipt_path.read_text())
    if not isinstance(receipt, dict):
        raise TypeError
    values = cast(dict[str, object], receipt)
    if (
        values.get("deployment_id") != identity["deployment_id"]
        or values.get("source_sha") != identity["source_sha"]
        or values.get("environment") != "staging"
        or values.get("final_active_state") != "ACTIVE"
    ):
        raise ValueError
    promotion_receipt = (
        values.get("receipt_type") is None
        and values.get("overall_outcome") == "SUCCEEDED"
    )
    replacement_receipt = (
        values.get("receipt_type") == "replacement_canonical_handoff"
        and values.get("provider_deployment_status") == "SUCCESS"
        and values.get("public_exact_instance_join") == "PASS"
    )
    if not (promotion_receipt or replacement_receipt):
        raise ValueError


def _active_instance(identity: Mapping[str, str]) -> str:
    project_id, environment_id, service_id, _ = _target_ids()
    service = _data(
        _railway(
            _ACTIVE_QUERY, {"serviceId": service_id, "environmentId": environment_id}
        ),
        "serviceInstance",
    )
    active = service.get("activeDeployments")
    if (
        service.get("serviceId") != service_id
        or service.get("environmentId") != environment_id
        or not isinstance(active, list)
    ):
        raise ValueError("active deployment invalid")
    typed_active = cast(list[object], active)
    if len(typed_active) != 1:
        raise ValueError("active deployment invalid")
    deployment = _mapping(typed_active[0])
    if (
        deployment is None
        or deployment.get("id") != identity["deployment_id"]
        or deployment.get("projectId") != project_id
        or deployment.get("serviceId") != service_id
        or deployment.get("environmentId") != environment_id
        or deployment.get("status") != "SUCCESS"
    ):
        raise ValueError("active deployment invalid")
    instances = deployment.get("instances")
    if not isinstance(instances, list):
        raise TypeError("active deployment invalid")
    running: list[str] = []
    for item in cast(list[object], instances):
        instance = _mapping(item)
        instance_id = instance.get("id") if instance else None
        if (
            instance is None
            or _uuid(instance_id) is None
            or not isinstance(instance.get("status"), str)
        ):
            raise ValueError("active deployment invalid")
        if instance["status"] == "RUNNING":
            running.append(cast(str, instance_id))
    if len(running) != 1:
        raise ValueError("active deployment invalid")
    return running[0]


def _variables(service_id: str) -> dict[str, str]:
    project_id, environment_id, _, _ = _target_ids()
    response = _json_command(
        [
            "railway",
            "variable",
            "list",
            "--project",
            project_id,
            "--environment",
            environment_id,
            "--service",
            service_id,
            "--json",
        ]
    )
    if not all(isinstance(value, str) for value in response.values()):
        raise ValueError("configuration invalid")
    return {key: cast(str, value) for key, value in response.items()}


def _runtime_database_fingerprint() -> str:
    project_id, environment_id, service_id, postgres_id = _target_ids()
    api = _variables(service_id)
    postgres = _variables(postgres_id)
    expected_api = {
        "RAILWAY_PROJECT_ID": project_id,
        "RAILWAY_ENVIRONMENT_ID": environment_id,
        "RAILWAY_SERVICE_ID": service_id,
        "RAILWAY_ENVIRONMENT_NAME": "staging",
    }
    expected_postgres = {**expected_api, "RAILWAY_SERVICE_ID": postgres_id}
    if (
        any(api.get(key) != value for key, value in expected_api.items())
        or any(postgres.get(key) != value for key, value in expected_postgres.items())
        or not isinstance(api.get("DATABASE_URL"), str)
        or not api["DATABASE_URL"]
        or api["DATABASE_URL"] != postgres.get("DATABASE_URL")
    ):
        raise ValueError("configuration invalid")
    return hashlib.sha256(api["DATABASE_URL"].encode()).hexdigest()


def _read_configuration(path: Path) -> dict[str, str]:
    try:
        parent = path.parent
        parent_status = parent.lstat()
        file_status = path.lstat()
        if (
            stat.S_ISLNK(parent_status.st_mode)
            or stat.S_ISLNK(file_status.st_mode)
            or not stat.S_ISDIR(parent_status.st_mode)
            or not stat.S_ISREG(file_status.st_mode)
        ):
            raise TypeError
        if (
            parent_status.st_uid != os.getuid()
            or file_status.st_uid != os.getuid()
            or stat.S_IMODE(parent_status.st_mode) != 0o700
            or stat.S_IMODE(file_status.st_mode) != 0o600
            or file_status.st_size > 16 * 1024
        ):
            raise TypeError
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            if line.count("=") != 1:
                raise ValueError
            key, value = line.split("=", 1)
            if (
                key not in _CONFIGURATION_NAMES
                or key in values
                or not value
                or _CONFIGURATION_VALUE.fullmatch(value) is None
            ):
                raise ValueError
            values[key] = value
        if frozenset(values) != _CONFIGURATION_NAMES:
            raise ValueError
        return values
    except (OSError, TypeError, UnicodeError, ValueError):
        raise ValueError("configuration invalid") from None


def _bundle_members(root: Path) -> list[Path]:
    paths: list[Path] = []
    for package in _PACKAGES:
        directory = root / "services" / "api" / package
        if not directory.is_dir():
            raise ValueError("bundle invalid")
        paths.extend(sorted(directory.rglob("*.py")))
    paths.extend(root / name for name in _ROOT_HELPERS)
    return paths


def _build_bundle(root: Path) -> tuple[str, dict[str, str]]:
    manifest: dict[str, str] = {}
    output = io.BytesIO()
    try:
        with tarfile.open(fileobj=output, mode="w") as archive:
            for source in _bundle_members(root):
                relative = source.relative_to(root).as_posix()
                status = source.lstat()
                ancestor = source.parent
                while ancestor != root:
                    if stat.S_ISLNK(ancestor.lstat().st_mode):
                        raise ValueError("bundle invalid")
                    ancestor = ancestor.parent
                if (
                    not stat.S_ISREG(status.st_mode)
                    or stat.S_ISLNK(status.st_mode)
                    or relative in manifest
                ):
                    raise ValueError("bundle invalid")
                content = source.read_bytes()
                manifest[relative] = hashlib.sha256(content).hexdigest()
                info = tarfile.TarInfo(relative)
                info.size = len(content)
                info.mode = 0o600
                archive.addfile(info, io.BytesIO(content))
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        if len(output.getvalue()) > 8 * 1024 * 1024:
            raise ValueError("bundle invalid")
        return encoded, manifest
    except (OSError, ValueError):
        raise ValueError("bundle invalid") from None


def _execute_remote(request: Mapping[str, object], root: Path) -> tuple[int, str]:
    """Bind copied code to runtime identity and invoke the existing reset CLI."""
    try:
        identity = request["identity"]
        operation = request["operation"]
        fingerprint = request["database_url_fingerprint"]
        configuration = request["configuration"]
        if (
            not isinstance(identity, Mapping)
            or operation not in {"reset", "provision"}
            or not isinstance(fingerprint, str)
            or not isinstance(configuration, Mapping)
        ):
            raise TypeError
        raw_identity = cast(Mapping[str, object], identity)
        source_sha = raw_identity.get("source_sha")
        deployment_id = raw_identity.get("deployment_id")
        environment_name = raw_identity.get("environment")
        if (
            frozenset(raw_identity)
            != frozenset({"source_sha", "deployment_id", "environment"})
            or not isinstance(source_sha, str)
            or _SOURCE_SHA.fullmatch(source_sha) is None
            or _uuid(deployment_id) is None
            or environment_name != "staging"
        ):
            raise TypeError
        typed_identity = {
            "source_sha": source_sha,
            "deployment_id": cast(str, deployment_id),
            "environment": cast(str, environment_name),
        }
        runtime: dict[str, str | None] = {
            "source_sha": source_sha,
            "deployment_id": os.environ.get("RAILWAY_DEPLOYMENT_ID"),
            "environment": os.environ.get("RAILWAY_ENVIRONMENT_NAME"),
        }
        from config.replacement_target_binding import (
            TargetBindingError,
            validate_runtime_target,
        )

        try:
            validate_runtime_target(os.environ)
        except TargetBindingError:
            raise ValueError from None
        if (
            typed_identity != runtime
            or hashlib.sha256(os.environ.get("DATABASE_URL", "").encode()).hexdigest()
            != fingerprint
        ):
            raise ValueError
        record = _json_loads(_BUILD_IDENTITY_PATH.read_text())
        if record != {"source_sha": source_sha}:
            raise ValueError
        environment = dict(os.environ)
        raw_configuration = cast(Mapping[object, object], configuration)
        if not all(isinstance(key, str) for key in raw_configuration):
            raise TypeError
        typed_configuration = {
            cast(str, key): value for key, value in raw_configuration.items()
        }
        if frozenset(typed_configuration) != _CONFIGURATION_NAMES or not all(
            isinstance(value, str) for value in typed_configuration.values()
        ):
            raise ValueError
        values = {key: cast(str, value) for key, value in typed_configuration.items()}
        original_path = list(sys.path)
        original_argv = list(sys.argv)
        reset: ModuleType | None = None
        original_preflight: object | None = None
        try:
            os.environ.update(values)
            os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
            sys.path[:0] = [str(root), str(root / "services" / "api")]
            from scripts import api_staging_reset as reset

            original_preflight = reset.validate_target

            def pinned_preflight(target: str) -> dict[str, str]:
                result = original_preflight(target)
                if result != typed_identity:
                    raise ValueError("preflight unavailable")
                return {
                    "source_sha": result["source_sha"],
                    "deployment_id": result["deployment_id"],
                    "environment": result["environment"],
                }

            reset.validate_target = pinned_preflight
            stdout = io.StringIO()
            stderr = io.StringIO()
            sys.argv = ["api_staging_reset.py"]
            if operation == "provision":
                sys.argv.append("--provision")
            sys.argv.extend(
                [
                    "--confirm",
                    "provision-tailtag-staging-reset"
                    if operation == "provision"
                    else "reset-tailtag-staging",
                ]
            )
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_status = reset.main()
            if exit_status == 0 and operation == "provision":
                from rehearsal.safety import validate_identity

                configuration = reset.load_configuration(os.environ)
                validate_identity(configuration)
                if (
                    hashlib.sha256(
                        os.environ.get("DATABASE_URL", "").encode()
                    ).hexdigest()
                    != fingerprint
                    or reset.validate_target(_TARGET) != typed_identity
                ):
                    raise ValueError
        finally:
            if reset is not None and original_preflight is not None:
                reset.validate_target = original_preflight
            os.environ.clear()
            os.environ.update(environment)
            sys.path[:] = original_path
            sys.argv[:] = original_argv
        if exit_status != 0:
            failure = stderr.getvalue().strip()
            return (
                1,
                failure
                if failure in _CORE_FAILURES
                else "FAIL staging reset maintenance unknown",
            )
        if operation == "provision":
            if stdout.getvalue().strip() != "Staging reset identity provisioned.":
                raise ValueError
            return 0, json.dumps(
                {"identity": typed_identity, "provision_postcondition": "PASS"},
                sort_keys=True,
            )
        output = _json_loads(stdout.getvalue())
        if not isinstance(output, dict):
            raise TypeError
        return 0, json.dumps(output, sort_keys=True)
    except BaseException:  # noqa: BLE001
        return 1, "FAIL staging reset maintenance unknown"


_BOOTSTRAP = r"""import base64, contextlib, hashlib, io, json, os, shutil, signal, sys, tarfile, tempfile
from pathlib import Path, PurePosixPath
def fail():
    print("FAIL staging reset maintenance unknown", file=sys.stderr)
    return 1
def safe(name):
    packages=("accounts","authentication","catches","config","conventions","fursuits","health","media","operator_audit","profiles","rehearsal")
    return (isinstance(name,str) and PurePosixPath(name).as_posix()==name and name in {"scripts/api_staging_reset.py","scripts/api_staging_preflight.py","scripts/api_staging_reset_ssh.py"} or isinstance(name,str) and PurePosixPath(name).as_posix()==name and name.endswith(".py") and not name.startswith(".") and "/." not in name and "\\" not in name and any(name.startswith("services/api/"+package+"/") for package in packages) and "/tests/" not in name and ".." not in name and "//" not in name)
def duplicate(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError
        result[key]=value
    return result
def interrupted(*_): raise KeyboardInterrupt
signal.signal(signal.SIGTERM,interrupted)
root=None; status=1; output=""
try:
    request_data=sys.stdin.buffer.read(12*1024*1024+1)
    if len(request_data)>12*1024*1024: raise ValueError
    request=json.loads(request_data,object_pairs_hook=duplicate)
    if not isinstance(request,dict) or set(request)!={"bundle","manifest","identity","database_url_fingerprint","configuration","operation"}: raise ValueError
    bundle=request["bundle"]; manifest=request["manifest"]
    identity=request["identity"]; configuration=request["configuration"]
    operation=request["operation"]
    if operation not in ("reset","provision"): raise ValueError
    if not isinstance(identity,dict) or set(identity)!={"source_sha","deployment_id","environment"} or not isinstance(configuration,dict) or set(configuration)!={"TAILTAG_STAGING_RESET_ENABLED","TAILTAG_STAGING_RESET_ID","TAILTAG_STAGING_DATABASE_SYSTEM_ID","TAILTAG_STAGING_DATABASE_HOST","TAILTAG_STAGING_DATABASE_PORT","TAILTAG_STAGING_DATABASE_NAME","TAILTAG_STAGING_RESET_OWNER_CLERK_ID","TAILTAG_STAGING_RESET_CATCHER_CLERK_ID","TAILTAG_STAGING_RESET_MEDIA_KEY"}: raise ValueError
    if not isinstance(bundle,str) or not isinstance(manifest,dict): raise ValueError
    raw=base64.b64decode(bundle,validate=True)
    if len(raw)>8*1024*1024 or not manifest or any(not safe(k) or not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v) for k,v in manifest.items()): raise ValueError
    root=tempfile.mkdtemp(prefix="tailtag-staging-reset-",dir="/tmp")
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:") as archive:
        members=archive.getmembers()
        if len(members)>1024 or len(members)!=len(manifest) or len({member.name for member in members})!=len(members) or any(member.size<0 or member.size>1024*1024 or not member.isfile() or member.name not in manifest for member in members): raise ValueError
        validated=[]
        for member in members:
            content=archive.extractfile(member).read()
            if hashlib.sha256(content).hexdigest()!=manifest[member.name]: raise ValueError
            validated.append((member.name,content))
        for name, content in validated:
            destination=os.path.join(root,name); os.makedirs(os.path.dirname(destination),exist_ok=True)
            with open(destination,"xb") as handle: handle.write(content)
    sys.path[:0]=[root,os.path.join(root,"services","api")]
    captured_stdout=io.StringIO(); captured_stderr=io.StringIO()
    with contextlib.redirect_stdout(captured_stdout), contextlib.redirect_stderr(captured_stderr):
        from scripts.api_staging_reset_ssh import _execute_remote
        status, output = _execute_remote(request,Path(root))
except BaseException:
    status=1
finally:
    if root:
        try: shutil.rmtree(root)
        except BaseException: status=1
        if os.path.exists(root): status=1
if status!=0:
    if output in {"FAIL staging reset confirmation","FAIL staging reset configuration","FAIL staging reset preflight","FAIL staging reset provision","FAIL staging reset maintenance retained","FAIL staging reset committed maintenance retained","FAIL staging reset maintenance unknown"}: print(output,file=sys.stderr)
    else: fail()
    raise SystemExit(1)
try:
    result=json.loads(output)
    if not isinstance(result,dict): raise ValueError
    if operation=="provision":
        if set(result)!={"identity","provision_postcondition"} or result["provision_postcondition"]!="PASS": raise ValueError
    elif set(result)!={"identity","baseline_version","counts"}: raise ValueError
    result["bundle_fingerprint"]=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    result["cleanup_confirmed"]=True
    print(json.dumps(result,sort_keys=True))
except Exception:
    raise SystemExit(fail())
"""


def _arguments() -> argparse.Namespace:
    parser = _SafeArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--provision", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--config", type=Path, default=REPLACEMENT_RESET_CONFIG_PATH)
    return parser.parse_args()


def main() -> int:
    try:
        arguments = _arguments()
        operation = "provision" if arguments.provision else "reset"
        expected_confirmation = (
            "provision-tailtag-staging-reset"
            if arguments.provision
            else "reset-tailtag-staging"
        )
        if arguments.confirm != expected_confirmation:
            raise ValueError
    except (SystemExit, ValueError):
        return _fail("confirmation")
    try:
        project_id, environment_id, service_id, _ = _target_ids()
        configuration = _read_configuration(arguments.config)
        _railway_identity()
        identity = _preflight()
        _approved_receipt(identity)
        instance = _active_instance(identity)
        fingerprint = _runtime_database_fingerprint()
        bundle, manifest = _build_bundle(_REPOSITORY_ROOT)
        _railway_identity()
        request: dict[str, object] = {
            "operation": operation,
            "bundle": bundle,
            "manifest": manifest,
            "identity": identity,
            "database_url_fingerprint": fingerprint,
            "configuration": configuration,
        }
        result = _run(
            [
                "railway",
                "ssh",
                "--project",
                project_id,
                "--service",
                service_id,
                "--environment",
                environment_id,
                "--deployment-instance",
                instance,
                "--",
                "/app/.venv/bin/python",
                "-I",
                "-c",
                _BOOTSTRAP,
            ],
            input=json.dumps(request, separators=(",", ":")),
            timeout=120,
        )
        if result.returncode != 0:
            failure = result.stderr.strip()
            if failure in _CORE_FAILURES:
                print(failure, file=sys.stderr)
                return 1
            return _fail("maintenance unknown")
        raw_output = _json_loads(result.stdout)
        if not isinstance(raw_output, dict):
            return _fail("maintenance unknown")
        output = cast(dict[str, object], raw_output)
        expected_fingerprint = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        common_valid = (
            output.get("identity") == identity
            and output.get("bundle_fingerprint") == expected_fingerprint
            and output.get("cleanup_confirmed") is True
        )
        provision_valid = (
            set(output)
            == {
                "identity",
                "provision_postcondition",
                "bundle_fingerprint",
                "cleanup_confirmed",
            }
            and output.get("provision_postcondition") == "PASS"
        )
        reset_valid = (
            set(output)
            == {
                "identity",
                "baseline_version",
                "counts",
                "bundle_fingerprint",
                "cleanup_confirmed",
            }
            and type(output.get("baseline_version")) is int
            and output.get("baseline_version") == 1
            and isinstance(output.get("counts"), dict)
            and cast(dict[str, object], output["counts"]) == _EXPECTED_COUNTS
        )
        if not common_valid or not (
            provision_valid if operation == "provision" else reset_valid
        ):
            return _fail("maintenance unknown")
        print(json.dumps(output, sort_keys=True))
        return 0
    except (
        OSError,
        TypeError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        TimeoutError,
    ):
        return _fail("maintenance unknown")


if __name__ == "__main__":
    raise SystemExit(main())
