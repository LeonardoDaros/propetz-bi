"""Identidade visual do Propetz BI; sem acesso a dados, sessao ou app.py.

Chame apply_theme() depois de st.set_page_config(). Os demais helpers renderizam
um bloco HTML completo por chamada e aceitam apenas texto, nunca HTML externo.
"""
import html

import streamlit as st


COLORS = {
    "brand": "#00B2A9",
    "ink": "#2C2A29",
    "muted": "#52615E",
    "primary": "#006D66",
    "primary_hover": "#005750",
    "canvas": "#F5F7F6",
    "surface": "#FFFFFF",
    "border": "#DCE4E1",
    "input": "#eff6ff",
    "focus": "#006D66",
}

THEME_CSS = """
<style>
.agenda-kicker { color:#006D66; font-size:.72rem; letter-spacing:.09em; font-weight:700; text-transform:uppercase; }
.agenda-client { color:#2C2A29; font-size:1.13rem; line-height:1.4; font-weight:650; margin:.25rem 0; }
.agenda-next { color:#006D66; font-size:.87rem; line-height:1.5; padding:.5rem 0 .75rem; font-weight:600; }
.pp-stats-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1rem; }
@media(max-width:760px) { .pp-stats-grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:.6rem; } }
</style>
<style>
:root {
  --pp-brand: #00B2A9;
  --pp-ink: #2C2A29;
  --pp-muted: #52615E;
  --pp-primary: #006D66;
  --pp-hover: #005750;
  --pp-canvas: #F5F7F6;
  --pp-surface: #FFFFFF;
  --pp-border: #DCE4E1;
  --pp-radius: 12px;
  --pp-font: Gotham, "Avenir Next", "Segoe UI", Arial, sans-serif;
}

/* Fonte local: nenhum download e nenhuma alteracao nas fontes dos icones. */
.stApp, .stApp input, .stApp textarea, .stApp button, .stApp select {
  font-family: var(--pp-font);
}
.stApp { color: var(--pp-ink); background: var(--pp-canvas); }
.block-container {
  max-width: 1440px;
  padding: 2.25rem 2.4rem 3rem;
}
h1, h2, h3, h4 {
  color: var(--pp-ink);
  font-family: var(--pp-font);
  font-weight: 650;
  letter-spacing: -.035em;
}
h1 { font-size: clamp(1.8rem, 3vw, 2.6rem); line-height: 1.18; }
h2 { font-size: 1.45rem; line-height: 1.3; padding-top: 1.1rem; }
h3 { font-size: 1.15rem; line-height: 1.4; }
[data-testid="stMarkdownContainer"] p { line-height: 1.6; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
.stCaption, .stCaption p { color: var(--pp-muted); font-size: .83rem; line-height: 1.55; }
[data-testid="stMarkdownContainer"] a { color: var(--pp-primary); text-underline-offset: 3px; }
hr { margin: 1.4rem 0; border-color: var(--pp-border); }

/* Mantem controles nativos e botao de abrir a sidebar disponiveis no celular. */
[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid var(--pp-border); }
[data-testid="stSidebarUserContent"] { padding: 1.25rem 1.1rem 2rem; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .8rem; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { font-size: .86rem; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  font-size: .88rem; letter-spacing: 0; padding-top: .8rem;
}
[data-testid="stSidebar"] [data-baseweb="radio"] {
  min-height: 42px;
  padding: .55rem .65rem;
  border: 1px solid transparent;
  border-radius: 8px;
  margin: 0;
}
[data-testid="stSidebar"] [data-baseweb="radio"]:hover { background: #F0F6F4; }
[data-testid="stSidebar"] [data-baseweb="radio"]:focus-within {
  outline: 2px solid var(--pp-primary); outline-offset: 2px;
}
[data-testid="stSidebar"] [data-baseweb="radio"] p { font-size: .88rem; }

/* A cor azul dos campos e uma escolha operacional do usuario: preservar. */
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stNumberInput"] [data-baseweb="input"],
[data-testid="stDateInput"] [data-baseweb="input"],
[data-testid="stTextArea"] [data-baseweb="textarea"],
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
  background-color: #eff6ff !important;
  border: 1.5px solid #6388B2 !important;
  border-radius: 8px !important;
  min-height: 42px;
  color: var(--pp-ink);
}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input, [data-testid="stTextArea"] textarea {
  background-color: transparent !important;
  color: var(--pp-ink);
  font-size: .94rem;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stNumberInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder { color: #5C6B7D; }
[data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
[data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
[data-testid="stDateInput"] [data-baseweb="input"]:focus-within,
[data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within,
[data-testid="stSelectbox"] [data-baseweb="select"]:focus-within,
[data-testid="stMultiSelect"] [data-baseweb="select"]:focus-within {
  outline: 2px solid var(--pp-primary);
  outline-offset: 2px;
}
[data-testid="stWidgetLabel"] p { color: var(--pp-ink); font-weight: 550; font-size: .87rem; }
[data-testid="stForm"] {
  background: var(--pp-surface);
  border: 1px solid var(--pp-border);
  border-radius: var(--pp-radius);
  padding: 1.25rem;
}
[data-testid="stButton"] button,
[data-testid="stFormSubmitButton"] button,
[data-testid="stDownloadButton"] button {
  min-height: 42px;
  border-radius: 8px;
  font-weight: 600;
  padding: .55rem .95rem;
  border: 1px solid #B8CBC5;
  color: var(--pp-ink);
  background: #FFFFFF;
}
[data-testid="stButton"] button:hover,
[data-testid="stFormSubmitButton"] button:hover,
[data-testid="stDownloadButton"] button:hover {
  color: var(--pp-primary); border-color: var(--pp-primary); background: #EFF8F5;
}
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--pp-primary) !important;
  border-color: var(--pp-primary) !important;
  color: #FFFFFF !important;
}
[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: var(--pp-hover) !important;
  border-color: var(--pp-hover) !important;
  color: #FFFFFF !important;
}
button:focus-visible, a:focus-visible, [role="tab"]:focus-visible,
input:focus-visible, select:focus-visible, summary:focus-visible {
  outline: 2px solid var(--pp-primary) !important;
  outline-offset: 3px;
}
[data-testid="stButton"] button:disabled,
[data-testid="stFormSubmitButton"] button:disabled,
[data-testid="stDownloadButton"] button:disabled {
  background: #EDF0EF !important; color: #5E6966 !important;
  border-color: #CFD8D4 !important; cursor: not-allowed;
}

/* Mantem o componente Streamlit como fonte de comportamento e acessibilidade. */
[data-baseweb="tab-list"] { gap: .45rem; padding: .25rem 0 .5rem; }
[data-baseweb="tab"] {
  min-height: 42px; padding: .6rem 1rem;
  border-radius: 8px; color: var(--pp-muted); background: #EAF0ED;
}
[data-baseweb="tab"][aria-selected="true"] { background: #DDF4EE; color: #00574F; font-weight: 650; }
[data-testid="stExpander"] {
  background: var(--pp-surface); border: 1px solid var(--pp-border);
  border-radius: var(--pp-radius); box-shadow: none;
}
[data-testid="stExpander"] summary { min-height: 48px; padding: .9rem 1rem; }
[data-testid="stDataFrame"] {
  border: 1px solid var(--pp-border); border-radius: var(--pp-radius);
}
[data-testid="stPlotlyChart"] {
  border: 1px solid var(--pp-border); border-radius: var(--pp-radius);
  background: #FFFFFF; padding: .7rem;
}
[data-testid="stAlert"] { border-radius: 10px; }
[data-testid="stMetric"] {
  border: 1px solid var(--pp-border); border-top: 3px solid var(--pp-brand);
  border-radius: var(--pp-radius); background: #FFFFFF; padding: 1.1rem 1.2rem;
  box-shadow: none;
}
[data-testid="stMetricLabel"] { color: var(--pp-muted); font-size: .8rem; }
[data-testid="stMetricValue"] {
  color: var(--pp-ink); font-size: clamp(1.55rem, 2.6vw, 2.2rem);
  font-weight: 650; letter-spacing: -.045em;
}
[data-testid="stMetricDelta"] { font-size: .78rem; }

/* Blocos completos produzidos pelos helpers abaixo. */
.pp-hero {
  position: relative;
  display: flex; align-items: center; justify-content: space-between; gap: 2rem;
  padding: 1.6rem 2.1rem; margin: .25rem 0 1.1rem;
  border: 1px solid var(--pp-border); border-top: 4px solid var(--pp-brand);
  border-radius: var(--pp-radius); background: #FFFFFF;
}
.pp-hero-copy { min-width: 0; max-width: 900px; }
.pp-eyebrow {
  margin: 0 0 .75rem; font-size: .7rem; line-height: 1.5;
  font-weight: 750; letter-spacing: .16em; text-transform: uppercase;
  color: var(--pp-primary);
}
.pp-hero h1 {
  color: var(--pp-ink); font-size: clamp(1.8rem, 3.25vw, 3rem);
  font-weight: 650; line-height: 1.13; letter-spacing: -.055em;
  margin: 0 0 .85rem; padding: 0; overflow-wrap: anywhere;
}
.pp-hero-description {
  font-size: .96rem; color: var(--pp-muted); line-height: 1.65; margin: 0;
  max-width: 760px; overflow-wrap: anywhere;
}
.pp-hero-meta {
  display: inline-block; margin-top: 1.1rem; padding-top: .8rem;
  border-top: 1px solid var(--pp-border); color: var(--pp-muted);
  font-size: .76rem; line-height: 1.6; overflow-wrap: anywhere;
}
.pp-hero-mark { display: flex; gap: 6px; align-items: flex-end; height: 72px; flex: 0 0 auto; }
.pp-hero-mark span { display: block; width: 10px; border-radius: 3px; }
.pp-mark-short { height: 27px; background: #DDF4EE; }
.pp-mark-mid { height: 48px; background: #6DD2C5; }
.pp-mark-tall { height: 72px; background: var(--pp-brand); }
.pp-stat {
  --pp-stat-accent: #006D66;
  min-height: 128px; padding: 1.1rem; margin: 0 0 .5rem;
  border: 1px solid var(--pp-border); border-radius: var(--pp-radius);
  background: #FFFFFF; box-sizing: border-box;
}
.pp-stat-amber { --pp-stat-accent: #925000; }
.pp-stat-rose { --pp-stat-accent: #B02C3C; }
.pp-stat-blue { --pp-stat-accent: #305D9E; }
.pp-stat-neutral { --pp-stat-accent: #52615E; }
.pp-stat-label {
  display: flex; align-items: flex-start; gap: .5rem;
  color: var(--pp-muted); font-size: .79rem; font-weight: 600;
  line-height: 1.55; margin: 0 0 .9rem; overflow-wrap: anywhere;
}
.pp-stat-dot {
  display: inline-block; flex: 0 0 6px; width: 6px; height: 6px;
  margin-top: .42rem; border-radius: 50%; background: var(--pp-stat-accent);
}
.pp-stat-value {
  color: var(--pp-ink); font-size: clamp(1.65rem, 2.8vw, 2.4rem);
  font-weight: 650; line-height: 1.18; letter-spacing: -.055em;
  margin: 0; overflow-wrap: anywhere;
}
.pp-stat-detail {
  color: var(--pp-muted); font-size: .76rem; line-height: 1.6;
  margin: .8rem 0 0; overflow-wrap: anywhere;
}
.pp-identity { padding: .3rem 0 1.25rem; border-bottom: 1px solid var(--pp-border); margin-bottom: .25rem; }
.pp-brandline { display: flex; align-items: center; gap: .65rem; margin-bottom: 1.3rem; }
.pp-wordmark { font-size: 1.48rem; font-weight: 700; letter-spacing: -.06em; color: var(--pp-ink); }
.pp-brand-tag { padding: .18rem .4rem; border-radius: 4px; background: #DDF4EE; color: #00574F; font-size: .62rem; font-weight: 750; letter-spacing: .07em; }
.pp-profile { display: flex; gap: .7rem; align-items: center; }
.pp-profile-initials {
  display: flex; align-items: center; justify-content: center;
  width: 38px; height: 38px; flex: 0 0 38px; border-radius: 10px;
  background: #E4F5F0; color: #00574F; font-size: .78rem; font-weight: 700;
}
.pp-profile-copy { min-width: 0; }
.pp-profile-name { font-size: .82rem; font-weight: 650; line-height: 1.4; color: var(--pp-ink); overflow-wrap: anywhere; }
.pp-profile-role { font-size: .73rem; color: var(--pp-muted); margin-top: .18rem; line-height: 1.4; overflow-wrap: anywhere; }
.pp-login-header {
  padding: 2.4rem; margin: 0 0 1.1rem; border-radius: var(--pp-radius);
  background: #173F3B; border-top: 4px solid var(--pp-brand); color: #FFFFFF;
}
.pp-login-header .pp-wordmark { color: #FFFFFF; font-size: 1.7rem; }
.pp-login-header .pp-brandline { margin-bottom: 2.4rem; }
.pp-login-header .pp-eyebrow { color: #9CE8DA; }
.pp-login-header h1 {
  margin: 0 0 1rem; padding: 0; font-size: clamp(2rem, 4vw, 3.35rem);
  font-weight: 650; letter-spacing: -.06em; line-height: 1.12; color: #FFFFFF;
}
.pp-login-description { color: #D9EAE5; margin: 0; font-size: .92rem; line-height: 1.65; }
.pp-login-track { margin-top: 2rem; padding-top: 1.1rem; border-top: 1px solid #456561; color: #D9EAE5; font-size: .72rem; letter-spacing: .04em; line-height: 1.6; }

/* Compatibilidade com os helpers de insights e badges das paginas existentes. */
.insight-card {
  padding: 1.05rem 1.15rem; margin-bottom: .8rem; background: #FFFFFF;
  border: 1px solid var(--pp-border); border-left: 3px solid var(--pp-primary);
  border-radius: 10px; box-shadow: none;
}
.insight-danger { border-left-color: #B02C3C; }
.insight-warning { border-left-color: #925000; }
.insight-success { border-left-color: var(--pp-primary); }
.insight-type { font-size: .64rem; text-transform: uppercase; letter-spacing: .12em; color: var(--pp-muted); font-weight: 750; margin-bottom: .4rem; }
.insight-text { font-size: .87rem; line-height: 1.6; color: var(--pp-ink); }
.insight-action { font-size: .79rem; line-height: 1.6; color: var(--pp-primary); margin-top: .55rem; font-weight: 600; }
.badge { display: inline-block; padding: .22rem .65rem; border-radius: 6px; font-size: .74rem; line-height: 1.5; font-weight: 600; }
.badge-green { color: #005C4B; background: #E2F5EE; }
.badge-yellow { color: #854600; background: #FFF0D6; }
.badge-red { color: #A12637; background: #FCE8EC; }
.badge-blue { color: #24518B; background: #E8F0FC; }

@media (max-width: 760px) {
  .block-container { padding: 1.4rem 1rem 2rem; }
  .pp-hero { padding: 1.35rem; gap: 1rem; margin-bottom: 1.15rem; }
  .pp-hero h1 { font-size: 1.95rem; }
  .pp-hero-description { font-size: .89rem; }
  .pp-hero-mark { display: none; }
  .pp-stat { min-height: 0; padding: 1.05rem; }
  .pp-stats-grid .pp-stat { padding: .8rem; margin: 0; }
  .pp-stats-grid .pp-stat-label { min-height: 2.45rem; margin-bottom: .45rem; }
  .pp-stats-grid .pp-stat-detail { display: none; }
  .pp-login-header { padding: 1.55rem; }
  .pp-login-header .pp-brandline { margin-bottom: 1.6rem; }
  .pp-login-header h1 { font-size: 2.25rem; }
  [data-testid="stForm"] { padding: 1rem; }
  [data-testid="stMetric"] { padding: .95rem; }
  [data-baseweb="tab"] { padding: .6rem .75rem; }
}
@media (prefers-reduced-motion: reduce) {
  .stApp *, .stApp *::before, .stApp *::after { scroll-behavior: auto !important; }
}
</style>
"""


def _text(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def apply_theme():
    """Aplica o tema estatico; nenhum dado de sessao entra no CSS."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def page_hero(eyebrow, title, description, meta=""):
    """Abertura editorial da pagina; meta descreve apenas a referencia informada."""
    meta_html = f'<div class="pp-hero-meta">{_text(meta)}</div>' if meta else ""
    st.markdown(
        f'<section class="pp-hero"><div class="pp-hero-copy">'
        f'<div class="pp-eyebrow">{_text(eyebrow)}</div>'
        f'<h1>{_text(title)}</h1><p class="pp-hero-description">{_text(description)}</p>'
        f'{meta_html}</div><div class="pp-hero-mark" aria-hidden="true">'
        '<span class="pp-mark-short"></span><span class="pp-mark-mid"></span>'
        '<span class="pp-mark-tall"></span></div></section>',
        unsafe_allow_html=True,
    )


def _stat_card_html(label, value, detail="", tone="teal"):
    """Indicador com texto livre escapado; cor nunca substitui o rotulo."""
    tones = {"teal": "teal", "green": "teal", "blue": "blue", "amber": "amber",
             "warning": "amber", "rose": "rose", "red": "rose", "danger": "rose",
             "neutral": "neutral"}
    safe_tone = tones.get(str(tone), "teal")
    detail_html = f'<p class="pp-stat-detail">{_text(detail)}</p>' if detail else ""
    return (
        f'<article class="pp-stat pp-stat-{safe_tone}">'
        '<div class="pp-stat-label"><span class="pp-stat-dot" aria-hidden="true"></span>'
        f'<span>{_text(label)}</span></div><div class="pp-stat-value">{_text(value)}</div>'
        f'{detail_html}</article>'
    )


def stat_card(label, value, detail="", tone="teal"):
    st.markdown(_stat_card_html(label, value, detail, tone), unsafe_allow_html=True)


def stats_grid(items):
    """Quatro indicadores no desktop; duas colunas no celular."""
    st.markdown('<div class="pp-stats-grid">' + ''.join(_stat_card_html(*item) for item in items) + '</div>',
                unsafe_allow_html=True)


def identity(name, role):
    """Identificacao de usuario na sidebar; a permissao continua sendo do app."""
    plain_name = str(name if name is not None else "")
    initials = "".join(part[0] for part in plain_name.split()[:2]).upper() or "P"
    role_labels = {"admin": "Administrador", "diretor": "Diretoria",
                   "vendedor": "Comercial", "garantia": "Assistência",
                   "garantia_master": "Assistência · Gestão"}
    role_label = role_labels.get(str(role), str(role if role is not None else ""))
    st.markdown(
        '<div class="pp-identity"><div class="pp-brandline">'
        '<span class="pp-wordmark">Propetz</span><span class="pp-brand-tag">BI</span></div>'
        f'<div class="pp-profile"><div class="pp-profile-initials" aria-hidden="true">{_text(initials)}</div>'
        f'<div class="pp-profile-copy"><div class="pp-profile-name">{_text(name)}</div>'
        f'<div class="pp-profile-role">{_text(role_label)}</div></div></div></div>',
        unsafe_allow_html=True,
    )


def login_header():
    """Apresentacao visual; formulario, autenticacao e sessao continuam no app."""
    st.markdown(
        '<section class="pp-login-header"><div class="pp-brandline">'
        '<span class="pp-wordmark">Propetz</span><span class="pp-brand-tag">BI</span></div>'
        '<div class="pp-eyebrow">Inteligência comercial</div>'
        '<h1>Seu próximo passo<br>começa aqui.</h1>'
        '<p class="pp-login-description">Clareza para vender. Cuidado em cada atendimento.</p>'
        '<div class="pp-login-track">DISTRIBUIÇÃO &nbsp; / &nbsp; ASSISTÊNCIA</div></section>',
        unsafe_allow_html=True,
    )
