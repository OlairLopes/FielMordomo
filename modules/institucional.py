import base64
import logging
from pathlib import Path

import streamlit as st


AZUL_PRINCIPAL = "#0B3A66"
AZUL_ESCURO = "#082A4A"
AZUL_PROFUNDO = "#061F35"
AZUL_CLARO = "#EAF2FB"
DOURADO = "#D4AF37"
CINZA_TEXTO = "#1F2933"
CINZA_SUAVE = "#F5F7FA"
LOGGER = logging.getLogger(__name__)
TAMANHO_MAXIMO_LOGO = 5 * 1024 * 1024
MIMES_LOGO_PERMITIDOS = {
    "gif": "image/gif",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def _pagina_atual():
    pagina = st.query_params.get("pagina", "inicio")
    if isinstance(pagina, list):
        pagina = pagina[0] if pagina else "inicio"
    return str(pagina or "inicio").strip().lower()


def _img_b64(dados, ext):
    ext = str(ext or "png").lower().replace(".", "")
    mime = MIMES_LOGO_PERMITIDOS.get(ext)
    if not mime:
        raise ValueError(f"Formato de logo não permitido: {ext}")

    if not isinstance(dados, (bytes, bytearray, memoryview)):
        raise TypeError("Os dados do logo devem estar em formato binário.")

    if len(dados) > TAMANHO_MAXIMO_LOGO:
        raise ValueError("O logo excede o limite de 5 MB.")

    return "data:" + mime + ";base64," + base64.b64encode(dados).decode("utf-8")


def _logo_sistema_src():
    """
    Tenta carregar o logo oficial do FielMordomo.
    Ordem:
    1. Logo cadastrado no painel admin/sistema.
    2. Arquivos locais comuns em assets/static.
    3. Fallback textual.
    """
    # 1. Logo salvo no banco/configuração do sistema
    try:
        from data.repository import obter_logo_sistema, obter_logo_sidebar_sistema

        logo = obter_logo_sistema() or obter_logo_sidebar_sistema()
        if logo:
            dados, ext = logo
            return _img_b64(dados, ext)
    except Exception:
        LOGGER.exception("Não foi possível carregar o logo configurado no sistema.")

    # 2. Logo em arquivo local, caso exista no projeto
    try:
        base = Path(__file__).resolve().parents[1]
        candidatos = [
            base / "assets" / "logo_fielmordomo.png",
            base / "assets" / "logo.png",
            base / "static" / "logo_fielmordomo.png",
            base / "static" / "logo.png",
            base / "logo_fielmordomo.png",
            base / "logo.png",
        ]

        for arq in candidatos:
            if arq.exists() and arq.is_file():
                ext = arq.suffix.replace(".", "") or "png"
                return _img_b64(arq.read_bytes(), ext)
    except Exception:
        LOGGER.exception("Não foi possível carregar um logo local.")

    return ""


def _marca_fielmordomo_html():
    logo_src = _logo_sistema_src()

    if logo_src:
        return (
            '<a class="fm-logo fm-logo-com-imagem" href="?pagina=inicio" target="_top">'
            f'<img class="fm-logo-img" src="{logo_src}" alt="FielMordomo">'
            '</a>'
        )

    # Fallback textual corrigido: sem "Campo+Mordomo" e sem "Fiel+Mordomo".
    return '<a class="fm-logo" href="?pagina=inicio" target="_top">FielMordomo</a>'


def _css_base():
    return f"""
    <style>
        * {{
            box-sizing: border-box;
        }}

        html {{
            scroll-behavior: smooth;
        }}

        body {{
            margin: 0;
        }}

        .fm-page {{
            width: 100%;
            min-height: 100vh;
            background: {CINZA_SUAVE};
            color: {CINZA_TEXTO};
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
        }}

        .fm-navbar-wrap {{
            width: 100%;
            background: rgba(255, 255, 255, 0.97);
            border-bottom: 1px solid rgba(8, 42, 74, 0.08);
            position: sticky;
            top: 0;
            z-index: 999;
            backdrop-filter: blur(12px);
        }}

        .fm-navbar {{
            max-width: 1180px;
            margin: 0 auto;
            padding: 16px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
        }}

        .fm-logo {{
            font-size: 30px;
            font-weight: 800;
            color: {AZUL_ESCURO};
            letter-spacing: -0.8px;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            white-space: nowrap;
        }}

        .fm-logo span {{
            color: {DOURADO};
            font-weight: 900;
        }}

        .fm-logo-img {{
            display: block;
            width: auto;
            height: auto;
            max-width: 240px;
            max-height: 72px;
            object-fit: contain;
        }}

        .fm-menu {{
            display: flex;
            align-items: center;
            gap: 22px;
            flex-wrap: wrap;
        }}

        .fm-menu a {{
            color: {AZUL_ESCURO};
            text-decoration: none;
            font-size: 15px;
            font-weight: 650;
        }}

        .fm-menu a:hover {{
            color: {DOURADO};
        }}

        .fm-btn-login {{
            background: {AZUL_PRINCIPAL};
            color: white !important;
            padding: 10px 18px;
            border-radius: 10px;
            box-shadow: 0 8px 20px rgba(11, 58, 102, 0.22);
        }}

        .fm-hero {{
            max-width: 1180px;
            margin: 0 auto;
            padding: 68px 24px 44px;
            display: grid;
            grid-template-columns: 1.02fr 0.98fr;
            gap: 54px;
            align-items: center;
            position: relative;
        }}

        .fm-hero::before {{
            content: "";
            position: absolute;
            left: -80px;
            top: 105px;
            width: 360px;
            height: 360px;
            background:
                radial-gradient(circle at center, rgba(11,58,102,0.10), transparent 60%),
                linear-gradient(135deg, rgba(212,175,55,0.08), transparent);
            border-radius: 50%;
            z-index: 0;
        }}

        .fm-hero-text {{
            position: relative;
            z-index: 1;
        }}

        .fm-eyebrow {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: {AZUL_CLARO};
            color: {AZUL_PRINCIPAL};
            border: 1px solid rgba(11,58,102,0.12);
            padding: 7px 12px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 750;
            margin-bottom: 18px;
        }}

        .fm-hero h1 {{
            color: {AZUL_ESCURO};
            font-size: 48px;
            line-height: 1.08;
            letter-spacing: -1.6px;
            margin: 0 0 22px;
            font-weight: 850;
        }}

        .fm-hero p {{
            color: #405064;
            font-size: 18px;
            line-height: 1.7;
            margin-bottom: 30px;
            max-width: 610px;
        }}

        .fm-actions {{
            display: flex;
            gap: 14px;
            flex-wrap: wrap;
            align-items: center;
        }}

        .fm-primary {{
            background: {AZUL_PRINCIPAL};
            color: white !important;
            text-decoration: none;
            padding: 14px 22px;
            border-radius: 12px;
            font-weight: 750;
            box-shadow: 0 12px 28px rgba(11,58,102,0.24);
            display: inline-flex;
            gap: 10px;
            align-items: center;
        }}

        .fm-secondary {{
            background: white;
            color: {AZUL_PRINCIPAL} !important;
            text-decoration: none;
            padding: 13px 22px;
            border-radius: 12px;
            font-weight: 750;
            border: 1px solid rgba(11,58,102,0.22);
            display: inline-flex;
            gap: 10px;
            align-items: center;
        }}

        .fm-dashboard {{
            background: linear-gradient(145deg, {AZUL_ESCURO}, {AZUL_PROFUNDO});
            border-radius: 24px;
            padding: 14px;
            box-shadow: 0 24px 55px rgba(8,42,74,0.24);
            position: relative;
        }}

        .fm-dashboard-inner {{
            background: #ffffff;
            border-radius: 16px;
            overflow: hidden;
            min-height: 360px;
            display: grid;
            grid-template-columns: 150px 1fr;
        }}

        .fm-sidebar {{
            background: linear-gradient(180deg, {AZUL_ESCURO}, {AZUL_PROFUNDO});
            color: white;
            padding: 18px 14px;
        }}

        .fm-side-logo {{
            font-weight: 800;
            font-size: 15px;
            margin-bottom: 22px;
        }}

        .fm-side-item {{
            font-size: 12px;
            padding: 8px 6px;
            color: rgba(255,255,255,0.82);
            display: flex;
            gap: 8px;
            align-items: center;
        }}

        .fm-main-panel {{
            padding: 18px;
            background: #F8FAFC;
        }}

        .fm-panel-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}

        .fm-panel-top h3 {{
            color: {AZUL_ESCURO};
            font-size: 18px;
            margin: 0;
        }}

        .fm-kpis {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-bottom: 12px;
        }}

        .fm-kpi {{
            background: white;
            border-radius: 10px;
            padding: 12px;
            border: 1px solid #EDF1F5;
        }}

        .fm-kpi small {{
            color: #64748B;
            font-size: 10px;
        }}

        .fm-kpi strong {{
            display: block;
            color: {AZUL_PRINCIPAL};
            font-size: 15px;
            margin-top: 4px;
        }}

        .fm-charts {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 12px;
        }}

        .fm-chart-box {{
            background: white;
            border-radius: 12px;
            padding: 14px;
            border: 1px solid #EDF1F5;
            min-height: 118px;
        }}

        .fm-chart-title {{
            color: {AZUL_ESCURO};
            font-size: 12px;
            font-weight: 800;
            margin-bottom: 12px;
        }}

        .fm-bars {{
            display: flex;
            gap: 10px;
            align-items: end;
            height: 70px;
        }}

        .fm-bar {{
            width: 15px;
            border-radius: 5px 5px 0 0;
            background: {AZUL_PRINCIPAL};
        }}

        .fm-bar.gold {{
            background: {DOURADO};
        }}

        .fm-donut {{
            width: 82px;
            height: 82px;
            border-radius: 50%;
            background: conic-gradient({AZUL_PRINCIPAL} 0 58%, {DOURADO} 58% 80%, #9DB6D3 80% 92%, #D7E3F0 92% 100%);
            margin: 4px auto;
            position: relative;
        }}

        .fm-donut::after {{
            content: "";
            position: absolute;
            width: 38px;
            height: 38px;
            border-radius: 50%;
            background: white;
            left: 22px;
            top: 22px;
        }}

        .fm-table {{
            background: white;
            border-radius: 12px;
            padding: 12px;
            border: 1px solid #EDF1F5;
        }}

        .fm-table-line {{
            display: grid;
            grid-template-columns: 0.8fr 1.8fr 1fr 1fr;
            gap: 8px;
            font-size: 10px;
            padding: 6px 0;
            border-bottom: 1px solid #EEF2F6;
            color: #475569;
        }}

        .fm-cards {{
            max-width: 1180px;
            margin: 0 auto;
            padding: 18px 24px 36px;
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 22px;
        }}

        .fm-card {{
            background: white;
            border-radius: 18px;
            padding: 26px;
            border: 1px solid rgba(8,42,74,0.07);
            box-shadow: 0 14px 34px rgba(8,42,74,0.08);
        }}

        .fm-icon {{
            width: 54px;
            height: 54px;
            border-radius: 16px;
            background: {AZUL_CLARO};
            color: {AZUL_PRINCIPAL};
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 25px;
            margin-bottom: 16px;
        }}

        .fm-card h3 {{
            color: {AZUL_ESCURO};
            margin: 0 0 10px;
            font-size: 20px;
        }}

        .fm-card p {{
            color: #516173;
            line-height: 1.65;
            margin: 0;
            font-size: 15px;
        }}

        .fm-section {{
            background: white;
            padding: 58px 24px;
        }}

        .fm-section-inner {{
            max-width: 1180px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 60px;
        }}

        .fm-section h2 {{
            color: {AZUL_ESCURO};
            font-size: 30px;
            margin: 0 0 16px;
        }}

        .fm-section p {{
            color: #4B5563;
            line-height: 1.75;
            font-size: 16px;
        }}

        .fm-list {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 13px;
            margin-top: 18px;
        }}

        .fm-list div {{
            display: flex;
            align-items: center;
            gap: 10px;
            color: #334155;
            font-weight: 650;
        }}

        .fm-check {{
            width: 22px;
            height: 22px;
            background: {AZUL_PRINCIPAL};
            color: white;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            flex-shrink: 0;
        }}

        .fm-cta {{
            background: linear-gradient(135deg, {AZUL_ESCURO}, {AZUL_PROFUNDO});
            padding: 48px 24px;
            color: white;
        }}

        .fm-cta-inner {{
            max-width: 1180px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 30px;
        }}

        .fm-cta h2 {{
            color: white;
            margin: 0 0 8px;
            font-size: 30px;
        }}

        .fm-cta p {{
            color: rgba(255,255,255,0.82);
            margin: 0;
            font-size: 16px;
        }}

        .fm-gold-btn {{
            background: {DOURADO};
            color: {AZUL_PROFUNDO} !important;
            text-decoration: none;
            padding: 14px 24px;
            border-radius: 12px;
            font-weight: 800;
            white-space: nowrap;
        }}

        .fm-footer {{
            background: {AZUL_PROFUNDO};
            color: rgba(255,255,255,0.78);
            padding: 22px 24px;
            border-top: 1px solid rgba(255,255,255,0.08);
        }}

        .fm-footer-inner {{
            max-width: 1180px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            gap: 20px;
            flex-wrap: wrap;
            font-size: 14px;
        }}

        .fm-footer a {{
            color: rgba(255,255,255,0.78);
            text-decoration: none;
            margin-left: 18px;
        }}

        .fm-footer a:hover {{
            color: {DOURADO};
        }}

        .fm-simple-page {{
            max-width: 920px;
            margin: 0 auto;
            padding: 58px 24px 80px;
        }}

        .fm-simple-card {{
            background: white;
            border-radius: 20px;
            padding: 38px;
            box-shadow: 0 14px 38px rgba(8,42,74,0.08);
            border: 1px solid rgba(8,42,74,0.08);
        }}

        .fm-simple-card h1 {{
            color: {AZUL_ESCURO};
            font-size: 36px;
            margin-top: 0;
        }}

        .fm-simple-card h2 {{
            color: {AZUL_PRINCIPAL};
            font-size: 22px;
            margin-top: 26px;
        }}

        .fm-simple-card p, .fm-simple-card li {{
            color: #4B5563;
            line-height: 1.75;
            font-size: 16px;
        }}

        @media (max-width: 900px) {{
            .fm-navbar {{
                align-items: flex-start;
                flex-direction: column;
            }}

            .fm-logo-img {{
                max-width: 190px;
                max-height: 58px;
            }}

            .fm-hero {{
                grid-template-columns: 1fr;
                padding-top: 42px;
            }}

            .fm-hero h1 {{
                font-size: 38px;
            }}

            .fm-cards {{
                grid-template-columns: 1fr;
            }}

            .fm-section-inner {{
                grid-template-columns: 1fr;
            }}

            .fm-cta-inner {{
                flex-direction: column;
                align-items: flex-start;
            }}

            .fm-dashboard-inner {{
                grid-template-columns: 1fr;
            }}

            .fm-sidebar {{
                display: none;
            }}

            .fm-kpis {{
                grid-template-columns: repeat(2, 1fr);
            }}

            .fm-charts {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
    """


def _navbar():
    return f"""
    <div class="fm-navbar-wrap">
        <div class="fm-navbar">
            {_marca_fielmordomo_html()}

            <div class="fm-menu">
                <a href="?pagina=inicio#sobre" target="_top">Sobre</a>
                <a href="?pagina=inicio#recursos" target="_top">Recursos</a>
                <a href="?pagina=contato" target="_top">Contato</a>
                <a href="?pagina=privacidade" target="_top">Privacidade LGPD</a>
                <a class="fm-btn-login" href="?pagina=login" target="_top">🔒 Acessar Sistema</a>
            </div>
        </div>
    </div>
    """


def _footer():
    return """
    <div class="fm-footer">
        <div class="fm-footer-inner">
            <div>FielMordomo © 2026 — Sistema de Gestão Financeira para Igrejas.</div>
            <div>
                <a href="?pagina=contato" target="_top">Contato</a>
                <a href="?pagina=privacidade" target="_top">Privacidade LGPD</a>
                <a href="?pagina=termos" target="_top">Termos de Uso</a>
            </div>
        </div>
    </div>
    """


def _home():
    return """
    <section class="fm-hero">
        <div class="fm-hero-text">
            <div class="fm-eyebrow">✦ Gestão Financeira para Igrejas</div>

            <h1>Gestão financeira simples, segura e organizada para Igrejas</h1>

            <p>
                Controle dízimos, ofertas, campanhas, missões, despesas, comprovantes
                e relatórios em uma única plataforma, com mais clareza para a tesouraria
                e mais transparência para a liderança.
            </p>

            <div class="fm-actions">
                <a class="fm-primary" href="?pagina=login" target="_top">🔒 Acessar Sistema</a>
                <a class="fm-secondary" href="#sobre">ⓘ Conheça o FielMordomo</a>
            </div>
        </div>

        <div class="fm-dashboard">
            <div class="fm-dashboard-inner">
                <div class="fm-sidebar">
                    <div class="fm-side-logo">FielMordomo</div>
                    <div class="fm-side-item">▣ Dashboard</div>
                    <div class="fm-side-item">◈ Contribuições</div>
                    <div class="fm-side-item">◇ Despesas</div>
                    <div class="fm-side-item">▤ Comprovantes</div>
                    <div class="fm-side-item">▥ Relatórios</div>
                    <div class="fm-side-item">⚙ Configurações</div>
                </div>

                <div class="fm-main-panel">
                    <div class="fm-panel-top">
                        <h3>Dashboard</h3>
                        <small>Igreja Exemplo ⌄</small>
                    </div>

                    <div class="fm-kpis">
                        <div class="fm-kpi"><small>Dízimos e Ofertas</small><strong>R$ 45.320,50</strong></div>
                        <div class="fm-kpi"><small>Campanhas e Missões</small><strong>R$ 12.680,75</strong></div>
                        <div class="fm-kpi"><small>Despesas</small><strong>R$ 18.540,30</strong></div>
                        <div class="fm-kpi"><small>Saldo do Período</small><strong>R$ 39.460,95</strong></div>
                    </div>

                    <div class="fm-charts">
                        <div class="fm-chart-box">
                            <div class="fm-chart-title">Receitas x Despesas</div>
                            <div class="fm-bars">
                                <div class="fm-bar" style="height:55px"></div>
                                <div class="fm-bar gold" style="height:32px"></div>
                                <div class="fm-bar" style="height:48px"></div>
                                <div class="fm-bar gold" style="height:28px"></div>
                                <div class="fm-bar" style="height:64px"></div>
                                <div class="fm-bar gold" style="height:36px"></div>
                                <div class="fm-bar" style="height:58px"></div>
                                <div class="fm-bar gold" style="height:30px"></div>
                            </div>
                        </div>

                        <div class="fm-chart-box">
                            <div class="fm-chart-title">Distribuição das Receitas</div>
                            <div class="fm-donut"></div>
                        </div>
                    </div>

                    <div class="fm-table">
                        <div class="fm-table-line"><strong>Data</strong><strong>Descrição</strong><strong>Categoria</strong><strong>Valor</strong></div>
                        <div class="fm-table-line"><span>10/06</span><span>Dízimo - João Silva</span><span>Dízimos</span><span>R$ 250,00</span></div>
                        <div class="fm-table-line"><span>10/06</span><span>Oferta - Culto</span><span>Ofertas</span><span>R$ 180,00</span></div>
                        <div class="fm-table-line"><span>09/06</span><span>Conta de Luz</span><span>Despesa</span><span>R$ 320,00</span></div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <section class="fm-cards">
        <div class="fm-card">
            <div class="fm-icon">▤</div>
            <h3>Controle Financeiro</h3>
            <p>Gerencie dízimos, ofertas, campanhas, missões e despesas com praticidade e confiança.</p>
        </div>

        <div class="fm-card">
            <div class="fm-icon">▥</div>
            <h3>Relatórios Claros</h3>
            <p>Relatórios completos e visuais que facilitam a análise e a prestação de contas à liderança.</p>
        </div>

        <div class="fm-card">
            <div class="fm-icon">♢</div>
            <h3>Segurança e Organização</h3>
            <p>Dados protegidos, acessos controlados e informações organizadas para maior transparência.</p>
        </div>
    </section>

    <section class="fm-section" id="sobre">
        <div class="fm-section-inner">
            <div>
                <h2>Sobre o FielMordomo</h2>
                <p>
                    O FielMordomo é uma plataforma de gestão financeira desenvolvida para apoiar igrejas,
                    congregações e ministérios na boa administração dos recursos confiados à sua responsabilidade.
                </p>
                <p>
                    O sistema auxilia tesourarias, secretarias, pastores e equipes administrativas no controle
                    de lançamentos, emissão de comprovantes, acompanhamento de relatórios e organização das
                    informações financeiras da igreja.
                </p>
            </div>

            <div id="recursos">
                <h2>Recursos principais</h2>
                <div class="fm-list">
                    <div><span class="fm-check">✓</span> Cadastro de membros e contribuintes</div>
                    <div><span class="fm-check">✓</span> Controle de dízimos, ofertas, campanhas e missões</div>
                    <div><span class="fm-check">✓</span> Registro de despesas e saídas</div>
                    <div><span class="fm-check">✓</span> Emissão de comprovantes</div>
                    <div><span class="fm-check">✓</span> Relatórios financeiros</div>
                    <div><span class="fm-check">✓</span> Backup e recuperação de dados</div>
                </div>
            </div>
        </div>
    </section>

    <section class="fm-cta">
        <div class="fm-cta-inner">
            <div>
                <h2>Pronto para organizar a gestão financeira da sua igreja?</h2>
                <p>
                    Mais controle, mais transparência e mais tempo para o que realmente importa:
                    o Reino de Deus.
                </p>
            </div>

            <a class="fm-gold-btn" href="?pagina=login" target="_top">🔒 Acessar Sistema</a>
        </div>
    </section>
    """


def _contato():
    return """
    <div class="fm-simple-page">
        <div class="fm-simple-card">
            <h1>Contato</h1>

            <p>
                Para dúvidas, suporte, sugestões ou informações sobre o FielMordomo,
                entre em contato pelos canais oficiais da administração do sistema.
            </p>

            <h2>Canais de atendimento</h2>

            <p><strong>E-mail:</strong> suporte@fielmordomo.com.br</p>
            <p><strong>Site:</strong> https://fielmordomo.com.br</p>

            <p>
                As solicitações serão analisadas pela equipe responsável, especialmente em casos relacionados
                a acesso, cadastro de igrejas, planos, backup, restauração de dados e orientações de uso.
            </p>
        </div>
    </div>
    """


def _privacidade():
    return """
    <div class="fm-simple-page">
        <div class="fm-simple-card">
            <h1>Pol&iacute;tica de Privacidade</h1>

            <p>
                O FielMordomo respeita a privacidade dos usuários e das instituições cadastradas.
                As informações inseridas no sistema são utilizadas para fins de gestão administrativa
                e financeira da igreja cadastrada.
            </p>

            <h2>1. Dados coletados</h2>
            <p>
                O sistema pode armazenar dados como nome da igreja, identificação da congregação,
                membros, lançamentos financeiros, categorias, formas de pagamento, datas, valores
                e demais informações necessárias à administração financeira.
            </p>

            <h2>2. Uso das informações</h2>
            <p>
                Os dados são utilizados para geração de relatórios, controle financeiro, emissão de comprovantes,
                acompanhamento de receitas e despesas, backup e organização administrativa.
            </p>

            <h2>3. Segurança</h2>
            <p>
                O acesso ao sistema é restrito a usuários autorizados. Recomenda-se que cada igreja mantenha
                suas credenciais protegidas e conceda acesso apenas a pessoas devidamente autorizadas.
            </p>

            <h2>4. Compartilhamento de dados</h2>
            <p>
                O FielMordomo não tem por finalidade vender, divulgar ou compartilhar dados das igrejas
                com terceiros para fins comerciais. As informações pertencem à instituição cadastrada.
            </p>

            <h2>5. Backup e recuperação</h2>
            <p>
                O sistema pode disponibilizar recursos de backup e restauração para proteger as informações
                administrativas, conforme o plano ou configuração utilizada.
            </p>

            <h2>6. Atualizações</h2>
            <p>
                Esta política poderá ser atualizada sempre que houver melhorias no sistema, alterações legais
                ou mudanças nas funcionalidades oferecidas.
            </p>
        </div>
    </div>
    """


def _termos():
    return """
    <div class="fm-simple-page">
        <div class="fm-simple-card">
            <h1>Termos de Uso</h1>

            <p>
                Ao utilizar o FielMordomo, o usuário declara estar ciente de que o sistema é uma ferramenta
                de apoio à gestão financeira e administrativa de igrejas, congregações e ministérios.
            </p>

            <h2>1. Responsabilidade pelo uso</h2>
            <p>
                A igreja ou instituição cadastrada é responsável pelas informações inseridas, conferência dos
                lançamentos, controle de usuários e validação dos relatórios gerados.
            </p>

            <h2>2. Acesso ao sistema</h2>
            <p>
                O acesso deve ser feito apenas por pessoas autorizadas. Cada usuário deve preservar suas
                credenciais e evitar compartilhamento indevido de login e senha.
            </p>

            <h2>3. Finalidade</h2>
            <p>
                O FielMordomo foi desenvolvido para registrar receitas, despesas, dízimos, ofertas, campanhas,
                missões, relatórios, comprovantes e demais informações relacionadas à administração financeira.
            </p>

            <h2>4. Integridade das informações</h2>
            <p>
                A precisão dos dados depende do correto preenchimento pelos usuários. A conferência periódica
                dos lançamentos é recomendada para manter a confiabilidade das informações.
            </p>

            <h2>5. Disponibilidade</h2>
            <p>
                O sistema poderá passar por atualizações, manutenções ou ajustes técnicos, visando preservar
                a segurança e estabilidade da aplicação.
            </p>

            <h2>6. Aceitação</h2>
            <p>
                O uso contínuo do sistema representa concordância com estes termos e com a política de
                privacidade aplicável.
            </p>
        </div>
    </div>
    """


def _conteudo_da_pagina():
    pagina = _pagina_atual()

    if pagina in ("", "inicio", "sobre", "recursos"):
        return _navbar() + _home() + _footer()

    if pagina == "contato":
        return _navbar() + _contato() + _footer()

    if pagina == "privacidade":
        return _navbar() + _privacidade() + _footer()

    if pagina == "termos":
        return _navbar() + _termos() + _footer()

    return _navbar() + _home() + _footer()


def _render_html(html_final: str):
    """
    Usa st.html quando disponivel para os links funcionarem no proprio app.
    Se a versao do Streamlit for antiga, usa st.markdown como alternativa.
    """
    if hasattr(st, "html"):
        st.html(html_final)
    else:
        st.markdown(html_final, unsafe_allow_html=True)


def render_institucional():
    st.markdown(
        """
        <style>
            .block-container {
                padding: 0 !important;
                max-width: 100% !important;
            }

            header[data-testid="stHeader"],
            #MainMenu,
            footer {
                display: none !important;
                visibility: hidden !important;
            }

            section[data-testid="stSidebar"] {
                display: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    html_final = _css_base() + '<div class="fm-page">' + _conteudo_da_pagina() + "</div>"
    _render_html(html_final)
