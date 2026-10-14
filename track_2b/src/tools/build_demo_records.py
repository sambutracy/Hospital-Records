"""Generate exclusively fictional upload samples (optional dependency: reportlab)."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[2]/'data'/'demo'
SAMPLES={
    'comfort-demo-lab.pdf':('Laboratory report',[
        'Fictional Cedar Clinic','Patient: Fictional Example','Document date: September 2026',
        'Specimen collected: 20 September 2026','Hemoglobin: 11.2 g/dL',
        'Reference range printed by this fictional issuer: 12.0-16.0 g/dL.',
        'These values are invented engineering fixtures. No interpretation is supplied.']),
    'comfort-demo-prescription.pdf':('Prescription',[
        'Fictional Cedar Clinic','Patient: Fictional Example','Document date: 12 September 2026',
        'Fictional medicine A','Label strength: 5 mg','Frequency: fictional label schedule',
        'Prescribed only; whether the medicine was taken is not documented.',
        'This is not a valid prescription or a treatment recommendation.']),
    'comfort-demo-referral.pdf':('Referral',[
        'Fictional Lakeview Clinic','Patient: Fictional Example','Document date: not stated',
        'Referral for a fictional respiratory-clinic visit.','Suspected asthma; diagnosis not confirmed.',
        'Appointment booking and completion are unknown.',
        'No real referral or clinical assessment has been made.']),
    'comfort-demo-return-note.pdf':('Consultation note',[
        'Fictional Cedar Clinic','Patient: Fictional Example','Document date: October 2026',
        'Fictional clinician return note for a demonstration episode.',
        'Patient-reported update: fictional medicine A was not taken.',
        'This does not change the original prescription.',
        'Follow-up completion is unknown. No clinical findings are verified.'])}

def build():
    ROOT.mkdir(parents=True,exist_ok=True)
    heading=ParagraphStyle('Title',fontName='Helvetica-Bold',fontSize=21,leading=25,textColor=colors.HexColor('#143C4A'),spaceAfter=18)
    body=ParagraphStyle('Body',fontName='Helvetica',fontSize=12,leading=18,spaceAfter=9)
    notice=ParagraphStyle('Notice',parent=body,fontName='Helvetica-Bold',fontSize=10,textColor=colors.HexColor('#94511D'))
    for name,(title,lines) in SAMPLES.items():
        story=[Paragraph('FICTIONAL DEMO RECORD - NOT FOR CLINICAL USE',notice),Spacer(1,18),Paragraph(title,heading)]
        story.extend(Paragraph(escape(line),body) for line in lines)
        story.extend([Spacer(1,28),Paragraph('Authored with Codex assistance for Comfort. No real patient or issuing institution. Content: CDLA-Permissive-2.0.',notice)])
        SimpleDocTemplate(str(ROOT/name),pagesize=A4,leftMargin=55,rightMargin=55,topMargin=60,bottomMargin=60,
            title='Comfort fictional demo - '+title,author='Comfort project').build(story)
    print('Four fictional upload samples generated; originals contain no patient data.')

if __name__=='__main__': build()
