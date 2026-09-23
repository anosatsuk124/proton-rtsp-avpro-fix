#!/usr/bin/env python3
"""Pinned build and isolated AVPro reproduction. Python standard library only."""

import argparse
import contextlib
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

from patch_binary import patch

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "versions.lock.json").read_text())
CACHE = ROOT / ".cache"
ART = ROOT / "artifacts"
VARIANTS = ("baseline", "binary-patched", "source-baseline", "source-patched")


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def require(*names):
    missing = [name for name in names if not shutil.which(name)]
    if missing:
        raise RuntimeError("Missing dependencies: " + ", ".join(missing))


def run(command, **kwargs):
    return subprocess.run([str(x) for x in command], check=True, **kwargs)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def sdk(command, log=None):
    require("docker")
    argv = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        "CCACHE_DISABLE=1",
        "-v",
        f"{ROOT}:/work",
        "-w",
        "/work",
        LOCK["sdk"],
        *command,
    ]
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w") as output:
            try:
                run(argv, stdout=output, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(f"Build failed; inspect {log}") from exc
    else:
        run(argv)


def get_proton(supplied=None):
    if supplied:
        base = Path(supplied).expanduser().resolve()
    else:
        require("tar")
        archive = CACHE / "downloads/proton.tar.gz"
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            temporary = archive.with_suffix(".partial")
            print("Downloading pinned Proton archive", flush=True)
            with (
                urllib.request.urlopen(LOCK["proton"]["url"], timeout=60) as response,
                temporary.open("wb") as out,
            ):
                shutil.copyfileobj(response, out)
            if sha(temporary) != LOCK["proton"]["archive_sha256"]:
                temporary.unlink()
                raise RuntimeError("Downloaded Proton archive hash mismatch")
            temporary.replace(archive)
        if sha(archive) != LOCK["proton"]["archive_sha256"]:
            raise RuntimeError(
                "Cached Proton archive hash mismatch; remove the invalid cache file"
            )
        base = CACHE / "proton" / LOCK["proton"]["name"]
        if not base.exists():
            base.parent.mkdir(parents=True, exist_ok=True)
            # The exact upstream archive is authenticated above. GNU tar preserves
            # Wine's default-prefix symlinks, including dosdevices/z: -> /.
            with tempfile.TemporaryDirectory(dir=base.parent) as directory:
                run(["tar", "-xf", archive, "-C", directory])
                (Path(directory) / LOCK["proton"]["name"]).rename(base)
    dll = base / LOCK["proton"]["dll"]
    if not dll.is_file() or sha(dll) != LOCK["proton"]["original_sha256"]:
        raise RuntimeError(
            "Baseline Proton DLL must match the pinned, unmodified release"
        )
    return base


def get_source():
    require("git")
    repo = CACHE / "wine-git"
    if not repo.exists():
        repo.mkdir(parents=True)
        run(["git", "init", repo])
        run(["git", "-C", repo, "remote", "add", "origin", LOCK["wine"]["url"]])
    found = (
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "cat-file",
                "-e",
                LOCK["wine"]["commit"] + "^{commit}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )
    if not found:
        run(["git", "-C", repo, "fetch", "--depth=1", "origin", LOCK["wine"]["commit"]])
    return repo


def fetch(args):
    get_proton(args.proton)
    if args.only == "proton":
        return
    get_source()
    get_registries()
    require("docker")
    for image in (LOCK["sdk"], LOCK["mediamtx"]["image"]):
        run(["docker", "pull", image])


def get_registries():
    for name, pin in LOCK["vulkan_registry"].items():
        path = CACHE / "downloads" / (name + ".xml")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with urllib.request.urlopen(pin["url"], timeout=60) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != pin["sha256"]:
                raise RuntimeError("Vulkan registry download hash mismatch")
            path.write_bytes(data)
        if sha(path) != pin["sha256"]:
            raise RuntimeError("Vulkan registry cache hash mismatch")


def build(args):
    repo = get_source()
    get_registries()
    archive = CACHE / "wine-source.tar"
    with archive.open("wb") as output:
        run(["git", "-C", repo, "archive", LOCK["wine"]["commit"]], stdout=output)
    for variant in ("baseline", "patched"):
        source = CACHE / f"src-{variant}"
        marker = source / ".repro-source.json"
        expected = {
            "commit": LOCK["wine"]["commit"],
            "patch_sha256": sha(ROOT / "patches/0001-live-network-state.patch")
            if variant == "patched"
            else None,
        }
        if source.exists() and (
            not marker.exists() or json.loads(marker.read_text()) != expected
        ):
            raise RuntimeError(
                f"Source cache provenance differs: remove {source} and build/wine-{variant} before rebuilding"
            )
        if not source.exists():
            source.mkdir()
            with tarfile.open(archive) as tar:
                tar.extractall(source, filter="data")
            if variant == "patched":
                run(
                    ["git", "apply", ROOT / "patches/0001-live-network-state.patch"],
                    cwd=source,
                )
            write_json(marker, expected)
        print(f"Building source-{variant}; log: build/source-{variant}.log", flush=True)
        sdk(
            ["bash", "scripts/build-wine.sh", variant, str(args.jobs)],
            ROOT / f"build/source-{variant}.log",
        )
        dll = ART / f"source-{variant}/mfmediaengine.dll"
        write_json(
            dll.parent / "manifest.json",
            {
                **expected,
                "sdk": LOCK["sdk"],
                "source_date_epoch": LOCK["wine"]["source_date_epoch"],
                "recipe_sha256": sha(ROOT / "scripts/build-wine.sh"),
                "dll_sha256": sha(dll),
            },
        )
    archive.unlink()


def binary_patch(args):
    base = get_proton(args.proton)
    output = ART / "binary-patched/mfmediaengine.dll"
    output.parent.mkdir(parents=True, exist_ok=True)
    patch(base / LOCK["proton"]["dll"], output)
    write_json(
        output.parent / "manifest.json",
        {"base_sha256": LOCK["proton"]["original_sha256"], "dll_sha256": sha(output)},
    )


def compile_probe(args):
    (ART / "probes").mkdir(parents=True, exist_ok=True)
    sdk(
        [
            "x86_64-w64-mingw32-gcc",
            "-O2",
            "-Wall",
            "-municode",
            "-o",
            "/work/artifacts/probes/avpro_probe.exe",
            "/work/probes/avpro_probe.c",
            "-ld3d11",
            "-ldxgi",
        ]
    )
    sdk(
        [
            "x86_64-w64-mingw32-gcc",
            "-O2",
            "-Wall",
            "-municode",
            "-o",
            "/work/artifacts/probes/mf_probe.exe",
            "/work/probes/mf_probe.c",
            "-lole32",
            "-loleaut32",
            "-luuid",
            "-lmfplat",
            "-lmfuuid",
        ]
    )


def prepare_runtime(base, variant):
    if variant == "baseline":
        return base
    dll = ART / variant / "mfmediaengine.dll"
    manifest = dll.parent / "manifest.json"
    if not dll.exists() or not manifest.exists():
        raise RuntimeError(
            f"Missing {variant} artifact; run make build / make patch first"
        )
    digest = sha(dll)
    if digest != json.loads(manifest.read_text())["dll_sha256"]:
        raise RuntimeError(f"{variant} artifact does not match its build manifest")
    runtime = CACHE / "runtimes" / variant
    destination = runtime / LOCK["proton"]["dll"]
    if runtime.exists():
        if not destination.exists() or sha(destination) != digest:
            raise RuntimeError(f"Stale runtime: remove {runtime} before retrying")
        return runtime
    runtime.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=runtime.parent) as tmp:
        staging = Path(tmp) / "proton"
        run(["cp", "-a", "--reflink=auto", base, staging])
        target = staging / LOCK["proton"]["dll"]
        target.unlink()  # Never write through a release DLL symlink/hardlink.
        shutil.copy2(dll, target)
        staging.rename(runtime)
    return runtime


def video_token(pid, environment=None, proc_root=Path("/proc")):
    environment = os.environ if environment is None else environment
    token = environment.get("STEAMVIDEOTOKEN")
    if pid is not None:
        location = proc_root / str(pid)
        if location.stat().st_uid != os.getuid():
            raise RuntimeError(
                "Video token may only be inherited from a process owned by this user"
            )
        pairs = (
            entry.split(b"=", 1)
            for entry in (location / "environ").read_bytes().split(b"\0")
            if b"=" in entry
        )
        token = dict(pairs).get(b"STEAMVIDEOTOKEN", b"").decode()
    if not token:
        raise RuntimeError(
            "No Steam video token. Start VRChat with Steam and pass --inherit-video-token-from PID, or inherit STEAMVIDEOTOKEN in the environment"
        )
    return token


def classify(rows, vod=False):
    """Require sustained playback and advancing video/audio; readiness alone is insufficient."""
    errors = [row for row in rows if row["error"] != 0]
    ready = [
        r
        for r in rows
        if r["canplay"] and r["metadata"] and r["width"] > 0 and r["height"] > 0
    ]
    if errors or len(ready) < 2:
        return {"status": "failed", "reason": "AVPro error or no ready video"}
    first, last = ready[0], ready[-1]
    frames = last["frames"] - first["frames"]
    audio = last["audio_samples"] - first["audio_samples"]
    media_ok = (
        frames >= 30
        and audio > 0
        and last["audio_peak"] > 0.0001
        and last["time"] > first["time"] + 1
    )
    span = last["elapsed"] - first["elapsed"]
    steady = [r for r in ready if r["elapsed"] >= last["elapsed"] - 5]
    if vod:
        passed = (
            media_ok
            and any(r["finished"] for r in ready)
            and not last["live"]
            and last["duration"] > 0
        )
        status = "passed" if passed else "failed"
    elif (
        media_ok
        and span >= 6
        and steady
        and all(r["playing"] for r in steady)
        and all(r["live"] for r in steady)
    ):
        status = "passed"
    elif (
        media_ok
        and span >= 6
        and steady
        and all(not r["playing"] for r in steady)
        and all(r["live"] for r in steady)
    ):
        status = "reproduced"
    else:
        status = "inconclusive"
    return {
        "status": status,
        "frame_delta": frames,
        "audio_delta": audio,
        "audio_peak": last["audio_peak"],
        "observed_seconds": round(span, 3),
        "final_playing": last["playing"],
        "final_buffering": last["buffering"],
        "final_finished": last["finished"],
    }


def windows_path(path):
    return "Z:" + str(Path(path).resolve()).replace("/", "\\")


def stop_process(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def run_probe(args, runtime, variant, url, token, vod=False):
    tag = variant + ("-vod" if vod else "-rtsp")
    prefix = Path(tempfile.mkdtemp(prefix=tag + "-", dir=CACHE))
    try:
        return _run_probe(args, runtime, variant, url, token, prefix, vod)
    finally:
        # Also runs on initialization failure, timeout, malformed output, or Ctrl+C.
        # WINEPREFIX selects only this diagnostic's server, never VRChat's server.
        try:
            subprocess.run(
                [str(runtime / "files/bin/wineserver"), "-k"],
                env={**os.environ, "WINEPREFIX": str(prefix / "pfx")},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        if not args.keep_prefixes:
            shutil.rmtree(prefix)


def _run_probe(args, runtime, variant, url, token, prefix, vod):
    steam = Path(args.steam_root).expanduser().resolve()
    avpro = (
        Path(args.avpro_dll).expanduser().resolve()
        if args.avpro_dll
        else steam / "steamapps/common/VRChat/VRChat_Data/Plugins/x86_64/AVProVideo.dll"
    )
    runner = (
        Path(args.runtime).expanduser().resolve()
        if args.runtime
        else steam / "steamapps/common/SteamLinuxRuntime_4/run"
    )
    for path in (avpro, runner, ART / "probes/avpro_probe.exe"):
        if not path.is_file():
            raise RuntimeError(f"Missing required file: {path}")
    if not (steam / "ubuntu12_64/video").is_dir():
        raise RuntimeError("Steam video decoder directory missing: ubuntu12_64/video")
    tag = variant + ("-vod" if vod else "-rtsp")
    report = ART / "runs" / (tag + ".ndjson")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.unlink(missing_ok=True)
    env = os.environ.copy()
    for key in (
        "WINEDLLOVERRIDES",
        "WINEPREFIX",
        "PROTON_LOG",
        "WINEDEBUG",
        "GST_DEBUG",
        "PROTON_DUMP_DEBUG_COMMANDS",
    ):
        env.pop(key, None)
    env.update(
        STEAMVIDEOTOKEN=token,
        STEAM_COMPAT_DATA_PATH=str(prefix),
        STEAM_COMPAT_CLIENT_INSTALL_PATH=str(steam),
        SteamAppId="438100",
        SteamGameId="438100",
        STEAM_COMPAT_TRANSCODED_MEDIA_PATH=str(prefix),
        WINEDEBUG="-all",
        GST_DEBUG="0",
    )
    launcher = [
        str(runner),
        "--",
        "env",
        "LD_LIBRARY_PATH=" + str(steam / "ubuntu12_64/video"),
        str(runtime / "proton"),
    ]
    # getcompatpath initializes Proton's prefix without Steam's app-launch wrapper.
    # runinprefix then directly returns the diagnostic executable's exit status.
    run(
        launcher + ["getcompatpath", str(ROOT)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=90,
    )
    if url.startswith("rtsp://"):
        url = "rtspt://" + url.removeprefix("rtsp://")
    command = launcher + [
        "runinprefix",
        str(ART / "probes/avpro_probe.exe"),
        windows_path(avpro),
        url,
        windows_path(report),
        str(args.seconds),
    ]
    print(f"Running {tag} in a fresh diagnostic prefix", flush=True)
    process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    timed_out = False
    try:
        output, _ = process.communicate(timeout=args.seconds + 90)
    except subprocess.TimeoutExpired:
        timed_out = True
        stop_process(process)
        output, _ = process.communicate()
    finally:
        stop_process(process)
    # Raw Wine/GStreamer logs can expose URLs or codec tokens. Persist only our
    # structured numerical output and an allowlisted native-version line.
    version = next(
        (
            line.removeprefix("AVPro native version: ").strip()
            for line in output.splitlines()
            if line.startswith("AVPro native version: ")
        ),
        None,
    )
    records = (
        [json.loads(line) for line in report.read_text().splitlines()]
        if report.exists()
        else []
    )
    version = next(
        (r["native_version"] for r in records if "native_version" in r), version
    )
    rows = [r for r in records if "elapsed" in r]
    result = classify(rows, vod)
    if timed_out or process.returncode:
        result = {
            "status": "failed",
            "reason": "probe timeout"
            if timed_out
            else f"probe exit {process.returncode}",
            "last_avpro_error": rows[-1]["error"] if rows else None,
        }
    result.update(
        variant=variant,
        mode="vod" if vod else "rtsp",
        dll_sha256=sha(runtime / LOCK["proton"]["dll"]),
        avpro_sha256=sha(avpro),
        avpro_native_version=version,
        source_commit=LOCK["wine"]["commit"],
    )
    write_json(report.with_suffix(".json"), result)
    print(json.dumps(result), flush=True)
    return result


@contextlib.contextmanager
def fixture():
    require("docker", "ffmpeg", "ffprobe")
    config = ROOT / "fixtures/mediamtx.yml"
    cid = run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "-p",
            "127.0.0.1::8554",
            "-v",
            f"{config}:/mediamtx.yml:ro",
            LOCK["mediamtx"]["image"],
        ],
        capture_output=True,
        text=True,
    ).stdout.strip()
    publisher = None
    try:
        mapping = run(
            ["docker", "port", cid, "8554/tcp"], capture_output=True, text=True
        ).stdout.strip()
        url = "rtsp://" + mapping + "/fixture"
        port = int(mapping.rsplit(":", 1)[1])
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Local MediaMTX did not start")
        (ART / "fixture").mkdir(parents=True, exist_ok=True)
        ffmpeg_args = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-re",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "baseline",
            "-g",
            "30",
            "-bf",
            "0",
            "-b:v",
            "2M",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
        ]
        with (ART / "fixture/publisher.log").open("w") as log:
            publisher = subprocess.Popen(
                ffmpeg_args + ["-rtsp_transport", "tcp", "-f", "rtsp", url],
                stdout=subprocess.DEVNULL,
                stderr=log,
                start_new_session=True,
            )
        time.sleep(2)
        if publisher.poll() is not None:
            raise RuntimeError(
                "Fixture publisher failed; inspect artifacts/fixture/publisher.log"
            )
        probe = run(
            [
                "ffprobe",
                "-v",
                "error",
                "-rtsp_transport",
                "tcp",
                "-show_streams",
                "-of",
                "json",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        write_json(ART / "fixture/streams.json", json.loads(probe.stdout))
        vod = ART / "fixture/control.mp4"
        run(
            [x for x in ffmpeg_args if x != "-re"]
            + ["-t", "8", "-movflags", "+faststart", "-y", vod],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        yield url, windows_path(vod)
    finally:
        if publisher:
            stop_process(publisher)
        subprocess.run(
            ["docker", "stop", "-t", "2", cid],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )


def reproduce(args):
    token = video_token(args.inherit_video_token_from)
    base = get_proton(args.proton)
    if not (ART / "probes/avpro_probe.exe").exists():
        compile_probe(args)
    variants = args.variants.split(",")
    if any(v not in VARIANTS for v in variants):
        raise RuntimeError("Unknown variant")
    runtimes = {v: prepare_runtime(base, v) for v in variants}
    results = []
    if args.url:
        for variant, runtime in runtimes.items():
            results.append(run_probe(args, runtime, variant, args.url, token))
    else:
        with fixture() as (url, vod):
            for variant, runtime in runtimes.items():
                results.append(run_probe(args, runtime, variant, url, token))
            for variant, runtime in runtimes.items():
                if variant != "baseline":
                    results.append(
                        run_probe(args, runtime, variant, vod, token, vod=True)
                    )
    expected = lambda r: (
        "reproduced"
        if r["mode"] == "rtsp" and r["variant"] in ("baseline", "source-baseline")
        else "passed"
    )
    passed = all(r["status"] == expected(r) for r in results)
    write_json(
        ART / "runs/summary.json", {"expectations_met": passed, "results": results}
    )
    if not passed:
        raise RuntimeError(
            "Comparison incomplete or unexpected; inspect artifacts/runs/summary.json. No fix conclusion is inferred from a failed/inconclusive probe"
        )


def install(args):
    base = get_proton(args.proton)
    runtime = prepare_runtime(base, args.variant)
    name = LOCK["proton"]["name"] + "-avpro-" + args.variant
    target = (
        Path(args.steam_root).expanduser().resolve() / "compatibilitytools.d" / name
    )
    if target.exists():
        raise RuntimeError(f"Install target already exists: {target}; no files changed")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        staging = Path(tmp) / name
        run(["cp", "-a", "--reflink=auto", runtime, staging])
        vdf = staging / "compatibilitytool.vdf"
        vdf.write_text(
            '"compatibilitytools"\n{\n "compat_tools"\n {\n  "' + name + '"\n  {\n'
            '   "install_path" "."\n   "display_name" "' + name + '"\n'
            '   "from_oslist" "windows"\n   "to_oslist" "linux"\n  }\n }\n}\n'
        )
        staging.rename(target)
    print(
        f"Installed {target}. Restart Steam and manually select this compatibility tool for VRChat."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "build", "patch", "probe", "fixture", "reproduce", "install"):
        command = sub.add_parser(name)
        command.add_argument(
            "--proton", help="Optional existing unmodified pinned Proton directory"
        )
        command.add_argument("--steam-root", default="~/.local/share/Steam")
        if name == "fetch":
            command.add_argument(
                "--only",
                choices=("proton",),
                help="Fetch only the pinned Proton release archive",
            )
        if name == "build":
            command.add_argument("--jobs", type=int, default=2)
        if name == "reproduce":
            command.add_argument(
                "--avpro-dll", help="User-owned native x86_64 AVPro DLL"
            )
            command.add_argument("--runtime", help="SteamLinuxRuntime_4/run path")
            command.add_argument("--inherit-video-token-from", type=int, metavar="PID")
            command.add_argument(
                "--seconds",
                type=int,
                choices=range(15, 61),
                default=20,
                metavar="15..60",
            )
            command.add_argument("--variants", default=",".join(VARIANTS))
            command.add_argument(
                "--url",
                help="Optional external RTSP URL; omitted = synthetic local RTSP plus finite MP4",
            )
            command.add_argument("--keep-prefixes", action="store_true")
        if name == "install":
            command.add_argument(
                "--variant",
                choices=("binary-patched", "source-patched"),
                default="binary-patched",
            )
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.error("This repository targets Linux x86_64 only")
    CACHE.mkdir(exist_ok=True)
    ART.mkdir(exist_ok=True)
    if args.command == "fixture":
        with fixture() as (url, _):
            print(url, flush=True)
            while True:
                time.sleep(1)
    else:
        {
            "fetch": fetch,
            "build": build,
            "patch": binary_patch,
            "probe": compile_probe,
            "reproduce": reproduce,
            "install": install,
        }[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
