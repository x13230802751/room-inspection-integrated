"""English body, figure and table styles derived from the supplied project report."""
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips, RGBColor
from docx.opc.constants import RELATIONSHIP_TYPE as RT


def node(name, **attrs):
    element = OxmlElement("w:" + name)
    for key, value in attrs.items():
        element.set(qn("w:" + key), str(value))
    return element


def document(title):
    doc = Document()
    doc.core_properties.title = title
    doc.core_properties.author = "CIVL 7023 Task 1"
    doc.core_properties.subject = "Geometric measurement of modular rooms"
    doc.core_properties.comments = ""
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Twips(11906), Twips(16838)
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Twips(1418)
    sec.header_distance, sec.footer_distance = Twips(851), Twips(283)
    for name, size, bold in (("Normal",12,False),("Title",18,True),("Heading 1",16,True),("Heading 2",12,True),("Caption",10,False)):
        style = doc.styles[name]
        style.font.name, style.font.size, style.font.bold = "Times New Roman", Pt(size), bold
        style.font.italic, style.font.color.rgb = False, RGBColor.from_string("000000")
        rfonts=style.element.get_or_add_rPr().rFonts
        for key in ("asciiTheme","hAnsiTheme","eastAsiaTheme","cstheme"):
            rfonts.attrib.pop(qn("w:"+key), None)
        for key in ("ascii","hAnsi","eastAsia","cs"):
            rfonts.set(qn("w:"+key),"Times New Roman")
        pf=style.paragraph_format
        pf.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY if name=="Normal" else WD_ALIGN_PARAGRAPH.LEFT
        pf.line_spacing=1.0
        pf.space_before=Pt(0 if name in ("Normal","Title","Caption") else 6)
        pf.space_after=Pt(8 if name in ("Normal","Title") else 5)
        pf.keep_with_next=name in ("Title","Heading 1","Heading 2")
        props=style.element.get_or_add_pPr()
        for border in props.findall(qn("w:pBdr")):
            props.remove(border)
    footer = sec.footer.paragraphs[0]
    footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    footer.paragraph_format.space_after=Pt(0)
    for word in ("PAGE", "/", "NUMPAGES"):
        if word=="/":
            footer.add_run(" / ").font.size=Pt(9)
        else:
            field=node("fldSimple",instr=word)
            run=node("r")
            fmt=node("rPr")
            fmt.append(node("rFonts",ascii="Times New Roman",hAnsi="Times New Roman"))
            fmt.append(node("sz",val="18"))
            run.append(fmt)
            text=node("t"); text.text="1"; run.append(text)
            field.append(run); footer._p.append(field)
    return doc


def heading(doc, text, *, new_page=False):
    p=doc.add_heading(text,level=1)
    p.paragraph_format.page_break_before=new_page
    return p


def caption(doc, text, above=False):
    p=doc.add_paragraph(text, style="Caption")
    p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before=Pt(4)
    p.paragraph_format.space_after=Pt(4 if above else 8)
    p.paragraph_format.keep_with_next=above
    return p


def table(doc, title, columns, rows, widths, numeric=(), font_size=11):
    caption(doc,title,above=True)
    tab=doc.add_table(rows=0,cols=len(columns))
    tab.alignment=WD_TABLE_ALIGNMENT.CENTER
    tab.autofit=False
    body_width=11906-2*1418
    sizes=[round(body_width*w/sum(widths)) for w in widths]
    sizes[-1]=body_width-sum(sizes[:-1])
    for col,size in zip(tab.columns,sizes): col.width=Twips(size)
    pr=tab._tbl.tblPr
    borders=node("tblBorders")
    for edge in ("top","bottom","left","right","insideH","insideV"):
        borders.append(node(edge,val="single" if edge in ("top","bottom") else "nil",sz="8",color="20272A"))
    pr.append(borders)
    mar=node("tblCellMar")
    for edge,value in (("top",45),("bottom",45),("left",78),("right",78)):
        mar.append(node(edge,w=value,type="dxa"))
    pr.append(mar)
    for i,values in enumerate([columns,*rows]):
        row=tab.add_row()
        rpr=row._tr.get_or_add_trPr()
        rpr.append(node("cantSplit"))
        if i==0: rpr.append(node("tblHeader",val=1))
        for j,(cell,sz,value) in enumerate(zip(row.cells,sizes,values)):
            cell.width=Twips(sz)
            cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cp=cell._tc.get_or_add_tcPr()
            if i==0:
                br=node("tcBorders"); br.append(node("bottom",val="single",sz=4,color="737B80")); cp.append(br)
            p=cell.paragraphs[0]
            pf=p.paragraph_format
            pf.alignment=WD_ALIGN_PARAGRAPH.RIGHT if j in numeric else WD_ALIGN_PARAGRAPH.LEFT
            pf.space_before=pf.space_after=Pt(0)
            pf.line_spacing=1.0
            run=p.add_run(str(value)); run.font.size=Pt(font_size); run.bold=(i==0)
    return tab


def figure(doc, path, title, width=6.1):
    from docx.shared import Inches
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    pf=p.paragraph_format; pf.keep_with_next=True; pf.space_after=Pt(0)
    p.add_run().add_picture(str(path),width=Inches(width))
    caption(doc,title)


def link(p, label, url):
    h=OxmlElement("w:hyperlink")
    h.set(qn("r:id"),p.part.relate_to(url, RT.HYPERLINK, is_external=True))
    run=node("r"); fmt=node("rPr")
    fmt.append(node("color",val="174D67")); fmt.append(node("u",val="single")); run.append(fmt)
    t=node("t"); t.text=label; run.append(t); h.append(run); p._p.append(h)
