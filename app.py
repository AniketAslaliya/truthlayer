"""TruthLayer - upload a PDF, get every factual claim checked against live data."""
from __future__ import annotations

import io
import json
from html import escape

import streamlit as st

st.set_page_config(page_title="TruthLayer - automated fact-check", page_icon="TL", layout="wide")

import os
_secret_files = [
    os.path.expanduser("~/.streamlit/secrets.toml"),
    os.path.join(os.getcwd(), ".streamlit", "secrets.toml"),
]
if any(os.path.exists(_f) for _f in _secret_files):
    try:
        for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            if _k in st.secrets and not os.environ.get(_k):
                os.environ[_k] = st.secrets[_k]
    except Exception:  # unreadable secrets file
        pass
if False:
    pass
from pypdf import PdfReader

from truthlayer.extract import find_claims
from truthlayer.verify import verify_all, VERIFIED, INACCURATE, FALSE
from truthlayer.report import summarise, rows, to_csv

st.markdown("""
<style>
.block-container {padding-top: 2.2rem; max-width: 1100px;}
.badge {display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px;
        font-weight:600; letter-spacing:.02em;}
.v {background:#e6f4ea; color:#137333;}
.i {background:#fef7e0; color:#b06000;}
.f {background:#fce8e6; color:#c5221f;}
.claim {font-size:15px; line-height:1.5; margin:0 0 6px 0;}
.real {font-size:14px; color:#3c4043;}
.src {font-size:12px; color:#5f6368;}
</style>
""", unsafe_allow_html=True)

st.title("TruthLayer")
st.caption("Upload a document. Every stat, date and figure in it is checked against live public data "
           "and flagged Verified, Inaccurate or False - with the real number.")

with st.sidebar:
    st.subheader("How it works")
    st.write("1. Claims are extracted from the PDF text.")
    st.write("2. Each claim is matched to a live source: World Bank, Wikipedia, Wikidata.")
    st.write("3. The claimed value is compared with the live one.")
    st.write("No API keys, no credits to run out.")
    max_claims = st.slider("Max claims to check", 5, 40, 20)

uploaded = st.file_uploader("Upload a PDF", type=["pdf"])

sample = None
try:
    with open("sample/trap_sample.pdf", "rb") as fh:
        sample = fh.read()
except OSError:
    sample = None

use_sample = st.button("Try the sample trap document") if sample else False

data = None
if uploaded is not None:
    data = uploaded.read()
elif use_sample:
    data = sample

if data:
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    with st.spinner("Reading and checking claims against live data..."):
        claims = find_claims(text, max_claims=max_claims)
        verdicts = verify_all(claims)
    if not claims:
        st.warning("No checkable claims found in this document.")
    else:
        s = summarise(verdicts)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Claims checked", len(claims))
        c2.metric("Verified", s[VERIFIED])
        c3.metric("Inaccurate", s[INACCURATE])
        c4.metric("False", s[FALSE])

        st.divider()
        for r in rows(claims, verdicts):
            cls = {VERIFIED: "v", INACCURATE: "i", FALSE: "f"}.get(r["verdict"], "i")
            st.markdown('<p class="claim">%s</p>' % escape(str(r["claim"])), unsafe_allow_html=True)
            st.markdown('<span class="badge %s">%s</span>' % (cls, r["verdict"]), unsafe_allow_html=True)
            if r["real_value"] is not None:
                st.markdown('<p class="real">Real: %s%s - %s</p>' % (
                    "{:,.2f}".format(r["real_value"]).rstrip("0").rstrip("."),
                    " (%s)" % r["real_year"] if r["real_year"] else "", escape(str(r["note"]))),
                    unsafe_allow_html=True)
            else:
                st.markdown('<p class="real">%s</p>' % escape(str(r["note"])), unsafe_allow_html=True)
            if r["source_url"]:
                st.markdown('<p class="src">Source: <a href="%s" target="_blank">%s</a></p>'
                            % (r["source_url"], r["source"]), unsafe_allow_html=True)
            st.divider()

        st.download_button("Download the report (CSV)", to_csv(claims, verdicts),
                           file_name="truthlayer_report.csv", mime="text/csv")
else:
    st.info("Upload a PDF to start. The sample document has deliberate errors in it.")
