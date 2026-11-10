import base64
import datetime
import html
import io
import re
import secrets

import streamlit as st

from data.repository import (
    TIPOS_DOCUMENTO_MEMBRO, buscar_documento_emitido, buscar_igreja_por_slug,
    carregar_cadastros, listar_documentos_emitidos, obter_logo_igreja,
    registrar_documento_emitido,
)
from modules.pix_brcode import gerar_qr_png
from utils.helpers import slug_da_sessao

URL_BASE_APP = "https://fielmordomo.streamlit.app"
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
]
AZUL_FIELMORDOMO = (0x06 / 255, 0x1B / 255, 0x44 / 255)  # #061B44, cor padrao do sistema
VERSO_APRESENTACAO = "Deixai vir a mim as criancinhas (Marcos 10:14)"
CERTIFICADOS = (
    "Certificado de Apresentação de Crianças",
    "Certificado de Batismo",
    "Certificado de Consagração de Obreiros",
    "Certificado de Treinamento de Lideranças",
)


def _data_extenso(data):
    return f"{data.day} de {MESES[data.month - 1]} de {data.year}"


def _data_de(valor):
    """Converte a data guardada no cadastro (ISO ou dd/mm/aaaa) para date."""
    if isinstance(valor, datetime.date):
        return valor
    texto = str(valor or "").strip()[:10]
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _data_br(valor):
    data = _data_de(valor)
    return data.strftime("%d/%m/%Y") if data else str(valor or "")


def _cpf_mascarado(cpf):
    digitos = re.sub(r"\D", "", str(cpf or ""))
    if len(digitos) != 11:
        return ""
    return f"***.{digitos[3:6]}.***-**"


def _foto_bytes(foto_data_uri):
    if not foto_data_uri or "," not in str(foto_data_uri):
        return None
    try:
        return base64.b64decode(str(foto_data_uri).split(",", 1)[1])
    except (ValueError, TypeError):
        return None


def _logo_png(slug):
    """Logo da igreja como PNG (o ReportLab nao le WEBP), ou None se nao houver."""
    from PIL import Image

    logo = obter_logo_igreja(slug)
    if not logo:
        return None
    dados, _extensao = logo
    try:
        imagem = Image.open(io.BytesIO(dados)).convert("RGBA")
    except (OSError, ValueError):
        return None
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


def _url_verificacao(slug, codigo):
    return f"{URL_BASE_APP}/?verificar={slug}.{codigo}"


def _novo_codigo():
    # token_urlsafe usa letras, numeros, "-" e "_", nunca ponto, que separa slug e codigo na URL
    return secrets.token_urlsafe(9)


def gerar_carteirinha_pdf(igreja_nome, membro, url_verificacao, logo_png=None):
    """Carteirinha no tamanho de cartao (85,6 x 54 mm), com logo, funcao, foto 3x4 e QR."""
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    largura, altura = 85.6 * mm, 54 * mm
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(largura, altura))
    c.setTitle(f"Carteirinha - {membro['nome']}")

    c.setFillColorRGB(*AZUL_FIELMORDOMO)
    c.rect(0, altura - 12 * mm, largura, 12 * mm, fill=1, stroke=0)
    texto_cabecalho_x = 3 * mm
    if logo_png:
        c.setFillColorRGB(1, 1, 1)
        c.roundRect(2 * mm, altura - 11 * mm, 9 * mm, 9 * mm, 1.5 * mm, fill=1, stroke=0)
        c.drawImage(ImageReader(io.BytesIO(logo_png)), 2.5 * mm, altura - 10.5 * mm, 8 * mm, 8 * mm,
                    preserveAspectRatio=True, anchor="c", mask="auto")
        texto_cabecalho_x = 13 * mm
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(texto_cabecalho_x, altura - 7.5 * mm, igreja_nome[:40])

    foto_x, foto_w, foto_h = 4 * mm, 20 * mm, 26.7 * mm
    foto_y = altura - 12 * mm - 3 * mm - foto_h
    foto = _foto_bytes(membro.get("foto"))
    if foto:
        c.drawImage(ImageReader(io.BytesIO(foto)), foto_x, foto_y, foto_w, foto_h,
                    preserveAspectRatio=True, anchor="c")
    else:
        c.setStrokeColorRGB(0.6, 0.6, 0.6)
        c.rect(foto_x, foto_y, foto_w, foto_h, fill=0, stroke=1)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.setFont("Helvetica", 6)
        c.drawCentredString(foto_x + foto_w / 2, foto_y + foto_h / 2, "Sem foto")

    texto_x = 28 * mm
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(texto_x, altura - 19 * mm, membro["nome"][:34])
    c.setFont("Helvetica", 7)
    c.drawString(texto_x, altura - 24 * mm, (membro.get("funcao") or membro.get("tipo_membro") or "Membro")[:34])
    if membro.get("cpf_mascarado"):
        c.drawString(texto_x, altura - 28 * mm, f"CPF {membro['cpf_mascarado']}")

    qr = ImageReader(io.BytesIO(gerar_qr_png(url_verificacao)))
    c.drawImage(qr, largura - 21 * mm, 4 * mm, 17 * mm, 17 * mm)
    c.setFont("Helvetica", 5)
    c.drawCentredString(largura - 12.5 * mm, 2 * mm, "Verificar")

    c.showPage()
    c.save()
    return buffer.getvalue()


def gerar_certificado_pdf(igreja_nome, logo_png, cidade, tipo, texto, codigo, url_verificacao):
    """Certificado em formato de diploma (A4 paisagem), com moldura, logo e QR de verificacao."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    azul = colors.HexColor("#1F3A68")
    dourado = colors.HexColor("#B8963E")
    cinza = colors.HexColor("#6B6B6B")
    pagina = landscape(A4)
    largura, altura = pagina

    def moldura(canvas_pdf, _doc):
        canvas_pdf.saveState()
        canvas_pdf.setStrokeColor(azul)
        canvas_pdf.setLineWidth(3)
        canvas_pdf.rect(1.0 * cm, 1.0 * cm, largura - 2.0 * cm, altura - 2.0 * cm)
        canvas_pdf.setStrokeColor(dourado)
        canvas_pdf.setLineWidth(1)
        canvas_pdf.rect(1.35 * cm, 1.35 * cm, largura - 2.7 * cm, altura - 2.7 * cm)
        canvas_pdf.drawImage(ImageReader(io.BytesIO(gerar_qr_png(url_verificacao))),
                             2.2 * cm, 1.9 * cm, 2.2 * cm, 2.2 * cm)
        canvas_pdf.setFillColor(cinza)
        canvas_pdf.setFont("Times-Roman", 8)
        canvas_pdf.drawString(4.7 * cm, 3.0 * cm, f"Código de verificação: {codigo}")
        canvas_pdf.drawString(4.7 * cm, 2.5 * cm, "Confira a autenticidade em:")
        canvas_pdf.drawString(4.7 * cm, 2.1 * cm, url_verificacao)
        canvas_pdf.restoreState()

    centro = ParagraphStyle("centro", fontName="Times-Roman", fontSize=12, alignment=TA_CENTER,
                            leading=15, textColor=azul)
    igreja_estilo = ParagraphStyle("igreja", parent=centro, fontName="Times-Bold", fontSize=18, leading=22)
    titulo_estilo = ParagraphStyle("titulo", parent=centro, fontName="Times-Bold", fontSize=40,
                                   leading=46, spaceBefore=6)
    subtitulo_estilo = ParagraphStyle("subtitulo", parent=centro, fontName="Times-Italic", fontSize=20,
                                      leading=26, textColor=dourado)
    corpo = ParagraphStyle("corpo", parent=centro, fontName="Times-Roman", fontSize=15, leading=22,
                           textColor=colors.black, spaceBefore=14, spaceAfter=10)
    assinatura = ParagraphStyle("assinatura", parent=centro, fontSize=11)

    historia = []
    if logo_png:
        historia.append(Image(io.BytesIO(logo_png), 2.6 * cm, 2.6 * cm, kind="proportional"))
    historia += [
        Paragraph(html.escape(igreja_nome), igreja_estilo),
        Paragraph("CERTIFICADO", titulo_estilo),
        Paragraph(html.escape(tipo.replace("Certificado de ", "")), subtitulo_estilo),
        Paragraph(html.escape(texto), corpo),
        Spacer(1, 0.6 * cm),
        Paragraph(f"{html.escape(cidade)}, {_data_extenso(datetime.date.today())}.", centro),
        Spacer(1, 1.4 * cm),
    ]
    linha_assinaturas = Table(
        [
            [Paragraph("_________________________", assinatura), Paragraph("_________________________", assinatura)],
            [Paragraph("Pastor(a) presidente", assinatura), Paragraph("Secretário(a)", assinatura)],
        ],
        colWidths=[9.5 * cm, 9.5 * cm],
    )
    linha_assinaturas.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    historia.append(linha_assinaturas)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=pagina, leftMargin=2.5 * cm, rightMargin=2.5 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm, title=tipo)
    doc.build(historia, onFirstPage=moldura, onLaterPages=moldura)
    return buffer.getvalue()


def _pomba(c, x, y, tamanho):
    """Pomba do Espirito Santo com formas simples. x, y marcam o centro do corpo."""
    t = tamanho
    contorno = (0.02, 0.11, 0.27)
    c.saveState()
    c.setLineWidth(1.2)
    c.setStrokeColorRGB(*contorno)
    c.setFillColorRGB(1, 1, 1)
    rabo = c.beginPath()
    rabo.moveTo(x - 0.55 * t, y + 0.02 * t)
    rabo.lineTo(x - 0.95 * t, y + 0.22 * t)
    rabo.lineTo(x - 0.9 * t, y - 0.08 * t)
    rabo.close()
    c.drawPath(rabo, fill=1, stroke=1)
    c.ellipse(x - 0.6 * t, y - 0.28 * t, x + 0.42 * t, y + 0.28 * t, fill=1, stroke=1)
    asa = c.beginPath()
    asa.moveTo(x - 0.25 * t, y + 0.06 * t)
    asa.curveTo(x - 0.35 * t, y + 0.7 * t, x + 0.12 * t, y + 0.72 * t, x + 0.2 * t, y + 0.15 * t)
    asa.close()
    c.drawPath(asa, fill=1, stroke=1)
    c.circle(x + 0.45 * t, y + 0.24 * t, 0.2 * t, fill=1, stroke=1)
    bico = c.beginPath()
    bico.moveTo(x + 0.62 * t, y + 0.27 * t)
    bico.lineTo(x + 0.82 * t, y + 0.21 * t)
    bico.lineTo(x + 0.62 * t, y + 0.18 * t)
    bico.close()
    c.setFillColorRGB(0.99, 0.78, 0.24)
    c.drawPath(bico, fill=1, stroke=1)
    c.restoreState()


def _sol(c, x, y, raio):
    import math

    c.saveState()
    c.setStrokeColorRGB(1.0, 0.78, 0.24)
    c.setLineWidth(3)
    c.setLineCap(1)
    for i in range(12):
        angulo = i * math.pi / 6
        c.line(x + raio * 1.2 * math.cos(angulo), y + raio * 1.2 * math.sin(angulo),
               x + raio * 1.5 * math.cos(angulo), y + raio * 1.5 * math.sin(angulo))
    c.setFillColorRGB(1.0, 0.85, 0.35)
    c.circle(x, y, raio, fill=1, stroke=0)
    c.restoreState()


def _nuvem(c, x, y, escala):
    c.saveState()
    c.setFillColorRGB(0.84, 0.93, 0.98)
    for dx, dy, r in [(-1.0, 0.0, 0.6), (-0.3, 0.45, 0.85), (0.5, 0.3, 0.7), (1.1, -0.05, 0.55)]:
        c.circle(x + dx * escala, y + dy * escala, r * escala, fill=1, stroke=0)
    c.rect(x - 1.6 * escala, y - 0.6 * escala, 3.2 * escala, 0.6 * escala, fill=1, stroke=0)
    c.restoreState()


def _flor(c, x, y, raio, cor_petala):
    import math

    c.saveState()
    c.setFillColor(cor_petala)
    for i in range(5):
        angulo = i * 2 * math.pi / 5 + math.pi / 2
        c.circle(x + raio * 0.6 * math.cos(angulo), y + raio * 0.6 * math.sin(angulo), raio * 0.5,
                 fill=1, stroke=0)
    c.setFillColorRGB(1.0, 0.85, 0.35)
    c.circle(x, y, raio * 0.35, fill=1, stroke=0)
    c.restoreState()


def _cordeiro(c, x, y, r):
    """Cordeirinho simples: corpo de bolinhas, cabeca escura e patas."""
    navy = (0.02, 0.11, 0.27)
    c.saveState()
    c.setFillColorRGB(0.91, 0.95, 0.98)
    for dx, dy, rr in [(-0.5, 0.0, 0.5), (0.0, 0.15, 0.55), (0.5, 0.0, 0.5), (0.2, -0.2, 0.45), (-0.2, -0.2, 0.45)]:
        c.circle(x + dx * r, y + dy * r, rr * r, fill=1, stroke=0)
    c.setFillColorRGB(*navy)
    c.circle(x + 0.85 * r, y + 0.3 * r, 0.3 * r, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.circle(x + 0.92 * r, y + 0.36 * r, 0.06 * r, fill=1, stroke=0)
    c.setStrokeColorRGB(*navy)
    c.setLineWidth(1.6)
    for px in (-0.35, 0.35):
        c.line(x + px * r, y - 0.45 * r, x + px * r, y - 0.8 * r)
    c.restoreState()


def _ramo_oliveira(c, x, y, comprimento):
    """Ramo de oliveira saindo do bico da pomba, com folhas em pares."""
    from reportlab.lib.units import cm

    verde_oliva = (0.42, 0.75, 0.29)
    c.saveState()
    c.setStrokeColorRGB(*verde_oliva)
    c.setLineWidth(2)
    c.line(x, y, x + comprimento, y + 0.15 * comprimento)
    c.setFillColorRGB(*verde_oliva)
    for i in range(1, 5):
        px = x + comprimento * i / 5
        py = y + 0.15 * comprimento * i / 5
        c.ellipse(px - 0.2 * cm, py + 0.05 * cm, px + 0.3 * cm, py + 0.45 * cm, fill=1, stroke=0)
        c.ellipse(px - 0.3 * cm, py - 0.45 * cm, px + 0.2 * cm, py - 0.05 * cm, fill=1, stroke=0)
    c.restoreState()


def gerar_certificado_infantil_pdf(igreja_nome, logo_png, cidade, texto, codigo, url_verificacao,
                                   verso=""):
    """Certificado de apresentacao de criancas em estilo infantil: cores vivas, arco-iris,
    estrelas e pomba, com a mesma informacao de verificacao dos demais certificados."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    creme = colors.HexColor("#FFF9EC")
    azul_ceu = colors.HexColor("#4FB3E8")
    amarelo = colors.HexColor("#FFC83D")
    rosa = colors.HexColor("#FF7AA2")
    verde = colors.HexColor("#6CC24A")
    navy = colors.HexColor("#061B44")
    pagina = landscape(A4)
    largura, altura = pagina

    def decoracao(canvas_pdf, _doc):
        canvas_pdf.saveState()
        canvas_pdf.setFillColor(creme)
        canvas_pdf.rect(0, 0, largura, altura, fill=1, stroke=0)
        canvas_pdf.setStrokeColor(azul_ceu)
        canvas_pdf.setLineWidth(8)
        canvas_pdf.roundRect(1.0 * cm, 1.0 * cm, largura - 2.0 * cm, altura - 2.0 * cm, 0.8 * cm,
                             fill=0, stroke=1)
        cores_bolinhas = [amarelo, rosa, verde, azul_ceu]
        for i in range(int((largura - 2.0 * cm) / (1.1 * cm))):
            cor = cores_bolinhas[i % len(cores_bolinhas)]
            canvas_pdf.setFillColor(cor)
            x = 1.5 * cm + i * 1.1 * cm
            canvas_pdf.circle(x, 1.5 * cm, 0.22 * cm, fill=1, stroke=0)
            canvas_pdf.circle(x, altura - 1.5 * cm, 0.22 * cm, fill=1, stroke=0)
        _sol(canvas_pdf, largura / 2, altura - 3.2 * cm, 0.95 * cm)
        _nuvem(canvas_pdf, 3.8 * cm, altura - 3.6 * cm, 0.9 * cm)
        _nuvem(canvas_pdf, largura - 3.8 * cm, altura - 3.6 * cm, 0.9 * cm)
        _flor(canvas_pdf, 3.2 * cm, altura - 7.4 * cm, 0.7 * cm, rosa)
        _flor(canvas_pdf, largura - 3.2 * cm, altura - 7.4 * cm, 0.7 * cm, amarelo)
        _pomba(canvas_pdf, largura - 7.5 * cm, 5.2 * cm, 1.3 * cm)
        _ramo_oliveira(canvas_pdf, largura - 7.5 * cm + 0.82 * 1.3 * cm, 5.2 * cm + 0.2 * 1.3 * cm, 2.4 * cm)
        _cordeiro(canvas_pdf, largura - 3.8 * cm, 3.4 * cm, 0.9 * cm)
        canvas_pdf.drawImage(ImageReader(io.BytesIO(gerar_qr_png(url_verificacao))),
                             2.4 * cm, 2.6 * cm, 2.2 * cm, 2.2 * cm)
        canvas_pdf.setFillColor(navy)
        canvas_pdf.setFont("Helvetica", 8)
        canvas_pdf.drawString(5.0 * cm, 4.2 * cm, f"Código de verificação: {codigo}")
        canvas_pdf.drawString(5.0 * cm, 3.7 * cm, "Confira a autenticidade em:")
        canvas_pdf.drawString(5.0 * cm, 3.3 * cm, url_verificacao)
        canvas_pdf.restoreState()

    centro = ParagraphStyle("centro_inf", fontName="Helvetica-Bold", fontSize=13, alignment=TA_CENTER,
                            leading=17, textColor=navy)
    igreja_estilo = ParagraphStyle("igreja_inf", parent=centro, fontSize=17, leading=21)
    titulo_estilo = ParagraphStyle("titulo_inf", parent=centro, fontSize=36, leading=42, spaceBefore=4,
                                   textColor=rosa)
    subtitulo_estilo = ParagraphStyle("subtitulo_inf", parent=centro, fontSize=22, leading=28,
                                      textColor=azul_ceu)
    corpo = ParagraphStyle("corpo_inf", parent=centro, fontName="Helvetica", fontSize=15, leading=22,
                           spaceBefore=12, spaceAfter=6)
    verso_estilo = ParagraphStyle("verso_inf", parent=centro, fontName="Helvetica-Oblique", fontSize=12,
                                  leading=16, textColor=verde, spaceAfter=8)
    assinatura = ParagraphStyle("assinatura_inf", parent=centro, fontSize=11)

    historia = []
    if logo_png:
        historia.append(Image(io.BytesIO(logo_png), 2.4 * cm, 2.4 * cm, kind="proportional"))
    historia += [
        Paragraph(html.escape(igreja_nome), igreja_estilo),
        Paragraph("CERTIFICADO", titulo_estilo),
        Paragraph("Apresentação de Crianças", subtitulo_estilo),
        Paragraph(html.escape(texto), corpo),
    ]
    if verso:
        historia.append(Paragraph(html.escape(verso), verso_estilo))
    historia += [
        Spacer(1, 0.4 * cm),
        Paragraph(f"{html.escape(cidade)}, {_data_extenso(datetime.date.today())}.", centro),
        Spacer(1, 1.0 * cm),
    ]
    linha_assinaturas = Table(
        [
            [Paragraph("_________________________", assinatura), Paragraph("_________________________", assinatura)],
            [Paragraph("Pastor(a) presidente", assinatura), Paragraph("Secretário(a)", assinatura)],
        ],
        colWidths=[9.5 * cm, 9.5 * cm],
    )
    linha_assinaturas.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    historia.append(linha_assinaturas)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=pagina, leftMargin=2.6 * cm, rightMargin=2.6 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title="Certificado de Apresentação de Crianças")
    doc.build(historia, onFirstPage=decoracao, onLaterPages=decoracao)
    return buffer.getvalue()


def gerar_documento_pdf(igreja_nome, cidade, titulo, paragrafos, codigo, url_verificacao):
    """Carta em A4, com espaco para assinatura e QR de verificacao."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

    estilos = getSampleStyleSheet()
    centro = ParagraphStyle("centro", parent=estilos["Normal"], alignment=TA_CENTER, fontSize=11)
    titulo_estilo = ParagraphStyle("titulo", parent=estilos["Title"], fontSize=18, spaceAfter=24)
    corpo = ParagraphStyle("corpo", parent=estilos["Normal"], fontSize=12, leading=18,
                           alignment=TA_JUSTIFY, spaceAfter=10)
    rodape = ParagraphStyle("rodape", parent=estilos["Normal"], fontSize=8,
                            alignment=TA_CENTER, textColor=colors.grey)

    historia = [
        Paragraph(html.escape(igreja_nome), centro),
        Spacer(1, 1.2 * cm),
        Paragraph(html.escape(titulo), titulo_estilo),
    ]
    historia += [Paragraph(html.escape(p), corpo) for p in paragrafos]
    historia += [
        Spacer(1, 1.2 * cm),
        Paragraph(f"{html.escape(cidade)}, {_data_extenso(datetime.date.today())}.", corpo),
        Spacer(1, 2.2 * cm),
        Paragraph("______________________________________", centro),
        Paragraph("Pastor(a) responsável", centro),
        Spacer(1, 1.6 * cm),
        Image(io.BytesIO(gerar_qr_png(url_verificacao)), 3 * cm, 3 * cm),
        Paragraph(
            f"Código de verificação: {html.escape(codigo)}<br/>"
            f"Confira a autenticidade em {html.escape(url_verificacao)}",
            rodape,
        ),
    ]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2.5 * cm, rightMargin=2.5 * cm,
                            topMargin=2.5 * cm, bottomMargin=2 * cm, title=titulo)
    doc.build(historia)
    return buffer.getvalue()


def _textos_carta(tipo, igreja_nome, membro, dados):
    """Titulo e paragrafos das cartas de recomendacao e transferencia."""
    nome = membro["nome"]
    cpf = f" (CPF {membro['cpf_mascarado']})" if membro.get("cpf_mascarado") else ""

    if tipo == "Carta de Recomendação":
        return "Carta de Recomendação", [
            f"A {igreja_nome} declara que {nome}{cpf} é membro desta igreja e está sendo "
            f"recomendado(a) para {dados['finalidade']}.",
            "Esta carta é emitida a pedido do(a) interessado(a), com a recomendação da liderança local.",
        ]
    if tipo == "Carta de Transferência":
        return "Carta de Transferência", [
            f"A {igreja_nome} transfere o membro {nome}{cpf}, para a {dados['destino']}, "
            "onde passará a congregar.",
            "A transferência é registrada nos arquivos desta igreja a partir da data de emissão.",
        ]
    raise ValueError("Tipo de carta invalido.")


def _texto_certificado(tipo, igreja_nome, membro, dados):
    """Texto do corpo do diploma para cada tipo de certificado."""
    nome = membro["nome"]
    cpf = f" (CPF {membro['cpf_mascarado']})" if membro.get("cpf_mascarado") else ""

    if tipo == "Certificado de Batismo":
        return (f"Certificamos que {nome}{cpf} foi batizado(a) nas águas em "
                f"{_data_br(membro.get('data_batismo_aguas'))}, conforme os registros desta igreja.")
    if tipo == "Certificado de Apresentação de Crianças":
        return (f"Certificamos que {dados['crianca']}, nascido(a) em {dados['nascimento'].strftime('%d/%m/%Y')}, "
                f"foi apresentado(a) ao Senhor na {igreja_nome}, em {dados['apresentacao'].strftime('%d/%m/%Y')}, "
                f"filho(a) de {nome}.")
    if tipo == "Certificado de Consagração de Obreiros":
        return (f"Certificamos que {nome}{cpf} foi consagrado(a) ao ministério de {dados['ministerio']} "
                f"na {igreja_nome}, em {dados['data'].strftime('%d/%m/%Y')}, para servir ao Senhor com dedicação.")
    if tipo == "Certificado de Treinamento de Lideranças":
        carga = f", com carga horária de {dados['carga']} horas" if dados.get("carga") else ""
        return (f"Certificamos que {nome}{cpf} concluiu o {dados['treinamento']}, realizado pela "
                f"{igreja_nome}, em {dados['data'].strftime('%d/%m/%Y')}{carga}.")
    raise ValueError("Tipo de certificado invalido.")


def pagina_verificacao(slug, codigo):
    """Pagina publica (?verificar=<slug>.<codigo>), sem login."""
    igreja = buscar_igreja_por_slug(slug)
    documento = buscar_documento_emitido(slug, codigo) if igreja else None

    st.title("Verificação de documento")
    if not documento:
        st.error("Documento não encontrado. Confira o código no documento ou peça uma nova via à igreja.")
        return

    st.success("Documento autêntico, emitido por esta igreja.")
    st.markdown(
        f"**Igreja:** {html.escape(igreja['nome'])}  \n"
        f"**Tipo:** {html.escape(documento['tipo'])}  \n"
        f"**Titular:** {html.escape(documento['nome_titular'])}  \n"
        f"**Emitido em:** {_data_br(documento['emitido_em'][:10])}  \n"
        f"**Código:** {html.escape(documento['codigo'])}"
    )


def render():
    slug = slug_da_sessao()
    if not slug:
        st.error("Sessão inválida. Faça login novamente.")
        return

    igreja = buscar_igreja_por_slug(slug)
    igreja_nome = igreja["nome"] if igreja else slug
    df = carregar_cadastros(slug)

    st.subheader("Documentos de membros")
    if df.empty:
        st.info("Cadastre membros para emitir documentos.")
        return

    membros = df.sort_values("nome")
    opcoes = [int(i) for i in membros["id_cadastro"]]
    nomes = dict(zip(opcoes, membros["nome"]))

    id_escolhido = st.selectbox(
        "Membro", opcoes, format_func=lambda i: nomes[i], key=f"doc_membro_{slug}",
    )
    linha = df[df["id_cadastro"] == id_escolhido].iloc[0].to_dict()
    membro = {
        "nome": str(linha.get("nome") or ""),
        "tipo_membro": linha.get("tipo_membro"),
        "funcao": str(linha.get("funcao") or ""),
        "cpf_mascarado": _cpf_mascarado(linha.get("cpf")),
        "data_batismo_aguas": linha.get("data_batismo_aguas"),
        "foto": linha.get("foto"),
        "situacao": str(linha.get("situacao") or ""),
    }

    tipo = st.selectbox("Tipo de documento", TIPOS_DOCUMENTO_MEMBRO, key=f"doc_tipo_{slug}")
    dados = {}
    if tipo == "Carta de Recomendação":
        dados["finalidade"] = st.text_input("Finalidade (ex.: congregar em outra igreja)", max_chars=160)
    elif tipo == "Carta de Transferência":
        dados["destino"] = st.text_input("Igreja de destino", max_chars=120)
    elif tipo == "Certificado de Apresentação de Crianças":
        dados["crianca"] = st.text_input("Nome da criança", max_chars=120)
        col1, col2 = st.columns(2)
        dados["nascimento"] = col1.date_input("Data de nascimento da criança", format="DD/MM/YYYY")
        dados["apresentacao"] = col2.date_input("Data da apresentação", value=datetime.date.today(),
                                                format="DD/MM/YYYY")
    elif tipo == "Certificado de Consagração de Obreiros":
        dados["ministerio"] = st.text_input("Ministério (ex.: Diaconato)", value=membro["funcao"], max_chars=80)
        dados["data"] = st.date_input("Data da consagração", value=datetime.date.today(), format="DD/MM/YYYY")
    elif tipo == "Certificado de Treinamento de Lideranças":
        dados["treinamento"] = st.text_input("Nome do treinamento", max_chars=120)
        col1, col2 = st.columns(2)
        dados["data"] = col1.date_input("Data de conclusão", value=datetime.date.today(), format="DD/MM/YYYY")
        dados["carga"] = col2.text_input("Carga horária (opcional, em horas)", max_chars=4)
    elif tipo == "Certificado de Batismo":
        st.caption(f"Usa a data de batismo nas águas do cadastro: {_data_br(membro['data_batismo_aguas']) or 'não informada'}.")

    cidade = ""
    if tipo != "Carteirinha":
        cidade = st.text_input("Cidade", max_chars=60, key=f"doc_cidade_{slug}")

    if st.button("Gerar documento", type="primary", key=f"doc_gerar_{slug}"):
        try:
            _gerar_e_oferecer(slug, igreja_nome, membro, tipo, dados, cidade, id_escolhido)
        except ValueError as ex:
            st.error(str(ex))

    st.divider()
    st.markdown("**Documentos emitidos para este membro**")
    emitidos = listar_documentos_emitidos(slug, id_escolhido)
    if emitidos:
        st.dataframe(
            [
                {
                    "Código": e["codigo"],
                    "Tipo": e["tipo"],
                    "Emitido em": _data_br(e["emitido_em"][:10]),
                }
                for e in emitidos
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("Nenhum documento emitido para este membro.")


def _validar(tipo, membro, dados, cidade):
    if not membro["nome"]:
        raise ValueError("Cadastro sem nome.")
    if tipo == "Carteirinha":
        if membro["situacao"].upper() != "ATIVO":
            raise ValueError("A carteirinha só pode ser emitida para membro ativo.")
        return
    if not cidade.strip():
        raise ValueError("Informe a cidade.")
    if tipo == "Carta de Recomendação" and not dados.get("finalidade", "").strip():
        raise ValueError("Informe a finalidade da carta.")
    if tipo == "Carta de Transferência" and not dados.get("destino", "").strip():
        raise ValueError("Informe a igreja de destino.")
    if tipo == "Certificado de Apresentação de Crianças":
        if not dados.get("crianca", "").strip():
            raise ValueError("Informe o nome da criança.")
        if dados["apresentacao"] < dados["nascimento"]:
            raise ValueError("A data de apresentação não pode ser anterior ao nascimento.")
    if tipo == "Certificado de Batismo" and not _data_de(membro.get("data_batismo_aguas")):
        raise ValueError("O cadastro não tem data de batismo nas águas.")
    if tipo == "Certificado de Consagração de Obreiros" and not dados.get("ministerio", "").strip():
        raise ValueError("Informe o ministério.")
    if tipo == "Certificado de Treinamento de Lideranças":
        if not dados.get("treinamento", "").strip():
            raise ValueError("Informe o nome do treinamento.")
        carga = dados.get("carga", "").strip()
        if carga and not carga.isdigit():
            raise ValueError("A carga horária deve ser um número inteiro de horas.")


def _gerar_e_oferecer(slug, igreja_nome, membro, tipo, dados, cidade, id_cadastro):
    cidade = cidade.strip()
    _validar(tipo, membro, dados, cidade)

    codigo = _novo_codigo()
    url = _url_verificacao(slug, codigo)
    logo = _logo_png(slug)
    if tipo == "Carteirinha":
        pdf = gerar_carteirinha_pdf(igreja_nome, membro, url, logo)
        descricao = "Carteirinha de membro"
    elif tipo == "Certificado de Apresentação de Crianças":
        texto = _texto_certificado(tipo, igreja_nome, membro, dados)
        pdf = gerar_certificado_infantil_pdf(igreja_nome, logo, cidade, texto, codigo, url,
                                             verso=VERSO_APRESENTACAO)
        descricao = tipo
    elif tipo in CERTIFICADOS:
        texto = _texto_certificado(tipo, igreja_nome, membro, dados)
        pdf = gerar_certificado_pdf(igreja_nome, logo, cidade, tipo, texto, codigo, url)
        descricao = tipo
    else:
        titulo, paragrafos = _textos_carta(tipo, igreja_nome, membro, dados)
        pdf = gerar_documento_pdf(igreja_nome, cidade, titulo, paragrafos, codigo, url)
        descricao = titulo

    registrar_documento_emitido(slug, codigo, tipo, id_cadastro, membro["nome"], descricao)
    st.success(f"Documento emitido. Código de verificação: {codigo}")
    st.download_button(
        "Baixar PDF",
        data=pdf,
        file_name=f"{tipo.lower().replace(' ', '_')}_{codigo}.pdf",
        mime="application/pdf",
        key=f"doc_baixar_{codigo}",
    )
