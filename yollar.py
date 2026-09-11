from uygulama import uygulama
from uzantılar import db
from modeller import Kullanıcı, Anket, Soru
from email_validator import validate_email, EmailNotValidError
from flask import render_template, request, redirect, url_for, session, abort
from werkzeug.security import generate_password_hash, check_password_hash

@uygulama.route("/")
def ana_sayfa():
    kimlik = session.get("kullanıcı_kimlik")
    anketler = []
    if kimlik:
        anketler = db.session.execute(
            db.select(Anket).where(Anket.sahip_kimlik == kimlik)
        ).scalars().all()
    return render_template("ana_sayfa.html", anketler=anketler)

@uygulama.route("/kayit", methods=["GET", "POST"])
def kayıt_ekranı():
    if request.method == "POST":
        e_posta = request.form["e_posta"]
        parola = request.form["parola"]
        # 1. biçim geçersizse mesaj göster, kaydetme
        try:
            validate_email(e_posta, check_deliverability=False)
        except EmailNotValidError:
            return render_template("kayit.html", hata="Geçersiz e-posta adresi")
        # 2. e-posta kayıtlıysa mesaj göster, kaydetme
        if db.session.execute(db.select(Kullanıcı).where(Kullanıcı.e_posta == e_posta)).scalar_one_or_none():
            return render_template("kayit.html", hata="E-posta adresi zaten kayıtlı")
        # 3. özet al
        özet = generate_password_hash(parola)
        # 4. kullanıcıyı oluştur, add + commit
        kullanıcı = Kullanıcı(e_posta=e_posta, parola_özeti=özet)
        db.session.add(kullanıcı)
        db.session.commit()
        # 5. yönlendir
        return redirect(url_for("ana_sayfa"))
    return render_template("kayit.html")

@uygulama.route("/giris", methods=["GET", "POST"])
def giriş_ekranı():
    if request.method == "POST":
        e_posta = request.form["e_posta"]
        parola = request.form["parola"]
        # e-posta var mı?
        kullanıcı = db.session.execute(
            db.select(Kullanıcı).where(Kullanıcı.e_posta == e_posta)
        ).scalar_one_or_none()
        if not kullanıcı:
            return render_template("giris.html", hata="E-posta veya parola hatalı")
        # parola eşleşiyor mu?
        if not check_password_hash(kullanıcı.parola_özeti, parola):
            return render_template("giris.html", hata="E-posta veya parola hatalı")
        # giriş yap (session ile)
        session["kullanıcı_kimlik"] = kullanıcı.kimlik
        return redirect(url_for("ana_sayfa"))
    return render_template("giris.html")

@uygulama.route("/çıkış")
def çıkış():
    session.pop("kullanıcı_kimlik", None)
    return redirect(url_for("ana_sayfa"))

@uygulama.route("/anket/yeni", methods=["GET", "POST"])
def anket_oluşturma():
    kimlik = session.get("kullanıcı_kimlik")

    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    if request.method == "POST":
        başlık = request.form["başlık"]
        açıklama = request.form["açıklama"]
        anonim_mi = "anonim_mi" in request.form
        if not başlık.strip():
            return render_template("anket_yeni.html", hata="Başlık boş bırakılamaz")

        herkese_açık_mı = "herkese_açık_mı" in request.form
        anket = Anket(başlık=başlık, açıklama=açıklama, anonim_mi=anonim_mi, herkese_açık_mı=herkese_açık_mı, sahip_kimlik=kimlik)
        db.session.add(anket)
        db.session.commit()
        return redirect(url_for("ana_sayfa"))
    return render_template("anket_yeni.html")

@uygulama.route("/anket/<int:anket_kimlik>/duzenle")
def anket_duzenle(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)
    return render_template("anket_duzenle.html", anket=anket)

@uygulama.route("/anket/<int:anket_kimlik>/soru/yeni", methods=["GET", "POST"])
def soru_ekleme(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)
    if request.method == "POST":
        metin = request.form["metin"]
        tip = request.form["tip"]
        zorunlu_mu = "zorunlu_mu" in request.form
        if not metin.strip():
            return render_template("anket_duzenle.html", hata="Metin boş bırakılamaz")
        soru = Soru(metin=metin, tip=tip, zorunlu_mu=zorunlu_mu, anket_kimlik=anket_kimlik, sıra=len(anket.sorular) + 1)
        db.session.add(soru)
        db.session.commit()
        return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))
    return render_template("anket_duzenle.html", anket=anket)

@uygulama.context_processor
def oturum_bilgisi():
    kimlik = session.get("kullanıcı_kimlik")
    return {"oturum_kullanıcısı": db.session.get(Kullanıcı, kimlik) if kimlik else None}