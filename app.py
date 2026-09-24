from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


SPREADSHEET_ID = "1jocHQg3sbv_v8KpPNK8Y4KWrSEmZW-Eee8k_ugLFnaI"
CONTAS_HEADERS = ["EMPRESA", "BANCO", "AGENCIA", "CONTA", "APELIDO", "ATIVA", "ORDEM"]
SALDOS_HEADERS = [
    "ID", "DATA", "EMPRESA", "BANCO", "AGENCIA", "CONTA", "SALDO",
    "ARQUIVO", "ORIGEM", "CONFIANCA", "DATA_HORA",
]

CONTAS_INICIAIS = [
    ("DT TINTAS COMÉRCIO VAREJISTA", "Banco do Brasil", "1231-9", "62.810-7", "DT TINTAS BB", True, 1),
    ("ÉTICA", "Banco do Brasil", "1231-9", "62.686-4", "ÉTICA BB", True, 2),
    ("MERCADO", "Banco do Brasil", "1231-9", "33.300-X", "MERCADO BB", True, 3),
    ("V&T", "Banco do Brasil", "1231-9", "62.619-8", "V&T BB", True, 4),
    ("ÚNICA", "Banco do Brasil", "1231-9", "62.608-2", "ÚNICA BB", True, 5),
    ("ÚNICA ATACADISTA TINTAS LTDA", "Itaú", "654", "73733-7", "ÚNICA ITAÚ", True, 6),
    ("DT TINTAS COMÉRCIO VAREJISTA", "Itaú", "654", "98240-4", "DT ITAÚ 98240-4", True, 7),
    ("DAUTO TINTAS SERVIÇOS E PRODUTOS", "Itaú", "654", "98530-8", "DAUTO ITAÚ 98530-8", True, 8),
    ("DT TINTAS COMÉRCIO VAREJISTA", "Itaú", "654", "99190-0", "DT ITAÚ 99190-0", True, 9),
    ("DT TINTAS COMÉRCIO VAREJISTA", "Itaú", "654", "99191-8", "DT ITAÚ 99191-8", True, 10),
    ("ÉTICA COMÉRCIO VAREJISTA DE TINTAS", "Itaú", "654", "99195-9", "ÉTICA ITAÚ 99195-9", True, 11),
    ("ÉTICA COMÉRCIO VAREJISTA DE TINTAS", "Itaú", "654", "99200-7", "ÉTICA ITAÚ 99200-7", True, 12),
    ("VET COMÉRCIO VAREJISTA DE TINTAS", "Itaú", "654", "99201-5", "V&T ITAÚ 99201-5", True, 13),
    ("VET COMÉRCIO VAREJISTA DE TINTAS", "Itaú", "654", "99202-3", "V&T ITAÚ 99202-3", True, 14),
    ("MERCADO DAS TINTAS EIRELI", "Itaú", "654", "99203-1", "MERCADO ITAÚ 99203-1", True, 15),
    ("MERCADO DAS TINTAS LTDA", "Itaú", "654", "99204-9", "MERCADO ITAÚ 99204-9", True, 16),
    ("DAUTO TINTAS LTDA", "Itaú", "654", "99205-6", "DAUTO ITAÚ 99205-6", True, 17),
    ("DT TINTAS COMÉRCIO VAREJISTA", "Itaú", "1890", "99348-6", "DT ITAÚ 99348-6", True, 18),
]


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root { --navy:#102a43; --blue:#1769aa; --ink:#243b53; --muted:#627d98; --line:#d9e2ec; }
        .stApp { background:#f4f7fa; color:var(--ink); }
        [data-testid="stSidebar"] { background:var(--navy); }
        [data-testid="stSidebar"] * { color:#fff; }
        [data-testid="stSidebar"] .stRadio label { padding:.34rem .15rem; }
        .hero { background:linear-gradient(125deg,#102a43,#1769aa); color:#fff; padding:1.5rem 1.7rem;
                border-radius:16px; margin:0 0 1rem; box-shadow:0 8px 24px rgba(16,42,67,.14); }
        .hero h1 { margin:0; font-size:1.65rem; color:#fff; }
        .hero p { margin:.35rem 0 0; opacity:.85; }
        .metric-card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:1rem 1.1rem;
                       min-height:112px; box-shadow:0 3px 12px rgba(16,42,67,.06); }
        .metric-card .label { color:var(--muted); font-size:.82rem; text-transform:uppercase; letter-spacing:.04em; }
        .metric-card .value { color:var(--navy); font-size:1.45rem; font-weight:700; margin-top:.45rem; }
        .status-ok { color:#16794a; font-weight:600; }
        .status-warn { color:#ad6800; font-weight:600; }
        div[data-testid="stMetric"] { background:#fff; border:1px solid var(--line); padding:1rem; border-radius:14px; }
        .block-container { max-width:1280px; padding-top:1.3rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def brl(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if number < 0 else ""
    raw = f"{abs(number):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{sign}R$ {raw}"


def br_number(value: Any) -> str:
    """Brazilian editable number without currency symbol."""
    if value is None or pd.isna(value):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    sign = "-" if number < 0 else ""
    raw = f"{abs(number):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return sign + raw


def parse_brl(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    text = str(value).strip().upper().replace("R$", "").replace(" ", "")
    if not text:
        return None
    negative = text.endswith("-") or (text.startswith("(") and text.endswith(")"))
    text = text.strip("()-")
    text = re.sub(r"[^0-9,.-]", "", text)
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        result = float(Decimal(text))
        return -result if negative else result
    except (InvalidOperation, ValueError):
        return None


def key_part(value: Any) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(value).upper())


def plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch)).upper()


def account_group(alias: str, bank: str) -> str:
    a = plain(alias)
    if plain(bank).startswith("BANCO DO BRASIL"):
        return re.sub(r"\s+", " ", re.sub(r"\s+BB$", " BB", alias)).strip()
    for prefix, label in [("DT ", "DT ITAÚ"), ("DAUTO ", "DAUTO ITAÚ"), ("ETICA ", "ÉTICA ITAÚ"),
                          ("UNICA ", "ÚNICA ITAÚ"), ("MERCADO ", "MERCADO ITAÚ"), ("V&T ", "V&T ITAÚ")]:
        if a.startswith(prefix):
            return label
    return alias


def company_group(alias: str, company: str) -> str:
    """Stable business label used to consolidate multiple accounts at the same bank."""
    source = plain(alias or company)
    mappings = [
        ("DT ", "DT TINTAS"),
        ("DAUTO ", "DAUTO"),
        ("ETICA ", "ÉTICA"),
        ("UNICA ", "ÚNICA"),
        ("MERCADO ", "MERCADO"),
        ("V&T ", "V&T"),
        ("VET ", "V&T"),
    ]
    for prefix, label in mappings:
        if source.startswith(prefix):
            return label
    return company or alias


def bank_group(bank: str) -> str:
    return "Banco do Brasil" if "BRASIL" in plain(bank) else "Itaú" if "ITAU" in plain(bank) else bank


@st.cache_resource(show_spinner=False)
def sheets_client():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise RuntimeError("Dependências do Google Sheets não instaladas.") from exc

    secrets = None
    try:
        for name in ("google_service_account", "gcp_service_account"):
            if name in st.secrets:
                secrets = dict(st.secrets[name])
                break
    except Exception:
        secrets = None
    if not secrets:
        raise RuntimeError(
            "Credencial do Google não configurada. Adicione a seção [google_service_account] "
            "aos Secrets do Streamlit e compartilhe a planilha com o e-mail client_email."
        )
    required = {"type", "project_id", "private_key", "client_email", "token_uri"}
    missing = sorted(required - set(secrets))
    if missing:
        raise RuntimeError("Credencial incompleta. Campos ausentes: " + ", ".join(missing))
    credentials = Credentials.from_service_account_info(
        secrets,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(credentials)


def get_book():
    return sheets_client().open_by_key(SPREADSHEET_ID)


def ensure_worksheet(book, title: str, headers: list[str], rows: int = 1000):
    import gspread
    try:
        ws = book.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(title=title, rows=rows, cols=max(12, len(headers)))
    values = ws.get_all_values()
    if not values:
        ws.append_row(headers, value_input_option="RAW")
    elif values[0] != headers:
        ws.update(range_name=f"A1:{chr(64 + len(headers))}1", values=[headers])
    return ws


def ensure_database():
    book = get_book()
    contas_ws = ensure_worksheet(book, "CONTAS", CONTAS_HEADERS, 100)
    saldos_ws = ensure_worksheet(book, "SALDOS", SALDOS_HEADERS, 5000)
    existing = contas_ws.get_all_records()
    existing_keys = {
        (key_part(row.get("BANCO")), key_part(row.get("AGENCIA")), key_part(row.get("CONTA")))
        for row in existing
    }
    new_rows = [list(row) for row in CONTAS_INICIAIS if (key_part(row[1]), key_part(row[2]), key_part(row[3])) not in existing_keys]
    if new_rows:
        contas_ws.append_rows(new_rows, value_input_option="USER_ENTERED")
    return contas_ws, saldos_ws


@st.cache_data(ttl=60, show_spinner=False)
def load_database(_refresh: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    contas_ws, saldos_ws = ensure_database()
    contas = pd.DataFrame(contas_ws.get_all_records(), columns=CONTAS_HEADERS)
    saldos = pd.DataFrame(saldos_ws.get_all_records(), columns=SALDOS_HEADERS)
    if not saldos.empty:
        saldos["SALDO"] = saldos["SALDO"].map(parse_brl)
        saldos["DATA_DT"] = pd.to_datetime(saldos["DATA"], dayfirst=True, errors="coerce")
    return contas, saldos


def local_accounts() -> pd.DataFrame:
    return pd.DataFrame(CONTAS_INICIAIS, columns=CONTAS_HEADERS)


def get_accounts() -> pd.DataFrame:
    try:
        contas, _ = load_database(st.session_state.get("db_refresh", 0))
        return contas if not contas.empty else local_accounts()
    except Exception:
        return local_accounts()


def preprocess_image(raw: bytes | Image.Image) -> Image.Image:
    image = raw.copy() if isinstance(raw, Image.Image) else Image.open(io.BytesIO(raw))
    image = ImageOps.exif_transpose(image).convert("L")
    if image.width < 1800:
        scale = 1800 / image.width
        image = image.resize((1800, int(image.height * scale)), Image.Resampling.LANCZOS)
    image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(1.35)
    return image.filter(ImageFilter.SHARPEN)


def preprocess_crop(image: Image.Image, box: tuple[int, int, int, int], invert: bool = False) -> Image.Image:
    """Prepare a small screen region without losing the tiny header characters."""
    crop = ImageOps.exif_transpose(image).convert("L").crop(box)
    scale = max(3.0, 2200 / max(crop.width, 1))
    crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.Resampling.LANCZOS)
    crop = ImageOps.autocontrast(crop, cutoff=1)
    crop = ImageEnhance.Contrast(crop).enhance(1.7)
    if invert:
        crop = ImageOps.invert(crop)
    return crop.filter(ImageFilter.SHARPEN)


def ocr_image(image: Image.Image, psm: int = 6, whitelist: str | None = None) -> str:
    try:
        import pytesseract
        config = f"--oem 3 --psm {psm}"
        if whitelist:
            config += f" -c tessedit_char_whitelist={whitelist}"
        try:
            return pytesseract.image_to_string(image, lang="por+eng", config=config)
        except pytesseract.TesseractError:
            return pytesseract.image_to_string(image, lang="eng", config=config)
    except Exception as exc:
        raise RuntimeError(
            "OCR indisponível. Confirme que tesseract-ocr e tesseract-ocr-por estão no packages.txt."
        ) from exc


def known_match(found: str, accounts: pd.DataFrame, bank: str) -> dict[str, Any] | None:
    target = key_part(found)
    subset = accounts[accounts["BANCO"].map(plain).str.contains(plain(bank), regex=False)]
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for row in subset.to_dict("records"):
        candidate = key_part(row["CONTA"])
        score = SequenceMatcher(None, target, candidate).ratio()
        if target == candidate:
            score = 1.0
        if score > best[0]:
            best = (score, row)
    return best[1] if best[0] >= 0.68 else None


MONEY_PATTERN = r"(?:R\$\s*)?[-(]?\d{1,3}(?:\.\d{3})*,\d{2}[)-]?"


def match_bb_account(texts: list[str], accounts: pd.DataFrame) -> tuple[dict[str, Any] | None, bool]:
    """Match the header against the five known accounts, tolerating OCR substitutions."""
    subset = accounts[accounts["BANCO"].map(plain).str.contains("BANCO DO BRASIL", regex=False)]
    rows = subset.to_dict("records")
    translation = str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})

    compact_texts = [key_part(plain(text)).translate(translation) for text in texts if text]
    for compact in compact_texts:
        for row in rows:
            expected = key_part(row["CONTA"]).translate(translation)
            if expected in compact:
                return row, True

    best_score = 0.0
    best_row = None
    for compact in compact_texts:
        for row in rows:
            expected = key_part(row["CONTA"]).translate(translation)
            size = len(expected)
            for width in (size - 1, size, size + 1):
                if width < 4:
                    continue
                for start in range(max(1, len(compact) - width + 1)):
                    score = SequenceMatcher(None, compact[start:start + width], expected).ratio()
                    if score > best_score:
                        best_score, best_row = score, row
    return (best_row, False) if best_score >= 0.80 else (None, False)


def final_bb_balance(texts: list[str]) -> float | None:
    # First choice: the final line explicitly labelled "Saldo".
    labelled: list[float] = []
    for text in texts:
        for line in text.splitlines():
            line_plain = plain(line).strip()
            if re.match(r"^SALD[O0]\b", line_plain) and "999" not in line_plain:
                values = re.findall(MONEY_PATTERN, line, flags=re.I)
                if values:
                    value = parse_brl(values[-1])
                    if value is not None:
                        labelled.append(value)
    if labelled:
        return labelled[-1]

    # In these BB screenshots the final balance is the last monetary value in the footer.
    # This fallback only receives footer OCR, so it cannot pick a transaction from the top.
    for text in texts:
        values = re.findall(MONEY_PATTERN, text, flags=re.I)
        if values:
            value = parse_brl(values[-1])
            if value is not None:
                return value
    return None


def extract_bb(raw: bytes, filename: str, accounts: pd.DataFrame) -> list[dict[str, Any]]:
    original = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    width, height = original.size

    # The account is in the blue header. Upscaling and inverting that region gives
    # Tesseract dark characters on a light background instead of a complex full screen.
    header_box = (int(width * 0.50), 0, width, min(height, max(80, int(height * 0.23))))
    header = preprocess_crop(original, header_box, invert=True)
    header_texts = [ocr_image(header, psm=6), ocr_image(header, psm=11)]
    account, exact = match_bb_account(header_texts, accounts)

    full_text = ""
    if not account:
        full_text = ocr_image(preprocess_image(original), psm=11)
        account, exact = match_bb_account(header_texts + [full_text], accounts)
    if not account:
        return [result_row(filename=filename, bank="Banco do Brasil", status="Conta não identificada", confidence="Baixa")]

    # Read only the lower part for the final balance. Two layout modes handle both
    # the aligned table and sparse footer text used by the Banco do Brasil page.
    footer_box = (0, int(height * 0.52), width, height)
    footer = preprocess_crop(original, footer_box)
    footer_texts = [ocr_image(footer, psm=6), ocr_image(footer, psm=11)]
    saldo = final_bb_balance(footer_texts)
    if saldo is None:
        if not full_text:
            full_text = ocr_image(preprocess_image(original), psm=6)
        saldo = final_bb_balance([full_text])
    if saldo is None:
        return [result_row(account, filename, "Banco do Brasil", status="Saldo não localizado", confidence="Média")]
    return [result_row(account, filename, "Banco do Brasil", saldo, "Leitura concluída", "Alta" if exact else "Média")]


def extract_pdf_text(raw: bytes) -> tuple[str, str]:
    try:
        import fitz
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:
        raise RuntimeError("Arquivo PDF inválido ou corrompido.") from exc
    direct = "\n".join(page.get_text("text") for page in doc)
    if len(re.sub(r"\s", "", direct)) >= 100:
        return direct, "Texto do PDF"
    pages = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2.4, 2.4), alpha=False)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        pages.append(ocr_image(preprocess_image(image), psm=6))
    return "\n".join(pages), "OCR do PDF"


def tolerant_account_pattern(account: str) -> str:
    chars = [re.escape(ch) for ch in key_part(account)]
    return r"[.\s\-/]*".join(chars)


def find_target_balance(block: str) -> float | None:
    lines = block.splitlines()
    for line in lines:
        normalized = plain(line)
        has_target = ("SDO" in normalized and "DISP" in normalized and "APLIC" in normalized and "HOJE" in normalized)
        if has_target:
            values = re.findall(MONEY_PATTERN, line, flags=re.I)
            if values:
                return parse_brl(values[-1])
    # OCR sometimes breaks the label and amount across two lines.
    compact = re.sub(r"\s+", " ", plain(block))
    match = re.search(r"SD[O0].{0,12}DISP.{0,12}APLIC.{0,12}HOJE.{0,20}?(" + MONEY_PATTERN + r")", compact)
    return parse_brl(match.group(1)) if match else None


def extract_itau(raw: bytes, filename: str, accounts: pd.DataFrame) -> list[dict[str, Any]]:
    text, origin = extract_pdf_text(raw)
    subset = accounts[accounts["BANCO"].map(plain).str.contains("ITAU", regex=False)].copy()
    positions: list[tuple[int, dict[str, Any]]] = []
    for account in subset.to_dict("records"):
        match = re.search(tolerant_account_pattern(str(account["CONTA"])), plain(text))
        if match:
            positions.append((match.start(), account))
    positions.sort(key=lambda item: item[0])
    if not positions:
        return [result_row(filename=filename, bank="Itaú", status="Conta não identificada", confidence="Baixa", origin=origin)]

    rows = []
    for idx, (start, account) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(text)
        block = text[start:end]
        saldo = find_target_balance(block)
        if saldo is None:
            rows.append(result_row(account, filename, "Itaú", status="Saldo não localizado", confidence="Média", origin=origin))
        else:
            rows.append(result_row(account, filename, "Itaú", saldo, "Leitura concluída", "Alta", origin))
    return rows


def result_row(
    account: dict[str, Any] | None = None,
    filename: str = "",
    bank: str = "",
    balance: float | None = None,
    status: str = "Arquivo inválido",
    confidence: str = "Baixa",
    origin: str = "OCR",
) -> dict[str, Any]:
    account = account or {}
    return {
        "Salvar": balance is not None,
        "Empresa": account.get("EMPRESA", ""),
        "Banco": bank or account.get("BANCO", ""),
        "Agência": str(account.get("AGENCIA", "")),
        "Conta": str(account.get("CONTA", "")),
        "Saldo identificado": balance,
        "Status": status,
        "Arquivo": filename,
        "Confiança": confidence,
        "Origem": origin,
    }


def process_file(uploaded, accounts: pd.DataFrame) -> list[dict[str, Any]]:
    raw = uploaded.getvalue()
    name = uploaded.name
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    try:
        if ext == "pdf":
            return extract_itau(raw, name, accounts)
        if ext in {"png", "jpg", "jpeg", "webp", "tif", "tiff"}:
            return extract_bb(raw, name, accounts)
        return [result_row(filename=name, status="Arquivo inválido")]
    except Exception as exc:
        return [result_row(filename=name, status=f"Não foi possível identificar o saldo deste arquivo. ({exc})")]


def save_balances(rows: pd.DataFrame, position_date: date) -> tuple[int, int]:
    _, ws = ensure_database()
    values = ws.get_all_values()
    date_text = position_date.strftime("%d/%m/%Y")
    index: dict[tuple[str, str, str], int] = {}
    for sheet_row, row in enumerate(values[1:], start=2):
        padded = row + [""] * (len(SALDOS_HEADERS) - len(row))
        record = dict(zip(SALDOS_HEADERS, padded))
        index[(record["DATA"], key_part(record["BANCO"]), key_part(record["CONTA"]))] = sheet_row

    inserted = updated = 0
    for _, row in rows.iterrows():
        balance = parse_brl(row["Saldo identificado"])
        if not bool(row["Salvar"]) or balance is None or not str(row["Conta"]).strip():
            continue
        key = (date_text, key_part(row["Banco"]), key_part(row["Conta"]))
        stable_id = hashlib.sha1("|".join(key).encode("utf-8")).hexdigest()[:16]
        payload = [
            stable_id, date_text, row["Empresa"], row["Banco"], row["Agência"], row["Conta"],
            balance, row["Arquivo"], row.get("Origem", "OCR"), row.get("Confiança", ""),
            datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        ]
        if key in index:
            sheet_row = index[key]
            # RAW preserves the JSON numeric value. USER_ENTERED can interpret the decimal
            # point as a thousands separator when the spreadsheet locale is pt-BR.
            ws.update(range_name=f"A{sheet_row}:K{sheet_row}", values=[payload], value_input_option="RAW")
            updated += 1
        else:
            ws.append_row(payload, value_input_option="RAW")
            inserted += 1
    st.session_state["db_refresh"] = st.session_state.get("db_refresh", 0) + 1
    load_database.clear()
    return inserted, updated


def page_update() -> None:
    hero("Atualizar saldos", "Envie os documentos do dia, confira os valores e confirme a atualização.")
    left, right = st.columns([1, 2])
    with left:
        position_date = st.date_input("Data da posição", value=date.today(), format="DD/MM/YYYY")
    with right:
        uploads = st.file_uploader(
            "PDF do Itaú e imagens do Banco do Brasil",
            type=["pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff"],
            accept_multiple_files=True,
        )
    if st.button("Ler documentos", type="primary", disabled=not uploads, use_container_width=True):
        accounts = get_accounts()
        progress = st.progress(0, text="Preparando leitura…")
        results: list[dict[str, Any]] = []
        for idx, uploaded in enumerate(uploads):
            progress.progress(idx / len(uploads), text=f"Lendo {uploaded.name}")
            results.extend(process_file(uploaded, accounts))
        progress.progress(1.0, text="Leitura concluída")
        st.session_state["review_rows"] = results
        st.session_state["position_date"] = position_date

    if "review_rows" not in st.session_state:
        st.info("Selecione os arquivos e clique em **Ler documentos**.")
        return

    st.subheader("Conferência")
    review = pd.DataFrame(st.session_state["review_rows"])
    display_columns = ["Salvar", "Empresa", "Banco", "Agência", "Conta", "Saldo identificado", "Status", "Arquivo"]
    review_display = review[display_columns].copy()
    review_display["Saldo identificado"] = review_display["Saldo identificado"].map(br_number)
    edited = st.data_editor(
        review_display,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        disabled=["Empresa", "Banco", "Agência", "Conta", "Status", "Arquivo"],
        column_config={
            "Salvar": st.column_config.CheckboxColumn(default=False),
            "Saldo identificado": st.column_config.TextColumn(
                "Saldo identificado",
                help="Use o formato brasileiro, por exemplo: 106.531,91",
            ),
        },
        key="review_editor",
    )
    total = edited.loc[edited["Salvar"], "Saldo identificado"].map(parse_brl).dropna().sum()
    st.metric("Total dos saldos selecionados", brl(total))
    if st.button("Confirmar atualização", type="primary", use_container_width=True):
        selected = edited[edited["Salvar"]].copy()
        invalid = selected["Saldo identificado"].map(parse_brl).isna() | selected["Conta"].astype(str).str.strip().eq("")
        if selected.empty:
            st.warning("Selecione ao menos uma linha para salvar.")
        elif invalid.any():
            st.error("Preencha conta e saldo em todas as linhas selecionadas.")
        else:
            for extra in ("Confiança", "Origem"):
                edited[extra] = review[extra].values
            try:
                with st.spinner("Atualizando Google Sheets…"):
                    inserted, updated = save_balances(edited, st.session_state.get("position_date", position_date))
                st.success(f"Atualização concluída: {inserted} novo(s) registro(s) e {updated} atualizado(s).")
            except Exception as exc:
                st.error(str(exc))


def password_gate() -> bool:
    if st.session_state.get("dashboard_unlocked"):
        return True
    st.subheader("Acesso protegido")
    with st.form("password_form"):
        password = st.text_input("Senha", type="password")
        sent = st.form_submit_button("Entrar", type="primary")
    try:
        expected = st.secrets.get("dashboard_password", "Dauto@10.10")
    except Exception:
        expected = "Dauto@10.10"
    if sent:
        if password == expected:
            st.session_state["dashboard_unlocked"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    return False


def page_dashboard() -> None:
    hero("Visão geral", "Saldos consolidados, composição por conta e evolução diária do grupo.")
    if not password_gate():
        return
    try:
        contas, saldos = load_database(st.session_state.get("db_refresh", 0))
    except Exception as exc:
        st.error(str(exc))
        return
    if saldos.empty or saldos["DATA_DT"].dropna().empty:
        st.info("Ainda não há saldos gravados para exibir.")
        return
    available = sorted(saldos["DATA_DT"].dropna().dt.date.unique(), reverse=True)
    selected_date = st.selectbox("Data da posição", available, format_func=lambda d: d.strftime("%d/%m/%Y"))
    day = saldos[saldos["DATA_DT"].dt.date == selected_date].copy()
    aliases = contas[["BANCO", "CONTA", "APELIDO", "ORDEM"]].copy()
    aliases["K"] = aliases["BANCO"].map(key_part) + "|" + aliases["CONTA"].map(key_part)
    day["K"] = day["BANCO"].map(key_part) + "|" + day["CONTA"].map(key_part)
    day = day.merge(aliases[["K", "APELIDO", "ORDEM"]], on="K", how="left")
    day["APELIDO"] = day["APELIDO"].fillna(day["CONTA"])
    day["EMPRESA_GRUPO"] = day.apply(
        lambda r: company_group(str(r["APELIDO"]), str(r["EMPRESA"])), axis=1
    )
    day["BANCO_GRUPO"] = day["BANCO"].map(bank_group)
    st.metric("Saldo consolidado", brl(day["SALDO"].sum()))

    grouped = (
        day.groupby(["EMPRESA_GRUPO", "BANCO_GRUPO"], as_index=False)
        .agg(
            CONTAS=("CONTA", lambda values: " • ".join(sorted({str(value) for value in values}))),
            SALDO=("SALDO", "sum"),
        )
        .sort_values(["EMPRESA_GRUPO", "BANCO_GRUPO"])
    )
    cols = st.columns(3)
    for idx, row in grouped.reset_index(drop=True).iterrows():
        with cols[idx % 3]:
            st.markdown(
                f'<div class="metric-card"><div class="label">{row["EMPRESA_GRUPO"]} • {row["BANCO_GRUPO"]}</div>'
                f'<div class="value">{brl(row["SALDO"])}</div></div>',
                unsafe_allow_html=True,
            )

    st.subheader("Saldos por empresa e banco")
    consolidated = grouped.rename(
        columns={
            "EMPRESA_GRUPO": "Empresa",
            "BANCO_GRUPO": "Banco",
            "CONTAS": "Contas",
            "SALDO": "Saldo consolidado",
        }
    )
    st.dataframe(
        consolidated,
        hide_index=True,
        use_container_width=True,
        column_config={"Saldo consolidado": st.column_config.NumberColumn(format="R$ %.2f")},
    )

    with st.expander("Ver contas individuais"):
        detail = day[["EMPRESA", "BANCO", "AGENCIA", "CONTA", "APELIDO", "SALDO"]].copy()
        detail.columns = ["Empresa", "Banco", "Agência", "Conta", "Apelido", "Saldo"]
        detail = detail.sort_values(["Empresa", "Banco", "Conta"])
        st.dataframe(
            detail,
            hide_index=True,
            use_container_width=True,
            column_config={"Saldo": st.column_config.NumberColumn(format="R$ %.2f")},
        )

    st.subheader("Histórico")
    history = saldos.dropna(subset=["DATA_DT", "SALDO"]).copy()
    daily = history.groupby("DATA_DT", as_index=False)["SALDO"].sum().sort_values("DATA_DT")
    fig = px.line(daily, x="DATA_DT", y="SALDO", markers=True, labels={"DATA_DT": "Data", "SALDO": "Saldo consolidado"})
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), plot_bgcolor="white", paper_bgcolor="white", yaxis_tickprefix="R$ ")
    st.plotly_chart(fig, use_container_width=True)

    options = ["Todas as contas"] + sorted(history["EMPRESA"].dropna().astype(str).unique().tolist())
    company = st.selectbox("Histórico por empresa", options)
    filtered = history if company == "Todas as contas" else history[history["EMPRESA"] == company]
    pivot = filtered.pivot_table(index="DATA_DT", columns="CONTA", values="SALDO", aggfunc="sum").sort_index()
    pivot["TOTAL"] = pivot.sum(axis=1)
    pivot.index = pivot.index.strftime("%d/%m/%Y")
    st.dataframe(pivot.style.format(lambda x: brl(x)), use_container_width=True)


def page_accounts() -> None:
    hero("Contas", "Cadastro usado para reconhecer os documentos e organizar o dashboard.")
    try:
        contas, _ = load_database(st.session_state.get("db_refresh", 0))
        st.dataframe(contas.sort_values("ORDEM"), hide_index=True, use_container_width=True)
        st.caption("O cadastro inicial é criado automaticamente sem duplicar BANCO + AGÊNCIA + CONTA.")
    except Exception as exc:
        st.warning(str(exc))
        st.dataframe(local_accounts(), hide_index=True, use_container_width=True)
        st.caption("Exibindo o cadastro padrão local enquanto o Google Sheets não está disponível.")


def main() -> None:
    st.set_page_config(page_title="Saldos Bancários", page_icon="🏦", layout="wide")
    inject_css()
    with st.sidebar:
        st.markdown("## Dauto Financeiro")
        st.caption("Controle diário de saldos")
        page = st.radio("Navegação", ["Atualizar Saldos", "Visão Geral", "Contas"], label_visibility="collapsed")
        st.divider()
        st.caption("Dados armazenados no Google Sheets")
    if page == "Atualizar Saldos":
        page_update()
    elif page == "Visão Geral":
        page_dashboard()
    else:
        page_accounts()


if __name__ == "__main__":
    main()
