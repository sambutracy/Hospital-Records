# Fictional Journal AI evaluation v1

This is a newly authored, entirely fictional text corpus for the Comfort Journal
proposal workflow. It contains no real people, patient records, generated model
answers, or external source material. Expected fields and evidence quotations
were written independently of Apertus output. The release is under
CDLA-Permissive-2.0; see `../../src/intelligence/DATA_LICENSE.txt`.

The manifest freezes development, validation, and held-out test partitions.
Cases cover numeric and qualitative severity, exact/partial/relative/unknown
dates, missing time, medication mentions, uncertainty, family history,
negation, hypothetical and conflicting statements, retrospective and recovery
notes, chronic care, abbreviations, Kenyan English, mixed English/Swahili,
prompt injection, unsupported requests, and empty input. One case always means
one patient narrative; no test expects automatic creation of multiple events.

Run `python src/tools/journal_ai_eval.py check` from `track_2b/` to validate the
frozen manifest and calculate the transparent deterministic baseline. After a
local Apertus endpoint is authorized, use `python src/tools/journal_ai_eval.py
run` to evaluate it. Live reports are written under ignored `.runtime/` and
never change the fixture. The harness records prompt, fixture, and code hashes,
field-level matches, schema/evidence validity, abstentions, and latency.

This is a small engineering evaluation set, not clinical validation or a
population-representative dataset. Results must report every attempted case,
including invalid responses, timeouts, and abstentions.
