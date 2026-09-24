import io
import re
import json
import hashlib
import cv2
import unicodedata
from datetime import date, datetime

import fitz  # PyMuPDF
import gspread
import numpy as np
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

# =========================================================
# CONFIGURAÇÃO
# =========================================================
st.set_page_config(
    page_title="Saldo de Contas | Grupo Dauto",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

SPREADSHEET_ID = "1jocHQg3sbv_v8KpPNK8Y4KWrSEmZW-Eee8k_ugLFnaI"
SHEET_CONTAS = "CONTAS"
SHEET_SALDOS = "SALDOS"
PAINEL_PASSWORD = "Dauto@10.10"

CONTAS_PADRAO = [
    # Empresa, Banco, Agência, Conta, Apelido, Ativa, Ordem
    ["DT TINTAS", "Banco do Brasil", "1231-9", "62.810-7", "DT TINTAS BB", "SIM", 1],
    ["ÉTICA", "Banco do Brasil", "1231-9", "62.686-4", "ÉTICA BB", "SIM", 2],
    ["MERCADO", "Banco do Brasil", "1231-9", "33.300-X", "MERCADO BB", "SIM", 3],
    ["V&T", "Banco do Brasil", "1231-9", "62.619-8", "V&T BB", "SIM", 4],
    ["ÚNICA", "Banco do Brasil", "1231-9", "62.608-2", "ÚNICA BB", "SIM", 5],

    ["ÚNICA ATACADISTA TINTAS LTDA", "Itaú", "654", "73733-7", "ÚNICA ITAÚ", "SIM", 6],
    ["DT TINTAS COMÉRCIO VAREJISTA", "Itaú", "654", "98240-4", "DT ITAÚ 98240-4", "SIM", 7],
    ["DAUTO TINTAS SERVIÇOS E PRODUTOS", "Itaú", "654", "98530-8", "DAUTO ITAÚ 98530-8", "SIM", 8],
    ["DT TINTAS COMÉRCIO VAREJISTA", "Itaú", "654", "99190-0", "DT ITAÚ 99190-0", "SIM", 9],
    ["DT TINTAS COMÉRCIO VAREJISTA", "Itaú", "654", "99191-8", "DT ITAÚ 99191-8", "SIM", 10],
    ["ÉTICA COMÉRCIO VAREJISTA DE TINTAS", "Itaú", "654", "99195-9", "ÉTICA ITAÚ 99195-9", "SIM", 11],
    ["ÉTICA COMÉRCIO VAREJISTA DE TINTAS", "Itaú", "654", "99200-7", "ÉTICA ITAÚ 99200-7", "SIM", 12],
    ["VET COMÉRCIO VAREJISTA DE TINTAS", "Itaú", "654", "99201-5", "V&T ITAÚ 99201-5", "SIM", 13],
    ["VET COMÉRCIO VAREJISTA DE TINTAS", "Itaú", "654", "99202-3", "V&T ITAÚ 99202-3", "SIM", 14],
    ["MERCADO DAS TINTAS EIRELI", "Itaú", "654", "99203-1", "MERCADO ITAÚ 99203-1", "SIM", 15],
    ["MERCADO DAS TINTAS LTDA", "Itaú", "654", "99204-9", "MERCADO ITAÚ 99204-9", "SIM", 16],
    ["DAUTO TINTAS LTDA", "Itaú", "654", "99205-6", "DAUTO ITAÚ 99205-6", "SIM", 17],
    ["DT TINTAS COMÉRCIO VAREJISTA", "Itaú", "1890", "99348-6", "DT ITAÚ 99348-6", "SIM", 18],
]

HEAD_CONTAS = ["EMPRESA", "BANCO", "AGENCIA", "CONTA", "APELIDO", "ATIVA", "ORDEM"]
HEAD_SALDOS = [
    "ID", "DATA", "EMPRESA", "BANCO", "AGENCIA", "CONTA", "SALDO",
    "ARQUIVO", "ORIGEM", "CONFIANCA", "DATA_HORA"
]

# =========================================================
# VISUAL
# =========================================================
st.markdown("""
<style>
    .stApp { background:#f4f7fb; }
    [data-testid="stSidebar"] { background:#123d70; }
    [data-testid="stSidebar"] * { color:white; }
    [data-testid="stSidebar"] .stRadio label { padding:8px 4px; }
    .hero {
        background:linear-gradient(135deg,#123d70,#1d568f);
        padding:24px 28px;border-radius:18px;color:white;margin-bottom:18px;
        box-shadow:0 10px 28px rgba(18,61,112,.15)
    }
    .hero h1 { margin:0;color:white;font-size:28px; }
    .hero p { margin:6px 0 0;color:#dbe9f6; }
    .card {
        background:white;border:1px solid #dde6f0;border-radius:15px;
        padding:17px 18px;min-height:128px;box-shadow:0 5px 18px rgba(18,61,112,.05)
    }
    .card .label { color:#6e7f94;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em; }
    .card .value { color:#17243a;font-size:24px;font-weight:800;margin-top:8px; }
    .card .sub { color:#7d8ca0;font-size:11px;margin-top:8px; }
    .total-card { background:#123d70;border-radius:15px;padding:18px;color:white;min-height:128px; }
    .total-card .label { color:#cbdced;font-size:11px;font-weight:700;text-transform:uppercase; }
    .total-card .value { font-size:28px;font-weight:800;margin-top:8px; }
    .small-note {color:#74849a;font-size:12px;}
    div[data-testid="stDataFrame"] {border:1px solid #dde6f0;border-radius:12px;overflow:hidden;}
</style>
""", unsafe_allow_html=True)

# =========================================================
# UTILITÁRIOS
# =========================================================
def norm(v):
    s = unicodedata.normalize("NFD", str(v or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().upper()

def norm_key(v):
    return re.sub(r"[^0-9A-Z]", "", norm(v))

def norm_bank(v):
    s = norm(v)
    if "ITAU" in s:
        return "ITAU"
    if s == "BB" or "BANCO DO BRASIL" in s:
        return "BB"
    return s

def brl(v):
    try:
        x = float(v)
        txt = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {txt}"
    except Exception:
        return "—"

def money_to_float(v):
    if v is None:
        return None
    s = str(v).strip().upper().replace("R$", "").replace(" ", "")
    negative = s.startswith("-") or s.endswith("D")
    s = re.sub(r"[CD]$", "", s).replace("-", "")
    # BR: 21.576,15
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        # OCR às vezes troca vírgula por ponto no decimal
        parts = s.split(".")
        if len(parts) == 2 and len(parts[-1]) == 2:
            pass
        else:
            s = s.replace(".", "")
    try:
        n = float(re.sub(r"[^0-9.]", "", s))
        return -n if negative else n
    except Exception:
        return None

def extract_money(line):
    vals = re.findall(r"(?:R\$\s*)?-?\s*\d{1,3}(?:\.\d{3})*,\d{2}\s*[CD]?|(?:R\$\s*)?-?\s*\d+,\d{2}\s*[CD]?", str(line), flags=re.I)
    if not vals:
        return None
    return money_to_float(vals[-1])

def clean_account(v):
    return str(v or "").strip().replace("–", "-").replace("—", "-").replace(" ", "")

def safe_date(v):
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    s = str(v or "")
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    try:
        return pd.to_datetime(s, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return s

# =========================================================
# GOOGLE SHEETS
# =========================================================
def credentials_from_secrets():
    """
    Aceita:
    [gcp_service_account]
    type = "service_account"
    ...
    """
    if "gcp_service_account" not in st.secrets:
        raise RuntimeError(
            "Credencial do Google não encontrada. Configure [gcp_service_account] "
            "no .streamlit/secrets.toml ou nos Secrets do Streamlit Cloud."
        )
    info = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    return Credentials.from_service_account_info(info, scopes=scopes)

@st.cache_resource(show_spinner=False)
def get_book():
    gc = gspread.authorize(credentials_from_secrets())
    return gc.open_by_key(SPREADSHEET_ID)

def ensure_worksheet(book, title, headers, rows=1000, cols=20):
    try:
        ws = book.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(title=title, rows=rows, cols=cols)
    first = ws.row_values(1)
    if first != headers:
        ws.update("A1", [headers])
    return ws

def prepare_database():
    book = get_book()
    ws_contas = ensure_worksheet(book, SHEET_CONTAS, HEAD_CONTAS, 200, 10)
    ws_saldos = ensure_worksheet(book, SHEET_SALDOS, HEAD_SALDOS, 5000, 15)

    existing = ws_contas.get_all_records()
    keys = {
        (norm_bank(r.get("BANCO")), norm_key(r.get("AGENCIA")), norm_key(r.get("CONTA")))
        for r in existing
    }
    missing = [
        row for row in CONTAS_PADRAO
        if (norm_bank(row[1]), norm_key(row[2]), norm_key(row[3])) not in keys
    ]
    if missing:
        ws_contas.append_rows(missing, value_input_option="USER_ENTERED")
    return book, ws_contas, ws_saldos

@st.cache_data(ttl=30, show_spinner=False)
def load_accounts():
    _, ws, _ = prepare_database()
    rows = ws.get_all_records()
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=HEAD_CONTAS)
    for c in HEAD_CONTAS:
        if c not in df.columns:
            df[c] = ""
    df["ORDEM"] = pd.to_numeric(df["ORDEM"], errors="coerce").fillna(999).astype(int)
    return df.sort_values("ORDEM").reset_index(drop=True)

@st.cache_data(ttl=15, show_spinner=False)
def load_balances():
    _, _, ws = prepare_database()
    rows = ws.get_all_records()
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=HEAD_SALDOS)
    for c in HEAD_SALDOS:
        if c not in df.columns:
            df[c] = ""
    df["SALDO"] = pd.to_numeric(
        df["SALDO"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
        errors="coerce"
    ).fillna(0)
    df["DATA"] = df["DATA"].apply(safe_date)
    return df

def find_registered_account(bank, agency, account):
    df = load_accounts()
    if df.empty:
        return None
    b, a, c = norm_bank(bank), norm_key(agency), norm_key(account)
    for _, r in df.iterrows():
        if norm_bank(r["BANCO"]) == b and norm_key(r["CONTA"]) == c:
            if not a or norm_key(r["AGENCIA"]) == a:
                return r.to_dict()
    # fallback pela conta + banco
    for _, r in df.iterrows():
        if norm_bank(r["BANCO"]) == b and norm_key(r["CONTA"]) == c:
            return r.to_dict()
    return None

def upsert_balances(items, position_date):
    _, _, ws = prepare_database()
    current = ws.get_all_values()
    header = current[0] if current else HEAD_SALDOS
    col = {name: i for i, name in enumerate(header)}
    index = {}
    for row_number, row in enumerate(current[1:], start=2):
        if len(row) <= max(col.get("DATA", 1), col.get("BANCO", 3), col.get("CONTA", 5)):
            continue
        key = (
            safe_date(row[col["DATA"]]),
            norm_bank(row[col["BANCO"]]),
            norm_key(row[col["CONTA"]]),
        )
        index[key] = row_number

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_rows = []
    updates = []
    for item in items:
        if not item.get("SELECIONAR", True):
            continue
        key = (safe_date(position_date), norm_bank(item["BANCO"]), norm_key(item["CONTA"]))
        rid = hashlib.sha1("|".join(key).encode()).hexdigest()[:16]
        row = [
            rid, safe_date(position_date), item.get("EMPRESA", ""), item.get("BANCO", ""),
            item.get("AGENCIA", ""), item.get("CONTA", ""), float(item.get("SALDO", 0)),
            item.get("ARQUIVO", ""), item.get("ORIGEM", ""), item.get("CONFIANCA", ""), now
        ]
        if key in index:
            updates.append((index[key], row))
        else:
            new_rows.append(row)

    for row_num, row in updates:
        ws.update(f"A{row_num}:K{row_num}", [row], value_input_option="USER_ENTERED")
    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")

    load_balances.clear()
    return len(new_rows), len(updates)

# =========================================================
# LEITURA / OCR
# =========================================================
@st.cache_resource(show_spinner=False)
def get_ocr():
    return RapidOCR()

def preprocess_image(pil_image):
    """
    Pré-processamento para OCR usando OpenCV.
    O projeto fixa Python 3.12 via runtime.txt para garantir compatibilidade
    com opencv-python-headless / RapidOCR no Streamlit Cloud.
    """
    img = np.array(pil_image.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    if gray.shape[1] < 1600:
        scale = 1600 / gray.shape[1]
        gray = cv2.resize(
            gray, None, fx=scale, fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    return gray

def ocr_image(pil_image):
    engine = get_ocr()
    img = preprocess_image(pil_image)
    result, _ = engine(img)
    if not result:
        return ""
    # RapidOCR: [box, text, score]
    lines = [str(x[1]) for x in result if len(x) >= 3 and float(x[2]) >= 0.35]
    return "\n".join(lines)

def pdf_text_or_ocr(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    for page in doc:
        text = page.get_text("text") or ""
        # Se há texto suficiente, não faz OCR.
        if len(re.sub(r"\s+", "", text)) >= 80:
            pages.append(text)
        else:
            pix = page.get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            pages.append(ocr_image(img))
    return "\n\n".join(pages)

def read_uploaded_file(uploaded):
    raw = uploaded.getvalue()
    name = uploaded.name.lower()
    if name.endswith(".pdf"):
        return pdf_text_or_ocr(raw)
    image = Image.open(io.BytesIO(raw))
    return ocr_image(image)

# =========================================================
# PARSERS
# =========================================================
def detect_bank(text, filename=""):
    t = norm(text)
    f = norm(filename)
    if "ITAU" in t or "SDO DISP P/ APLIC" in t or "ITAU" in f:
        return "ITAU"
    if "BB RENDE FACIL" in t or "BANCO DO BRASIL" in t or "AGENCIA E CONTA" in t:
        return "BB"
    return ""

def parse_itau(text, filename):
    """
    Estratégia:
    1) usa as 13 contas cadastradas como âncoras;
    2) localiza a conta no texto do PDF;
    3) procura SDO DISP P/ APLIC HOJE no bloco da conta;
    4) extrai o valor associado.
    Isso evita confundir saldos/movimentos intermediários.
    """
    accounts = load_accounts()
    itau = accounts[accounts["BANCO"].apply(norm_bank) == "ITAU"]
    flat = re.sub(r"[ \t]+", " ", text.replace("\r", "\n"))
    flat_norm = norm(flat)
    found = []

    # posições das contas conhecidas no documento
    anchors = []
    for _, acc in itau.iterrows():
        variants = {
            clean_account(acc["CONTA"]),
            norm_key(acc["CONTA"]),
        }
        positions = []
        for v in variants:
            if not v:
                continue
            p = flat_norm.find(norm(v))
            if p >= 0:
                positions.append(p)
        if positions:
            anchors.append((min(positions), acc.to_dict()))
    anchors.sort(key=lambda x: x[0])

    for idx, (start, acc) in enumerate(anchors):
        end = anchors[idx + 1][0] if idx + 1 < len(anchors) else min(len(flat_norm), start + 5000)
        block = flat_norm[start:end]
        # Padrões flexíveis para "SDO DISP P/ APLIC HOJE S/CPMF"
        marker = re.search(r"SDO\s+DISP.*?APLIC\s+HOJE", block, flags=re.S)
        saldo = None
        if marker:
            after = block[marker.start(): marker.start() + 500]
            vals = re.findall(r"(?:R\$\s*)?-?\s*\d{1,3}(?:\.\d{3})*,\d{2}|(?:R\$\s*)?-?\s*\d+,\d{2}", after)
            if vals:
                saldo = money_to_float(vals[0])

        # fallback: procura no texto original próximo à conta
        if saldo is None:
            conta = re.escape(clean_account(acc["CONTA"]))
            m = re.search(
                conta + r".{0,2500}?SDO\s+DISP.*?APLIC\s+HOJE.{0,250}?((?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}|(?:R\$\s*)?\d+,\d{2})",
                text, flags=re.I | re.S
            )
            if m:
                saldo = money_to_float(m.group(1))

        if saldo is not None:
            found.append({
                "SELECIONAR": True,
                "EMPRESA": acc["EMPRESA"],
                "BANCO": "Itaú",
                "AGENCIA": str(acc["AGENCIA"]),
                "CONTA": str(acc["CONTA"]),
                "SALDO": float(saldo),
                "STATUS": "Conta cadastrada",
                "ARQUIVO": filename,
                "ORIGEM": "SDO DISP P/ APLIC HOJE S/CPMF",
                "CONFIANCA": "ALTA",
            })
    return found

def extract_bb_account(text):
    t = text.replace("–", "-").replace("—", "-")
    # Exemplos: 1231-9 • 62810-7 / 1231-9 - 62608-2
    patterns = [
        r"(\d{3,5}\s*-\s*\d)\D{1,20}(\d{4,8}\s*-\s*[0-9Xx])",
        r"AG[EÊ]NCIA\s+E\s+CONTA.{0,120}?(\d{3,5}\s*-\s*\d).{0,30}?(\d{4,8}\s*-\s*[0-9Xx])",
    ]
    for p in patterns:
        m = re.search(p, t, flags=re.I | re.S)
        if m:
            return clean_account(m.group(1)), clean_account(m.group(2))

    # Fallback forte: compara as 5 contas BB cadastradas contra o OCR sem pontuação.
    compact = norm_key(t)
    accounts = load_accounts()
    bb = accounts[accounts["BANCO"].apply(norm_bank) == "BB"]
    for _, r in bb.iterrows():
        if norm_key(r["CONTA"]) in compact:
            return str(r["AGENCIA"]), str(r["CONTA"])
    return "", ""

def extract_bb_final_balance(text):
    """
    Regra solicitada: usar o 'Saldo' final, abaixo de Invest. Resgate Autom.,
    e não o 999 SALDO intermediário.
    """
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]
    candidates = []

    # Busca de baixo para cima por uma linha cujo rótulo seja SALDO.
    for i in range(len(lines) - 1, -1, -1):
        n = norm(lines[i])
        if re.match(r"^SALDO\b", n) and "999" not in n:
            val = extract_money(lines[i])
            if val is None:
                # OCR pode separar rótulo e valor em linhas consecutivas.
                for j in range(i + 1, min(i + 4, len(lines))):
                    val = extract_money(lines[j])
                    if val is not None:
                        break
            if val is not None:
                return val

    # Fallback: após "Invest. Resgate Autom." costuma haver o saldo final.
    full = "\n".join(lines)
    m = re.search(r"INVEST\.?\s*RESGATE\s*AUTOM.*?SALDO.{0,150}?(\d{1,3}(?:\.\d{3})*,\d{2})", full, flags=re.I | re.S)
    if m:
        return money_to_float(m.group(1))

    # Último valor monetário do documento como fallback de baixa confiança.
    for line in reversed(lines[-12:]):
        val = extract_money(line)
        if val is not None:
            candidates.append(val)
    return candidates[0] if candidates else None

def parse_bb(text, filename):
    agency, account = extract_bb_account(text)
    saldo = extract_bb_final_balance(text)
    if not account or saldo is None:
        return []
    acc = find_registered_account("BB", agency, account)
    return [{
        "SELECIONAR": True,
        "EMPRESA": acc["EMPRESA"] if acc else "",
        "BANCO": "Banco do Brasil",
        "AGENCIA": acc["AGENCIA"] if acc else agency,
        "CONTA": acc["CONTA"] if acc else account,
        "SALDO": float(saldo),
        "STATUS": "Conta cadastrada" if acc else "Conta não cadastrada",
        "ARQUIVO": filename,
        "ORIGEM": "Saldo final",
        "CONFIANCA": "ALTA" if acc else "MÉDIA",
    }]

def process_files(files, position_date):
    results, errors = [], []
    progress = st.progress(0, text="Preparando leitura...")
    total = len(files)

    for i, f in enumerate(files, 1):
        progress.progress((i - 1) / total, text=f"Lendo {i} de {total}: {f.name}")
        try:
            text = read_uploaded_file(f)
            if not text.strip():
                raise ValueError("Nenhum texto foi extraído.")
            bank = detect_bank(text, f.name)
            if bank == "ITAU":
                rows = parse_itau(text, f.name)
            elif bank == "BB":
                rows = parse_bb(text, f.name)
            else:
                rows = parse_itau(text, f.name)
                if not rows:
                    rows = parse_bb(text, f.name)
            if not rows:
                raise ValueError("Arquivo lido, mas não foi possível identificar conta e saldo.")
            results.extend(rows)
        except Exception as e:
            errors.append(f"{f.name}: {e}")

    progress.progress(1.0, text="Leitura concluída.")
    # Dedup por banco+conta
    unique = {}
    for r in results:
        unique[(norm_bank(r["BANCO"]), norm_key(r["CONTA"]))] = r
    return list(unique.values()), errors

# =========================================================
# DASHBOARD
# =========================================================
def render_dashboard():
    df = load_balances()
    accounts = load_accounts()
    if df.empty:
        st.info("Ainda não há saldos gravados.")
        return

    dates = sorted([x for x in df["DATA"].dropna().unique() if x], reverse=True)
    selected = st.selectbox(
        "Posição",
        dates,
        format_func=lambda x: pd.to_datetime(x).strftime("%d/%m/%Y"),
    )
    current = df[df["DATA"] == selected].copy()
    total = current["SALDO"].sum()

    st.markdown(
        f"""<div class="total-card">
        <div class="label">Saldo consolidado · {pd.to_datetime(selected).strftime('%d/%m/%Y')}</div>
        <div class="value">{brl(total)}</div>
        <div style="margin-top:8px;color:#cbdced;font-size:12px">{len(current)} conta(s) atualizada(s)</div>
        </div>""",
        unsafe_allow_html=True,
    )
    st.write("")

    current_map = {
        (norm_bank(r["BANCO"]), norm_key(r["CONTA"])): float(r["SALDO"])
        for _, r in current.iterrows()
    }

    active = accounts[accounts["ATIVA"].astype(str).str.upper().isin(["SIM", "TRUE", "1", "S"])]
    cols = st.columns(4)
    for i, (_, acc) in enumerate(active.iterrows()):
        saldo = current_map.get((norm_bank(acc["BANCO"]), norm_key(acc["CONTA"])))
        value = brl(saldo) if saldo is not None else "Não atualizado"
        cols[i % 4].markdown(
            f"""<div class="card">
            <div class="label">{acc['APELIDO'] or acc['EMPRESA']}</div>
            <div class="value">{value}</div>
            <div class="sub">{acc['BANCO']} · {acc['AGENCIA']} / {acc['CONTA']}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.subheader("Evolução do saldo consolidado")
    hist = df.groupby("DATA", as_index=False)["SALDO"].sum().sort_values("DATA")
    hist["DATA_DT"] = pd.to_datetime(hist["DATA"])
    st.line_chart(hist.set_index("DATA_DT")["SALDO"], height=300)

    st.subheader("Histórico consolidado")
    view = hist[["DATA", "SALDO"]].copy().sort_values("DATA", ascending=False)
    view["DATA"] = pd.to_datetime(view["DATA"]).dt.strftime("%d/%m/%Y")
    view["SALDO"] = view["SALDO"].apply(brl)
    st.dataframe(view.rename(columns={"DATA": "Data", "SALDO": "Saldo total"}), use_container_width=True, hide_index=True)

    st.subheader("Histórico por conta")
    pivot = df.pivot_table(index="DATA", columns="CONTA", values="SALDO", aggfunc="last").sort_index(ascending=False)
    pivot["TOTAL"] = pivot.sum(axis=1, skipna=True)
    pivot.index = pd.to_datetime(pivot.index).strftime("%d/%m/%Y")
    st.dataframe(pivot.style.format(lambda x: brl(x) if pd.notna(x) else "—"), use_container_width=True)

# =========================================================
# PÁGINAS
# =========================================================
def page_update():
    st.markdown("""<div class="hero"><h1>Atualizar Saldos</h1>
    <p>Importe o PDF do Itaú e as imagens do Banco do Brasil. Confira antes de gravar.</p></div>""", unsafe_allow_html=True)

    c1, c2 = st.columns([1, 3])
    with c1:
        position_date = st.date_input("Data da posição", value=date.today(), format="DD/MM/YYYY")
    with c2:
        files = st.file_uploader(
            "Documentos bancários",
            type=["pdf", "jpg", "jpeg", "png"],
            accept_multiple_files=True,
            help="Você pode enviar o PDF do Itaú e todas as imagens do Banco do Brasil de uma só vez.",
        )

    if st.button("Ler documentos", type="primary", use_container_width=True):
        if not files:
            st.warning("Selecione pelo menos um arquivo.")
        else:
            with st.spinner("Interpretando os documentos..."):
                rows, errors = process_files(files, position_date)
            st.session_state["read_rows"] = rows
            st.session_state["read_errors"] = errors
            st.session_state["read_date"] = position_date

    rows = st.session_state.get("read_rows", [])
    errors = st.session_state.get("read_errors", [])

    if rows:
        st.subheader("Conferência da leitura")
        df = pd.DataFrame(rows)
        show_cols = ["SELECIONAR", "EMPRESA", "BANCO", "AGENCIA", "CONTA", "SALDO", "STATUS", "ARQUIVO"]
        edited = st.data_editor(
            df[show_cols],
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "SELECIONAR": st.column_config.CheckboxColumn("Salvar", default=True),
                "SALDO": st.column_config.NumberColumn("Saldo identificado", format="R$ %.2f"),
                "EMPRESA": st.column_config.TextColumn("Empresa"),
                "BANCO": st.column_config.TextColumn("Banco", disabled=True),
                "STATUS": st.column_config.TextColumn("Status", disabled=True),
                "ARQUIVO": st.column_config.TextColumn("Arquivo", disabled=True),
            },
            disabled=["BANCO", "STATUS", "ARQUIVO"],
            key="editor_leitura",
        )

        # Reanexa campos técnicos
        save_rows = []
        for i, row in edited.iterrows():
            base = rows[i].copy()
            for c in show_cols:
                base[c] = row[c]
            save_rows.append(base)

        selected_total = sum(float(x["SALDO"]) for x in save_rows if x.get("SELECIONAR", True))
        a, b = st.columns([3, 1])
        a.info(f"Total dos saldos selecionados: **{brl(selected_total)}**")
        if b.button("Confirmar atualização", type="primary", use_container_width=True):
            try:
                new, updated = upsert_balances(save_rows, st.session_state["read_date"])
                st.success(f"Atualização concluída: {new} novo(s) e {updated} atualizado(s).")
                st.session_state.pop("read_rows", None)
                st.session_state.pop("read_errors", None)
            except Exception as e:
                st.error(f"Erro ao gravar no Google Sheets: {e}")

    for err in errors:
        st.warning(err)

def page_dashboard():
    st.markdown("""<div class="hero"><h1>Visão Geral</h1>
    <p>Saldo consolidado, contas e histórico de posições.</p></div>""", unsafe_allow_html=True)

    if not st.session_state.get("dashboard_auth"):
        with st.form("login"):
            st.subheader("Acesso protegido")
            pwd = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", type="primary", use_container_width=True)
            if submitted:
                if pwd == PAINEL_PASSWORD:
                    st.session_state["dashboard_auth"] = True
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
        return

    top1, top2 = st.columns([5, 1])
    with top2:
        if st.button("Sair do painel", use_container_width=True):
            st.session_state["dashboard_auth"] = False
            st.rerun()
    render_dashboard()

def page_accounts():
    st.markdown("""<div class="hero"><h1>Contas</h1>
    <p>Cadastro utilizado para reconhecer automaticamente empresa, banco, agência e conta.</p></div>""", unsafe_allow_html=True)
    df = load_accounts()
    st.success(f"{len(df)} contas cadastradas.")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("As 18 contas iniciais são criadas automaticamente. Para alterações estruturais, edite a aba CONTAS no Google Sheets.")

# =========================================================
# INICIALIZAÇÃO
# =========================================================
try:
    prepare_database()
except Exception as e:
    st.error("Não foi possível conectar ao Google Sheets.")
    st.code(str(e))
    st.info(
        "Configure a conta de serviço em .streamlit/secrets.toml e compartilhe a planilha "
        "com o e-mail client_email dessa conta como Editor."
    )
    st.stop()

with st.sidebar:
    st.markdown("## 💰 Saldo de Contas")
    st.caption("Grupo Dauto")
    st.divider()
    page = st.radio(
        "Navegação",
        ["Atualizar Saldos", "Visão Geral", "Contas"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("PDF Itaú: leitura direta quando houver texto.")
    st.caption("BB: OCR local no Python, sem Google Drive OCR.")

if page == "Atualizar Saldos":
    page_update()
elif page == "Visão Geral":
    page_dashboard()
else:
    page_accounts()
