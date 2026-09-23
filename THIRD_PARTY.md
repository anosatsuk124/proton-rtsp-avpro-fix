# Third-party components

- Wine and the derived `mfmediaengine` patch are subject to Wine's LGPL-2.1-or-later licensing. The pinned source, its notices, and license are fetched into `.cache/`; consult `LICENSE` / `COPYING.LIB` in that source tree before distributing modified Wine binaries.
- Proton, SteamRT SDK, MediaMTX, FFmpeg, and their dependencies retain their upstream licenses. Their upstream artifacts are downloaded or accessed separately and are not tracked in this repository.
- AVPro Video is proprietary software by RenderHeads. Supply your own locally installed native plugin. No AVPro DLL, trial Unity package, decompiled code, or trial C# source is included here.
- Steam's video decoder libraries and runtime video token are local dependencies. They are not redistributed. The token is inherited only in memory for the requested diagnostic process.
- The small probe hosts and orchestration scripts in this repository were written for this local reproduction. The Unity graphics-interface ABI identifiers used by the native host correspond to Unity's public native-plugin interfaces.

No license is granted here for redistributing third-party components. This repository is prepared for local use; choose appropriate licensing for original helper code before publishing it.
