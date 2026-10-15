# Fictional Journal fixtures v1

Three newly authored P02 observations: a consultation question, a timed symptom
with optional severity, and a retrospective symptom with only month precision
and no severity. They link to a new explicitly fictional, unconfirmed concern.
The observations do not assert a condition from P02's medical records.

Run `python track_2b/src/tools/journal_demo.py` from the repository root after
preparing the ordinary localhost client-demo accounts and applying migrations.
It uses actual OIDC, session/CSRF, authorization and Journal/care APIs, not SQL.
It never resets identities, records, datasets or evaluation history. Receipts and
local IDs remain ignored under `.runtime/journal-demo/`. Saved fixtures are not
recreated on reruns. Uncertain writes stop rather than replaying automatically.
The presence of a private editor draft also stops seeding to avoid interruption.

P14 is inspected without adding entries. Its empty-state result reflects the
actual installation; the command does not remove entries a tester has added.
These fixtures make no model calls and are not an Apertus evaluation result.
Content in `manifest.json` is released under CDLA-Permissive-2.0; see the
[dataset license text](../../src/intelligence/DATA_LICENSE.txt). Normal
application/source licensing is unchanged.
