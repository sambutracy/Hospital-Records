# Fictional upload samples

These four one-page PDF originals were authored with Codex assistance for Comfort. All names, institutions, values, prescriptions and events are fictional engineering examples. They contain no real patient information, valid prescriptions, professional assessments or treatment recommendations. Content license: CDLA-Permissive-2.0; [full license](../../src/intelligence/DATA_LICENSE.txt).

After `make run`, sign in using a generated synthetic account. Upload the laboratory report, prescription and referral together, review their original text, and confirm only what is stated. Keep the lab's document month separate from its specimen day; the referral date and appointment status are unknown. A prescription does not establish that medicine was taken.

Select the desired originals for a private packet. Approve temporary read access to another synthetic account, and approve note submission to an episode separately. The invited account can use the return-note sample under that authority; the patient can accept or reject it. Saved contacts never grant access automatically. All sample uploads remain in your private demo database/volume rather than this directory.

The separate 30-source evaluation suite uses short text JSON fixtures, not these PDF files. Passing its citation/format checks is not clinical validation. Optional regeneration: run `src/tools/build_demo_records.py` with Python/reportlab; the app does not need reportlab to run or read the committed samples.
