# Open-source-only policy

Local AI Companion is being developed as an open-source-only stack.

## Project rule

Mandatory runtime functionality must not depend on proprietary SDKs, closed-source desktop components, paid cloud APIs, hosted-only services, or vendor-locked infrastructure. The application must remain usable locally with source-available, inspectable components that are distributed under recognized open-source licenses.

Optional integrations must not make the core application depend on a proprietary service. A future connector may exist only as an optional adapter and must not replace the local open-source path.

## Dependency rule

Before adding a required dependency:

1. its source code and license must be publicly inspectable;
2. its license must be compatible with redistribution of this project;
3. the dependency must not silently upload companion data to a remote service;
4. an equivalent local workflow must remain possible without a proprietary account;
5. license and provenance should be recorded when release packaging is introduced.

The current Python application dependencies are intentionally from open-source projects. The backup encryption layer uses the open-source `cryptography` package rather than a proprietary security SDK.

## Models and media components

Model weights require the same care as application code. "Open weights" is not automatically the same thing as open source. Bundled defaults, documentation recommendations, and release presets should only point to model artifacts whose license permits the intended local use and redistribution. The exact license of a downloaded Ollama model/checkpoint/LoRA must be checked independently because users can install arbitrary third-party artifacts.

ComfyUI workflows are user-owned local configuration. A workflow may reference third-party checkpoints or custom nodes; those artifacts remain subject to their own licenses. The app should never claim that an arbitrary user-supplied model or node is open source merely because it runs locally.

## No telemetry by dependency

New dependencies must not introduce mandatory analytics, tracking, cloud crash reporting, remote moderation calls, or hidden network access. Network access in the core app is expected to target explicitly configured local endpoints such as Ollama and ComfyUI.

## Project license

Before the repository is made public as an open-source release, the copyright holder must choose and add an explicit OSI-approved project license. This policy deliberately does not choose GPL, AGPL, Apache, MIT, or another license on the user's behalf because that decision changes downstream redistribution rights.

Repository visibility and software licensing are separate decisions: a private development repository can use an open-source-only technical stack, but public redistribution requires an explicit project license.
