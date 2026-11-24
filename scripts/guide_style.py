# 生成中文项目说明的标题和表格样式。
from pathlib import Path
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT


def new_document(title):
    doc=Document();section=doc.sections[0];section.page_width=Inches(8.5);section.page_height=Inches(11)
    section.top_margin=section.bottom_margin=Inches(.7);section.left_margin=section.right_margin=Inches(.7)
    for name in ['Normal','Title','Heading 1','Heading 2']:
        style=doc.styles[name];style.font.name='Calibri';style._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'微软雅黑')
        style.font.color.rgb=RGBColor(0,0,0)
        style.font.underline=False
        for border in list(style._element.iter(qn('w:pBdr'))):border.getparent().remove(border)
    doc.styles['Normal'].font.size=Pt(11);doc.styles['Normal'].paragraph_format.space_after=Pt(6)
    doc.add_paragraph(title,'Title');return doc


def table(doc,headers,rows):
    t=doc.add_table(rows=1,cols=len(headers));t.style='Table Grid'
    for cell,text in zip(t.rows[0].cells,headers):cell.text=str(text)
    trPr=t.rows[0]._tr.get_or_add_trPr();repeat=OxmlElement('w:tblHeader');trPr.append(repeat)
    borders=OxmlElement('w:tblBorders')
    for edge in ['top','left','bottom','right','insideH','insideV']:
        el=OxmlElement('w:'+edge);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'4');el.set(qn('w:color'),'D9D9D9');borders.append(el)
    t._tbl.tblPr.append(borders)
    for row in rows:
        for c,text in zip(t.add_row().cells,row):c.text=str(text)
    widths=([1.35,5.75] if len(headers)==2 else
            [1.15,2.975,2.975] if len(headers)==3 and headers[0] in ['接口','模块'] else
            [7.1/len(headers)]*len(headers))
    t.autofit=False
    for col,width in zip(t.columns,widths):col.width=Inches(width)
    for row in t.rows:
        for cell,width in zip(row.cells,widths):
            cell.width=Inches(width);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            margins=OxmlElement('w:tcMar')
            for edge in ['top','left','bottom','right']:
                el=OxmlElement('w:'+edge);el.set(qn('w:w'),'80');el.set(qn('w:type'),'dxa');margins.append(el)
            cell._tc.get_or_add_tcPr().append(margins)
    for cell in t.rows[0].cells:
        shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'D9E6F2');cell._tc.get_or_add_tcPr().append(shade)
        for run in cell.paragraphs[0].runs:run.bold=True
    doc.add_paragraph();return t


