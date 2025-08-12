from flask import Flask, render_template, request, send_from_directory, redirect, url_for, session, abort
from openpyxl import Workbook, load_workbook
from datetime import datetime, timedelta
import os
import uuid
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import matplotlib.patches as patches
from flask_mail import Mail, Message
import requests
from flask_session import Session
import re
from io import BytesIO
from flask import send_file, abort, current_app



# ================== UYGULAMA & OTURUM ==================
app = Flask(__name__)
app.secret_key = 'gizli_anahtar'
app.permanent_session_lifetime = timedelta(minutes=10)
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# ================== MAİL ==================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'winJohariTest@gmail.com'
app.config['MAIL_PASSWORD'] = 'pebxhabcyhcucsmy'
app.config['MAIL_DEFAULT_SENDER'] = 'winJohariTest@gmail.com'
mail = Mail(app)

# ================== DİZİNLER & AYARLAR ==================
BASE_DIR = os.getcwd()
STATIC_DIR = os.path.join(BASE_DIR, "static")
GRAFIK_DIR = os.path.join(STATIC_DIR, "grafik")
DATA_DIR = os.path.join(BASE_DIR, "data")  # gizli tutulacak
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(GRAFIK_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

EXCEL_YOLU = os.path.join(DATA_DIR, "sonuclar.xlsx")  # artık static'te değil!
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")  # basit indirme koruması

# Güvenli dosya adı
def slugify(txt):
    txt = re.sub(r"[^\w\s-]", "", str(txt), flags=re.UNICODE).strip()
    txt = re.sub(r"[\s-]+", "_", txt)
    return txt[:40] if txt else "kisi"


def _harfe_cevir(v):
    if v is None:
        return None
    s = str(v).strip().upper()
    if s in ("A","B","C","D"):
        return s
    if s in ("1","2","3","4"):
        return {"1":"A","2":"B","3":"C","4":"D"}[s]
    return None  # tanınmayan değer
from openpyxl import load_workbook
from io import BytesIO
from flask import send_file, abort, current_app, flash

def _exceli_oku_ve_hesapla(file_storage):
    """
    Beklenen başlıklar: Yapan, Test Edilen, S1 .. S48
    Cevaplar A/B/C/D ya da 1/2/3/4 olabilir.
    Dönüş: (sonuclar_listesi, hatalar_listesi)
    """
    wb = load_workbook(filename=file_storage, data_only=True)
    ws = wb.active

    # Başlık satırı
    headers = [ (c.value or "").strip() if isinstance(c.value,str) else c.value for c in ws[1] ]
    # Esnek: Türkçe büyük/küçük harf farkını yumuşat
    h_lower = [ (h or "").lower() for h in headers ]

    def _idx(name):
        name_l = name.lower()
        if name_l in h_lower:
            return h_lower.index(name_l)
        return None

    yapan_idx = _idx("yapan")
    edilen_idx = _idx("test edilen")
    # S1..S48 sütunları
    s_idx = []
    for i in range(1,49):
        key = f"s{i}"
        j = _idx(key)
        if j is None:
            # Büyük harfe duyarsız ara: S1 / s1
            try:
                j = [x.lower() for x in headers].index(key)
            except ValueError:
                j = None
        s_idx.append(j)

    hatalar = []
    sonuclar = []
    if yapan_idx is None or edilen_idx is None or any(j is None for j in s_idx):
        hatalar.append("Başlıklar eksik. 'Yapan', 'Test Edilen', 'S1'..'S48' olmalı.")
        return [], hatalar

    # Satırları işle
    for row_idx in range(2, ws.max_row + 1):
        yapan = ws.cell(row=row_idx, column=yapan_idx+1).value
        edilen = ws.cell(row=row_idx, column=edilen_idx+1).value
        if not yapan and not edilen:
            continue  # boş satır

        # 48 cevap topla
        cevaplar = {}
        eksik = []
        for i in range(1,49):
            col = s_idx[i-1] + 1
            ham = ws.cell(row=row_idx, column=col).value
            harf = _harfe_cevir(ham)
            if not harf:
                eksik.append(i)
            else:
                cevaplar[f"soru{i}"] = harf

        if eksik:
            hatalar.append(f"{row_idx}. satırda eksik/yanlış cevaplar: {', '.join(map(str, eksik))}")
            continue

        # Mevcut puanlama ve alan hesaplarını kullan
        puanlar, genel_A, genel_G = puan_hesapla(cevaplar)
        alanlar = hesapla_johari_alanlari(puanlar)

        sonuclar.append({
            "yapan": str(yapan or "").strip(),
            "test_edilen": str(edilen or "").strip(),
            "puanlar": puanlar,
            "genel_A": genel_A,
            "genel_G": genel_G,
            "alanlar": alanlar
        })
    return sonuclar, hatalar
@app.route("/excel-yukle", methods=["GET","POST"], endpoint="excel_yukle")
def excel_yukle():
    wb = Workbook()
    ws = wb.active
    ws.title = "Cevaplar"
    headers = ["Yapan", "Test Edilen"] + [f"S{i}" for i in range(1,49)]
    ws.append(headers)
    # örnek satır
    ws.append(["Ali", "Veli"] + ["A"]*48)
    bio = BytesIO()
    wb.save(bio); bio.seek(0)
    return send_file(bio, as_attachment=True, download_name="johari_sablon.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

from werkzeug.utils import secure_filename

@app.route("/excel-yukle", methods=["GET","POST"])
def excel_yukle():
    if request.method == "GET":
        return render_template("excel_yukle.html")

    f = request.files.get("dosya")
    if not f or not f.filename.lower().endswith(".xlsx"):
        flash("Lütfen .xlsx uzantılı Excel dosyası yükleyin.", "error")
        return redirect(url_for("excel_yukle"))

    # Dosyayı bellekten oku
    try:
        sonuclar, hatalar = _exceli_oku_ve_hesapla(f)
    except Exception as e:
        flash(f"Dosya okunamadı: {e}", "error")
        return redirect(url_for("excel_yukle"))

    if hatalar:
        for h in hatalar:
            flash(h, "error")
        if not sonuclar:
            return redirect(url_for("excel_yukle"))

    # Yalnızca BU oturumda görünür
    session["excel_sonuc_list"] = sonuclar
    return redirect(url_for("excel_sonuc"))


# ================== ROUTELAR ==================
@app.route("/")
def giris():
    # Modern hero tasarımlı giriş
    return render_template("giris.html")

@app.route("/index", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        yapan = request.form.get("yapan", "").strip()
        test_edilen = request.form.get("test_edilen", "").strip()
        if request.form.get("kendim_icin") == "on":
            test_edilen = yapan

        # Sorular yükle
        from sorular import sorular

        # Oturuma temel bilgiler
        session.permanent = True
        session['yapan'] = yapan
        session['test_edilen'] = test_edilen
        session['cevap_id'] = str(uuid.uuid4())

        # Test sayfası
        return render_template("test.html", yapan=yapan, test_edilen=test_edilen, sorular=sorular)
    return render_template("index.html")  # mevcut sayfan varsa çalışmaya devam etsin

@app.route("/indir/sonuclar")
def indir_sonuc():
    admin_key = os.environ.get("ADMIN_PASS")
    key = request.args.get("key")
    if not admin_key or key != admin_key:
        abort(403)
    path = os.path.join(current_app.root_path, "data", "sonuclar.xlsx")
    if not os.path.exists(path):
        abort(404, description="Henüz kayıt yok.")
    return send_file(path, as_attachment=True, download_name="johari_tum_sonuclar.xlsx")


# === GİZLİ RAPOR/EXCEL İNDİRME (Admin korumalı) ===
from flask import send_file, abort, current_app
from werkzeug.utils import safe_join
import shutil, time

@app.route("/indir/benim-sonucum")
def indir_benim_sonucum():
    data = session.get("sonuc")
    if not data:
        return redirect(url_for("index"))

    wb = Workbook()
    ws = wb.active
    ws.title = "Benim Sonucum"
    ws.append([
        "Tarih", "Yapan", "Test Edilen",
        "A1", "A2", "G1", "G2", "Genel A", "Genel G",
        "Açık", "Kör", "Gizli", "Bilinmeyen",
        "Açık (%)", "Kör (%)", "Gizli (%)", "Bilinmeyen (%)"
    ])

    alanlar = data["alanlar"]
    puanlar = data["puanlar"]
    ws.append([
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        data["yapan"], data["test_edilen"],
        puanlar["A1"], puanlar["A2"], puanlar["G1"], puanlar["G2"],
        data["genel_A"], data["genel_G"],
        round(alanlar["acik"], 2), round(alanlar["kor"], 2),
        round(alanlar["gizli"], 2), round(alanlar["bilinmeyen"], 2),
        f"%{alanlar['acik_yuzde']}", f"%{alanlar['kor_yuzde']}",
        f"%{alanlar['gizli_yuzde']}", f"%{alanlar['bilinmeyen_yuzde']}"
    ])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    fname = f"johari_{data['yapan']}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        stream,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# === E-POSTA GÖNDERME (isteğe bağlı) ===
@app.route("/eposta-gonder", methods=["POST"])
def eposta_gonder():
    yapan = request.form.get("yapan")
    eposta = request.form.get("eposta")
    grafik_path = request.form.get("grafik_path")
    yorum = request.form.get("yorum")
    alanlar = {
        "acik_yuzde": float(request.form.get("alanlar_acik", 0)),
        "kor_yuzde": float(request.form.get("alanlar_kor", 0)),
        "gizli_yuzde": float(request.form.get("alanlar_gizli", 0)),
        "bilinmeyen_yuzde": float(request.form.get("alanlar_bilinmeyen", 0))
    }
    mail_gonder(eposta, yapan, grafik_path, alanlar, yorum)
    return redirect(url_for("sonuc_get"))

# === TEST SONUCU HESAPLAMA ===
@app.route("/sonuc", methods=["POST"])
def sonuc_post():
    yapan = request.form["yapan"]
    test_edilen = request.form["test_edilen"]
    cevaplar = {k: v for k, v in request.form.items() if k.startswith("soru")}
    puanlar, genel_A, genel_G = puan_hesapla(cevaplar)
    alanlar = hesapla_johari_alanlari(puanlar)

    # ÜSTTE Açık & Kör olacak şekilde grafik
    grafik_path = ciz_grafik_duzenli(alanlar, yapan)

    # Yapay zeka yorumu
    yorum = yapay_zeka_yorumla(yapan, test_edilen, alanlar)

    # Excel'e KAYIT (artık data/sonuclar.xlsx)
    kaydet_excel(yapan, test_edilen, puanlar, genel_A, genel_G, alanlar)

    # PRG (Post/Redirect/Get) için session'a özet koy
    session["sonuc"] = {
        "yapan": yapan,
        "test_edilen": test_edilen,
        "puanlar": puanlar,
        "genel_A": genel_A,
        "genel_G": genel_G,
        "grafik_path": grafik_path,
        "alanlar": alanlar,
        "yorum": yorum
    }
    return redirect(url_for("sonuc_get"))

@app.route("/sonuc", methods=["GET"])
def sonuc_get():
    data = session.get("sonuc")
    if not data:
        return redirect(url_for("index"))
    return render_template("sonuc.html", **data)

# ================== SKORLAMA ==================
def puan_hesapla(cevaplar):
    G1 = [1,4,6,14,16,24,26,34,36,40,46,47]
    G2 = [3,9,12,18,21,28,30,31,37,41,44]
    A1 = [2,5,7,13,17,19,23,25,27,29,32,35]
    A2 = [8,10,11,15,20,22,33,38,42,43,45,48]

    harf_puanlari = {"A": 1, "B": 2, "C": 3, "D": 4}
    puanlar = {"G1": 0, "G2": 0, "A1": 0, "A2": 0}

    for key, secenek in cevaplar.items():
        soru_no = int(key.replace("soru", ""))
        for grup, liste in [("G1", G1), ("G2", G2), ("A1", A1), ("A2", A2)]:
            if soru_no in liste:
                puanlar[grup] += harf_puanlari.get(secenek, 0)

    genel_A = round((puanlar["A1"] + puanlar["A2"]) / 2, 2)
    genel_G = round((puanlar["G1"] + puanlar["G2"]) / 2, 2)
    return puanlar, genel_A, genel_G

def hesapla_johari_alanlari(puanlar):
    # 48x48 grid’e yerleştiriyoruz
    A = (puanlar["A1"] + puanlar["A2"]) / 2
    G = (puanlar["G1"] + puanlar["G2"]) / 2

    alan_acik = (G * A) / 2304
    alan_kor = ((48 - G) * A) / 2304
    alan_gizli = (G * (48 - A)) / 2304
    alan_bilinmeyen = ((48 - G) * (48 - A)) / 2304

    return {
        "acik": alan_acik,
        "kor": alan_kor,
        "gizli": alan_gizli,
        "bilinmeyen": alan_bilinmeyen,
        "acik_yuzde": round(alan_acik * 100, 2),
        "kor_yuzde": round(alan_kor * 100, 2),
        "gizli_yuzde": round(alan_gizli * 100, 2),
        "bilinmeyen_yuzde": round(alan_bilinmeyen * 100, 2),
        "G": G,
        "A": A
    }

# ================== GRAFİK (ÜSTTE AÇIK & KÖR) ==================
def ciz_grafik_duzenli(alanlar, yapan_adi):
    G = max(0, min(48, alanlar["G"]))
    A = max(0, min(48, alanlar["A"]))

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(0, 48)
    ax.set_ylim(0, 48)
    ax.set_aspect("equal")
    ax.axis("off")

    # Üst sıra: Açık (sol) + Kör (sağ) — y=48-A ... 48
    rects = [
        ((0, 48 - A),       G,      A,      "Açık",        alanlar['acik_yuzde']),
        ((G, 48 - A),       48 - G, A,      "Kör",         alanlar['kor_yuzde']),
        ((0, 0),            G,      48 - A, "Gizli",       alanlar['gizli_yuzde']),
        ((G, 0),            48 - G, 48 - A, "Bilinmeyen",  alanlar['bilinmeyen_yuzde']),
    ]
    colors = ["#b8e994", "#f8c291", "#82ccdd", "#d1d8e0"]

    for i, (xy, w, h, ad, yuzde) in enumerate(rects):
        ax.add_patch(patches.Rectangle(xy, w, h, alpha=0.7, ec="#2f3640", fc=colors[i], lw=1.5))
        if w > 2 and h > 2:
            ax.text(xy[0] + w/2, xy[1] + h/2, f"{ad}\n%{yuzde}", ha="center", va="center", fontsize=12, weight="bold")

    # Bölücü çizgiler
    ax.axhline(y=48 - A, color="black", linewidth=1.5)
    ax.axvline(x=G, color="black", linewidth=1.5)

    # Dosya
    kisi = slugify(yapan_adi)
    dosya_adi = f"johari_{kisi}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    tam_yol = os.path.join(GRAFIK_DIR, dosya_adi)
    fig.tight_layout()
    fig.savefig(tam_yol, dpi=150)
    plt.close(fig)
    return f"grafik/{dosya_adi}"

# ================== YZ YORUM ==================
import os, requests

# app.py (üstte bunlar olsun)
import os, requests, hashlib
from flask import session

# app.py (üstte bunlar olsun)
import os, requests, hashlib
from flask import session

def yapay_zeka_yorumla(yapan, test_edilen, alanlar):
    # kişiye özel ton için tohum
    seed_src = f"{yapan}|{test_edilen}|{alanlar['acik_yuzde']}-{alanlar['kor_yuzde']}-{alanlar['gizli_yuzde']}-{alanlar['bilinmeyen_yuzde']}|{session.get('cevap_id','')}"
    seed_int = int(hashlib.sha256(seed_src.encode('utf-8')).hexdigest(), 16)
    tonlar = ["sakin", "analitik", "sıcak", "ilham verici"]
    ton = tonlar[seed_int % len(tonlar)]

    a = alanlar['acik_yuzde']; k = alanlar['kor_yuzde']; g = alanlar['gizli_yuzde']; b = alanlar['bilinmeyen_yuzde']
    prompt = f"""
Johari sonucu (Türkçe, serbest metin):
Yapan: {yapan}
Test edilen: {test_edilen}
Açık %{a}, Kör %{k}, Gizli %{g}, Bilinmeyen %{b}

Rolün: {ton} bir danışman gibi yaz.
Biçim: Serbest anlatı; en fazla 2 veya 3 paragraf; başlık, madde işareti, numara yok.
İçerik: Oranları birlikte yorumla; güçlü ve gelişime açık noktaları doğal akışta işle.
Açık alanı büyütme ve kör alanı azaltma fikirlerini metnin içine yedir; ayrı liste yapma.
Yaklaşık 180–260 kelime yaz; klişeden kaçın; tekrar etme.
Yalnızca Türkçe harfler ve standart noktalama kullan; emoji veya özel sembol kullanma.
"""

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return _yerel_serbest_yorum(test_edilen, a, k, g, b, ton)

    base_url = os.environ.get("OPENROUTER_URL", "https://openrouter.ai/api/v1")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("OR_REFERER", "https://example.com"),
        "X-Title": "Johari Test Platformu"
    }
    primary = os.environ.get("OPENROUTER_MODEL", "openrouter/auto")
    candidates = [primary,
                  "mistralai/mistral-small:free",
                  "mistralai/mistral-nemo:free",
                  "qwen/qwen2.5-7b-instruct:free",
                  "meta-llama/llama-3.1-8b-instruct:free"]

    def payload(model):
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": "Profesyonel, akıcı, kişiye özel ve tekrarsız Türkçe anlatı yaz."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 900,
            "temperature": 0.95,
            "top_p": 0.9,
            "presence_penalty": 0.4,
            "frequency_penalty": 0.35
        }

    for m in candidates:
        try:
            r = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload(m), timeout=25)
            if r.status_code == 200:
                txt = (r.json().get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
                words = len(txt.split())
                if words >= 160:  # alt sınır; çok kısaysa yedek dene
                    return txt.strip()
        except Exception:
            continue

    return _yerel_serbest_yorum(test_edilen, a, k, g, b, ton)


def _yerel_serbest_yorum(ad, a, k, g, b, ton):
    # Serbest, 2–3 paragraflık offline anlatım (başlık/madde yok)
    def s(x):
        if x >= 40: return "çok yüksek"
        if x >= 28: return "yüksek"
        if x >= 18: return "orta"
        return "düşük"

    p1 = (f"{ad} için çıkan tablo, güçlü yanları ile gelişime açık alanların yan yana durduğunu gösteriyor. "
          f"Açık alanın {s(a)} düzeyde olması, niyetin ve çalışma tarzının çoğunlukla anlaşılır olduğunu düşündürüyor; "
          f"bu da güveni ve işbirliğini destekler. Buna karşılık kör alanın {s(k)} görünmesi, bazı etkilerin niyet ile "
          f"tam örtüşmediği anlara işaret ediyor. Gizli alanın {s(g)} olması, uygun bağlam verildiğinde ilişkilerin daha da "
          f"rahatlayabileceğini düşündürürken, bilinmeyen alanın {s(b)} düzeyi küçük denemelerle yeni beceriler "
          f"kazanılabileceğini ima ediyor.")

    p2 = (f"Bu resimde odak, açık alanı bilinçli paylaşım ile büyütmek ve kör alanı geri bildirim akışıyla daraltmak olabilir. "
          f"Toplantı öncesi kısa bir özet paylaşmak, alınan kararlarda varsayımları görünür kılar; itiraz ya da farklı görüş "
          f"geldiğinde önce gerekçeyi merakla duymak etkili olur. Gün sonunda iki cümlelik notlar, hangi davranışın nasıl bir "
          f"etki yarattığını hatırlatır. Kişisel sınırlar ve beklentiler birkaç net cümleyle yazıldığında gizli alan rahatlar; "
          f"iki haftalık küçük bir pilot uygulama ise bilinmeyeni güvenli bir alanda keşfetmenin en pratik yoludur.")

    p3 = (f"Zaman içinde düzenli geri bildirim ile birlikte bu dört alanın dengesi değişir; açık alan büyüdükçe iletişim doğal "
          f"olarak sadeleşir ve karar süreçleri hızlanır. {ad} için öneri, hız yerine ritim kurmak: küçük adımlar, düzenli görünürlük "
          f"ve her adımın sonunda kısa bir değerlendirme. Böylece güçlü yanlar daha belirginleşir, gelişime açık taraflar ise "
          f"zorlanmadan dönüşür.")

    if (a + k + g + b) > 0:
        return f"{p1}\n\n{p2}\n\n{p3}"
    else:
        return (f"{ad} için yorum üretilemedi. Yine de küçük, düzenli paylaşımlar ve kısa geri bildirim turlarıyla açık alanı "
                f"artırmak mümkün. Her karar öncesi kısa bir taslak ve sonrasında iki cümlelik değerlendirme, doğal bir ilerleme ritmi sağlar.")




# ================== EXCEL KAYIT (GİZLİ KONUM) ==================
def kaydet_excel(yapan, test_edilen, puanlar, genel_A, genel_G, alanlar):
    os.makedirs("data", exist_ok=True)
    dosya_yolu = os.path.join("data", "sonuclar.xlsx")
    if not os.path.exists(dosya_yolu):
        wb = Workbook()
        ws = wb.active
        ws.title = "Sonuçlar"
        ws.append([
            "Tarih", "Yapan", "Test Edilen",
            "A1", "A2", "G1", "G2", "Genel A", "Genel G",
            "Açık", "Kör", "Gizli", "Bilinmeyen",
            "Açık (%)", "Kör (%)", "Gizli (%)", "Bilinmeyen (%)"
        ])
    else:
        wb = load_workbook(dosya_yolu)
        ws = wb.active

    ws.append([
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        yapan, test_edilen,
        puanlar["A1"], puanlar["A2"], puanlar["G1"], puanlar["G2"],
        genel_A, genel_G,
        round(alanlar["acik"], 2), round(alanlar["kor"], 2),
        round(alanlar["gizli"], 2), round(alanlar["bilinmeyen"], 2),
        f"%{alanlar['acik_yuzde']}", f"%{alanlar['kor_yuzde']}",
        f"%{alanlar['gizli_yuzde']}", f"%{alanlar['bilinmeyen_yuzde']}"
    ])
    wb.save(dosya_yolu)



# ================== MAİL ==================
def mail_gonder(eposta, yapan, grafik_path, alanlar, yorum):
    try:
        msg = Message(
            subject="Johari Test Sonucunuz ve Tavsiyeler",
            recipients=[eposta]
        )
        msg.body = (
            f"Merhaba {yapan},\n\n"
            "Johari Test Sonuçlarınız:\n"
            f"Açık Alan: %{alanlar['acik_yuzde']}\n"
            f"Kör Alan: %{alanlar['kor_yuzde']}\n"
            f"Gizli Alan: %{alanlar['gizli_yuzde']}\n"
            f"Bilinmeyen Alan: %{alanlar['bilinmeyen_yuzde']}\n\n"
            f"Yapay Zeka Yorumu:\n{yorum}\n\n"
            "Sevgiler,\nJohari Testi"
        )
        with app.open_resource(os.path.join("static", grafik_path)) as fp:
            msg.attach("johari_sonuc.png", "image/png", fp.read())
        mail.send(msg)
    except Exception as e:
        print(f"[HATA] Mail gönderilemedi: {str(e)}")

# ================== ÖNBELLEK KAPAT ==================
@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# ================== MAIN ==================
if __name__ == "__main__":
    app.run(debug=True)
