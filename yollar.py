from uygulama import uygulama
from uzantılar import db
from modeller import Kullanıcı, Anket, Soru, Seçenek, Yanıt, Cevap
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
    if anket.yayında_mı:
        return render_template("anket_duzenle.html", anket=anket, hata="Yayındaki ankete soru eklenemez")
    if request.method == "POST":
        metin = request.form["metin"]
        tip = request.form["tip"]
        zorunlu_mu = "zorunlu_mu" in request.form
        if not metin.strip():
            return render_template("anket_duzenle.html", anket=anket, hata="Metin boş bırakılamaz")

        ölçek_alt_sınırı = None
        ölçek_üst_sınırı = None
        if tip == "ölçek":
            try:
                ölçek_alt_sınırı = int(request.form["ölçek_alt_sınırı"])
                ölçek_üst_sınırı = int(request.form["ölçek_üst_sınırı"])
            except (ValueError, KeyError):
                return render_template("anket_duzenle.html", anket=anket, hata="Geçersiz ölçek sınırı")

            if ölçek_alt_sınırı >= ölçek_üst_sınırı:
                return render_template("anket_duzenle.html", anket=anket, hata="Alt sınır üst sınırdan küçük olmalıdır")

        seçenekler = []
        if tip == "çoktan seçmeli":
            seçenekler = [s.strip() for s in request.form.getlist("seçenek") if s.strip()]
            if len(seçenekler) < 2:
                return render_template("anket_duzenle.html", anket=anket, hata="Seçenek en az 2 olmalıdır")

        soru = Soru(
            metin=metin,
            tip=tip,
            zorunlu_mu=zorunlu_mu,
            anket_kimlik=anket_kimlik,
            sıra=len(anket.sorular) + 1,
            ölçek_alt_sınırı=ölçek_alt_sınırı,
            ölçek_üst_sınırı=ölçek_üst_sınırı
        )

        for sıra, seçenek_metni in enumerate(seçenekler, start=1):
            soru.seçenekler.append(Seçenek(metin=seçenek_metni, sıra=sıra))

        db.session.add(soru)
        db.session.commit()
        return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))
    return render_template("anket_duzenle.html", anket=anket)

@uygulama.route("/anket/<int:anket_kimlik>/yayinla", methods=["POST"])
def anket_yayınlama(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)
    if not anket.sorular:
        return render_template("anket_duzenle.html", anket=anket, hata="Boş anket yayınlanamaz")
    anket.yayında_mı = True
    db.session.commit()
    return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

@uygulama.route("/anket/<int:anket_kimlik>/yayindan-al", methods=["POST"])
def anket_yayından_alma(anket_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    kimlik = session.get("kullanıcı_kimlik")
    if anket is None:
        abort(404)
    if anket.sahip_kimlik != kimlik:
        abort(403)
    anket.yayında_mı = False
    db.session.commit()
    return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

@uygulama.context_processor
def oturum_bilgisi():
    kimlik = session.get("kullanıcı_kimlik")
    return {"oturum_kullanıcısı": db.session.get(Kullanıcı, kimlik) if kimlik else None}

@uygulama.route("/anketler")
def anket_listesi():
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))
    anketler = db.session.execute(
        db.select(Anket)
        .where(Anket.yayında_mı.is_(True), Anket.herkese_açık_mı.is_(True))
    ).scalars().all()
    return render_template("anketler.html", anketler=anketler)

@uygulama.route("/anket/<int:anket_kimlik>/yanitla", methods=["GET", "POST"])
def anket_yanıtlama(anket_kimlik):
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    anket = db.session.get(Anket, anket_kimlik)
    if anket is None:
        abort(404)

    if not anket.yayında_mı:
        abort(403)

    yanıt = db.session.execute(
        db.select(Yanıt).where(
            Yanıt.anket_kimlik == anket_kimlik,
            Yanıt.yanıtlayan_kimlik == kimlik,
        )
    ).scalar_one_or_none()
    if yanıt:
        return redirect(url_for("anket_listesi"))

    if request.method == "POST":
        yanıt = Yanıt(anket_kimlik=anket_kimlik, yanıtlayan_kimlik=kimlik)

        for soru in anket.sorular:
            değer = request.form.get("soru_" + str(soru.kimlik))

            if not değer or not değer.strip():
                if soru.zorunlu_mu:
                    db.session.rollback()
                    return render_template("anket_yanitla.html", anket=anket, hata=f"'{soru.metin}' sorusu zorunludur")
                continue

            değer = değer.strip()
            cevap = Cevap(soru_kimlik=soru.kimlik)

            if soru.tip == "açık uçlu":
                cevap.metin_değeri = değer
            elif soru.tip == "evet/hayır":
                cevap.evet_hayır_değeri = (değer == "evet")
            elif soru.tip == "ölçek":
                try:
                    sayısal = int(değer)
                except ValueError:
                    db.session.rollback()
                    return render_template("anket_yanitla.html", anket=anket, hata=f"'{soru.metin}' için geçerli bir sayı giriniz")
                if (soru.ölçek_alt_sınırı is not None and sayısal < soru.ölçek_alt_sınırı) or \
                   (soru.ölçek_üst_sınırı is not None and sayısal > soru.ölçek_üst_sınırı):
                    db.session.rollback()
                    return render_template("anket_yanitla.html", anket=anket, hata=f"'{soru.metin}' için değer {soru.ölçek_alt_sınırı} ile {soru.ölçek_üst_sınırı} arasında olmalıdır")
                cevap.sayısal_değer = sayısal
            elif soru.tip == "çoktan seçmeli":
                try:
                    seçilen_kimlik = int(değer)
                except ValueError:
                    db.session.rollback()
                    return render_template("anket_yanitla.html", anket=anket, hata="Geçersiz seçenek")
                if not any(seçenek.kimlik == seçilen_kimlik for seçenek in soru.seçenekler):
                    db.session.rollback()
                    return render_template("anket_yanitla.html", anket=anket, hata="Geçersiz seçenek")
                cevap.seçilen_seçenek_kimlik = seçilen_kimlik

            yanıt.cevaplar.append(cevap)

        db.session.add(yanıt)
        db.session.commit()
        return redirect(url_for("anket_listesi"))

    return render_template("anket_yanitla.html", anket=anket)

