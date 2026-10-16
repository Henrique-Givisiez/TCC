# Definitive environment lock references

The scientific runner identifies a definitive environment lock through the explicit
`path` and `sha256` in the supplied binding, rather than a prescribed filename.
The file must resolve within the repository and match its declared hash. The
binding hash, matching campaign HEAD, clean recorded/current tree, historical
lock/source-binding genealogy, protocol, seed plan and matrix checks remain in
force. Historical bindings remain supported under their existing contracts.

This permits an authorized pre-collection environmental refreeze without replacing
historical artifacts. Kernel and Docker Engine kernel differences remain fatal.
A changed runner requires a reviewed local commit and a new lock/binding captured
at that clean HEAD; earlier locks remain historical. Use explicit `--binding` and
`--binding-sha256`. A successful dry-run does not authorize scientific execution.
