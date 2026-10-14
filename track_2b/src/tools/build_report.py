"""Render the public Markdown report (optional authoring dependency: reportlab)."""
import re
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'Comfort_Report.pdf'
NAVY=colors.HexColor('#143C4A')
body=ParagraphStyle('Body',fontName='Helvetica',fontSize=10,leading=13.5,spaceAfter=7,textColor=NAVY,splitLongWords=True)
title=ParagraphStyle('Title',parent=body,fontName='Helvetica-Bold',fontSize=22,leading=26,spaceAfter=14)
heading=ParagraphStyle('Heading',parent=body,fontName='Helvetica-Bold',fontSize=12,leading=16,spaceBefore=12,spaceAfter=6,keepWithNext=True)
cell=ParagraphStyle('Cell',parent=body,fontSize=9,leading=12,spaceAfter=0)

def inline(text):
    text=text.replace('\u2014','-').replace('\u2013','-').replace('\u2011','-').replace('\u2019',"'").replace('≤','<=')
    text=escape(text)
    def link(match):
        url=match.group(2)
        if not url.startswith('https://'):
            url='https://github.com/sambutracy/Hospital-Records/blob/main/track_2b/'+url
        return '<link href="'+url+'" color="#176E82">'+match.group(1)+'</link>'
    text=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,text)
    text=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',text)
    return re.sub(r'`([^`]+)`',r'<font name="Courier" size="8.8">\1</font>',text)

def footer(canvas,doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#D3DFE2'))
    canvas.line(50,38,A4[0]-50,38)
    canvas.setFont('Helvetica',8)
    canvas.setFillColor(NAVY)
    canvas.drawString(50,25,'Comfort | Hack Apertus 2B | Working draft, 14 October 2026')
    canvas.drawRightString(A4[0]-50,25,str(doc.page))
    canvas.restoreState()

def build():
    lines=(ROOT/'technical_report.md').read_text(encoding='utf-8').splitlines()
    story=[]
    index=0
    while index<len(lines):
        line=lines[index].strip()
        if not line:
            index+=1
            continue
        if line.startswith('|'):
            rows=[]
            while index<len(lines) and lines[index].strip().startswith('|'):
                value=lines[index].strip()
                if not re.fullmatch(r'[|\s:-]+',value):
                    rows.append([Paragraph(inline(text.strip()),cell) for text in value.strip('|').split('|')])
                index+=1
            table=Table(rows,colWidths=[133,A4[0]-233],repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E5F0F1')),
                ('LINEBELOW',(0,0),(-1,0),0.8,NAVY),('LINEBELOW',(0,1),(-1,-1),0.35,colors.HexColor('#D3DFE2')),
                ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
            story.extend([table,Spacer(1,9)])
            continue
        if line.startswith('# '): story.append(Paragraph(inline(line[2:]),title))
        elif line.startswith('## '): story.append(Paragraph(inline(line[3:]),heading))
        else: story.append(Paragraph(inline(line),body))
        index+=1
    SimpleDocTemplate(str(OUTPUT),pagesize=A4,rightMargin=50,leftMargin=50,topMargin=48,bottomMargin=50,
        title='Comfort - technical report draft',author='Comfort project',allowSplitting=True).build(story,onFirstPage=footer,onLaterPages=footer)
    print('Report rendered; validate page count and layout before submission.')

if __name__=='__main__': build()
