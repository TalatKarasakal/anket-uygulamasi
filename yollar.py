from datetime import datetime, timedelta
from uygulama import uygulama
from uzantılar import db
from modeller import Kullanıcı, Anket, Soru, Seçenek, Yanıt, Cevap, AnketYetki, AnketTanımlama, Kalıp
from email_validator import validate_email, EmailNotValidError
from flask import render_template, request, redirect, url_for, session, abort
from werkzeug.security import generate_password_hash, check_password_hash

TİP_İZİN_ALANI = {
    "açık uçlu": "açık_uçlu_izinli_mi",
    "evet/hayır": "evet_hayır_izinli_mi",
    "ölçek": "ölçek_izinli_mi",
    "çoktan seçmeli": "çoktan_seçmeli_izinli_mi",
}

def yetkiyi_getir(anket, kimlik):
    if not anket or not kimlik:
        return None
    return db.session.execute(
        db.select(AnketYetki).where(
            AnketYetki.anket_kimlik == anket.kimlik,
            AnketYetki.kullanıcı_kimlik == kimlik,
        )
    ).scalar_one_or_none()

def anketi_getir(anket_kimlik, izin=None):
    anket = db.session.get(Anket, anket_kimlik)
    if anket is None:
        abort(404)
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        abort(403)
    if anket.sahip_kimlik == kimlik:
        return anket

    if izin == "sahip":
        abort(403)

    yetki = yetkiyi_getir(anket, kimlik)

    if not yetki:
        abort(403)

    if yetki.yöneticilik_mi:
        return anket

    if izin is None:
        return anket

    if isinstance(izin, (list, tuple, set)):
        if any(getattr(yetki, i, False) for i in izin):
            return anket
    elif getattr(yetki, izin, False):
        return anket

    abort(403)

def bekleyen_zorunlu_tanımlama(kimlik):
    if not kimlik:
        return []

    şimdi = datetime.now()
    gönderilmiş_anket_kimlikleri = db.select(Yanıt.anket_kimlik).where(
        Yanıt.yanıtlayan_kimlik == kimlik,
        Yanıt.gönderildi_mi.is_(True),
    )

    bekleyenler = db.session.execute(
        db.select(Anket)
        .join(AnketTanımlama, AnketTanımlama.anket_kimlik == Anket.kimlik)
        .where(
            AnketTanımlama.kullanıcı_kimlik == kimlik,
            AnketTanımlama.zorunlu_mu.is_(True),
            Anket.yayında_mı.is_(True),
            db.or_(Anket.son_tarih.is_(None), Anket.son_tarih >= şimdi),
            Anket.kimlik.not_in(gönderilmiş_anket_kimlikleri),
        )
    ).scalars().all()

    return bekleyenler

def anket_duzenle_goster(anket, hata=None):
    kimlik = session.get("kullanıcı_kimlik")
    sahip_mi = (anket.sahip_kimlik == kimlik)
    yetki = yetkiyi_getir(anket, kimlik)
    yönetici_mi = sahip_mi or (yetki and yetki.yöneticilik_mi)
    tanımlama_yetkisi = sahip_mi or (yetki and (yetki.yöneticilik_mi or yetki.kullanıcı_tanımlama_mı))
    içerik_yetkisi = sahip_mi or (yetki and (yetki.yöneticilik_mi or yetki.içerik_düzenleme_mi))
    üye_mi = (yetki is not None)
    return render_template(
        "anket_duzenle.html",
        anket=anket,
        hata=hata,
        sahip_mi=sahip_mi,
        yönetici_mi=yönetici_mi,
        üye_mi=üye_mi,
        tanımlama_yetkisi=tanımlama_yetkisi,
        içerik_yetkisi=içerik_yetkisi,
    )

@uygulama.route("/")
def ana_sayfa():
    kimlik = session.get("kullanıcı_kimlik")
    anketler = []
    üye_olunan_anketler = []
    if kimlik:
        anketler = db.session.execute(
            db.select(Anket).where(Anket.sahip_kimlik == kimlik)
        ).scalars().all()
        üye_olunan_anketler = db.session.execute(
            db.select(Anket).join(AnketYetki, AnketYetki.anket_kimlik == Anket.kimlik)
            .where(AnketYetki.kullanıcı_kimlik == kimlik)
        ).scalars().all()
    return render_template("ana_sayfa.html", anketler=anketler, üye_olunan_anketler=üye_olunan_anketler)

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

@uygulama.route("/hesap/sil", methods=["GET", "POST"])
def hesap_sil():
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    kullanıcı = db.session.get(Kullanıcı, kimlik)
    if not kullanıcı:
        session.clear()
        return redirect(url_for("giriş_ekranı"))

    anketler = db.session.execute(
        db.select(Anket).where(Anket.sahip_kimlik == kimlik)
    ).scalars().all()

    yanıt_sayısı = db.session.execute(
        db.select(db.func.count()).select_from(Yanıt).where(Yanıt.yanıtlayan_kimlik == kimlik)
    ).scalar()

    if request.method == "POST":
        yanıtlar_karar = request.form.get("yanıtlar_karar", "korunsun")
        if yanıtlar_karar not in ("korunsun", "silinsin"):
            return render_template(
                "hesap_sil.html",
                kullanıcı=kullanıcı,
                anketler=anketler,
                yanıt_sayısı=yanıt_sayısı,
                hata="Geçersiz yanıt kararı seçildi",
            )

        # 1. Aşama: Girdilerin ve devir hedeflerinin doğrulanması
        anket_kararları = {}
        for anket in anketler:
            karar = request.form.get(f"anket_{anket.kimlik}_karar")
            if karar not in ("silinsin", "sahipsiz_kalsin", "devredilsin"):
                return render_template(
                    "hesap_sil.html",
                    kullanıcı=kullanıcı,
                    anketler=anketler,
                    yanıt_sayısı=yanıt_sayısı,
                    hata=f"'{anket.başlık}' için geçersiz karar seçildi",
                )

            hedef_yetki = None
            if karar == "devredilsin":
                devir_str = request.form.get(f"anket_{anket.kimlik}_devir")
                try:
                    devir_kimlik = int(devir_str)
                except (ValueError, TypeError):
                    return render_template(
                        "hesap_sil.html",
                        kullanıcı=kullanıcı,
                        anketler=anketler,
                        yanıt_sayısı=yanıt_sayısı,
                        hata=f"'{anket.başlık}' için geçersiz devir hedefi seçildi",
                    )

                hedef_yetki = db.session.execute(
                    db.select(AnketYetki).where(
                        AnketYetki.anket_kimlik == anket.kimlik,
                        AnketYetki.kullanıcı_kimlik == devir_kimlik,
                    )
                ).scalar_one_or_none()

                if not hedef_yetki:
                    return render_template(
                        "hesap_sil.html",
                        kullanıcı=kullanıcı,
                        anketler=anketler,
                        yanıt_sayısı=yanıt_sayısı,
                        hata=f"'{anket.başlık}' için seçilen devir hedefi geçerli bir üye değil",
                    )

            anket_kararları[anket.kimlik] = {
                "karar": karar,
                "hedef_yetki": hedef_yetki,
            }

        # 2. Aşama: Veritabanı işlemlerinin sırayla uygulanması
        try:
            # Anketler
            for anket in anketler:
                bilgi = anket_kararları[anket.kimlik]
                karar = bilgi["karar"]
                if karar == "silinsin":
                    db.session.delete(anket)
                elif karar == "sahipsiz_kalsin":
                    anket.sahip_kimlik = None
                    anket.yayında_mı = False
                    anket.son_tarih = None
                    anket.süre_gün = None
                    for soru in anket.sorular:
                        soru.zorunlu_mu = False
                elif karar == "devredilsin":
                    hedef_yetki = bilgi["hedef_yetki"]
                    devir_kimlik = hedef_yetki.kullanıcı_kimlik
                    anket.sahip_kimlik = devir_kimlik
                    db.session.delete(hedef_yetki)
                    db.session.flush()

            # Yanıtlar (kalan yanıtlar üzerinde işlem yapılır)
            kalan_yanıtlar = db.session.execute(
                db.select(Yanıt).where(Yanıt.yanıtlayan_kimlik == kimlik)
            ).scalars().all()

            if yanıtlar_karar == "korunsun":
                for yanıt in kalan_yanıtlar:
                    yanıt.yanıtlayan_kimlik = None
            elif yanıtlar_karar == "silinsin":
                for yanıt in kalan_yanıtlar:
                    db.session.delete(yanıt)

            # Kullanıcının başka anketlerdeki üyelik ve tanımlamaları
            db.session.execute(
                db.delete(AnketYetki).where(AnketYetki.kullanıcı_kimlik == kimlik)
            )
            db.session.execute(
                db.delete(AnketTanımlama).where(AnketTanımlama.kullanıcı_kimlik == kimlik)
            )

            # Kullanıcı silinir ve oturum temizlenir
            db.session.delete(kullanıcı)
            db.session.commit()
            session.clear()
            return redirect(url_for("ana_sayfa"))

        except Exception as e:
            import traceback
            traceback.print_exc()
            db.session.rollback()
            return render_template(
                "hesap_sil.html",
                kullanıcı=kullanıcı,
                anketler=anketler,
                yanıt_sayısı=yanıt_sayısı,
                hata=f"Hesap silme işlemi sırasında bir hata oluştu: {e}",
            )

    return render_template(
        "hesap_sil.html",
        kullanıcı=kullanıcı,
        anketler=anketler,
        yanıt_sayısı=yanıt_sayısı,
    )


@uygulama.route("/kaliplar")
def kalıp_listesi():
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    sistem_kalıpları = db.session.execute(
        db.select(Kalıp).where(Kalıp.sistem_kalıbı_mı.is_(True)).order_by(Kalıp.ad)
    ).scalars().all()

    kullanıcı_kalıpları = db.session.execute(
        db.select(Kalıp).where(Kalıp.sahip_kimlik == kimlik).order_by(Kalıp.ad)
    ).scalars().all()

    return render_template(
        "kaliplar.html",
        sistem_kalıpları=sistem_kalıpları,
        kullanıcı_kalıpları=kullanıcı_kalıpları,
        uyarı=request.args.get("uyari"),
    )


@uygulama.route("/kalip/yeni", methods=["GET", "POST"])
def kalıp_oluşturma():
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    if request.method == "POST":
        ad = request.form.get("ad", "").strip()
        if not ad:
            return render_template("kalip_yeni.html", hata="Kalıp adı boş bırakılamaz", form=request.form)

        # 1. Sistem kalıbı adı ile çakışma denetimi (İG-12 ikinci yarısı)
        sistemde_var = db.session.execute(
            db.select(Kalıp).where(Kalıp.sistem_kalıbı_mı.is_(True), Kalıp.ad == ad)
        ).scalar_one_or_none()
        if sistemde_var:
            return render_template(
                "kalip_yeni.html",
                hata="Sistem kalıbı ile aynı ada sahip kalıp oluşturulamaz",
                form=request.form,
            )

        # 2. Kullanıcı bazında tekil ad denetimi (İG-12 ilk yarısı)
        kullanıcıda_var = db.session.execute(
            db.select(Kalıp).where(Kalıp.sahip_kimlik == kimlik, Kalıp.ad == ad)
        ).scalar_one_or_none()
        if kullanıcıda_var:
            return render_template(
                "kalip_yeni.html",
                hata="Bu ada sahip bir kalıbınız zaten bulunmaktadır",
                form=request.form,
            )

        açık_uçlu_izinli_mi = "açık_uçlu_izinli_mi" in request.form
        evet_hayır_izinli_mi = "evet_hayır_izinli_mi" in request.form
        ölçek_izinli_mi = "ölçek_izinli_mi" in request.form
        çoktan_seçmeli_izinli_mi = "çoktan_seçmeli_izinli_mi" in request.form
        anonim_mi = "anonim_mi" in request.form
        herkese_açık_mı = "herkese_açık_mı" in request.form

        süre_gün_metni = request.form.get("süre_gün", "").strip()
        süre_gün = None
        if süre_gün_metni:
            try:
                süre_gün = int(süre_gün_metni)
                if süre_gün <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                return render_template(
                    "kalip_yeni.html",
                    hata="Süre pozitif bir gün sayısı olmalıdır",
                    form=request.form,
                )

        # 3. Aynı özellik kümesi uyarısı (İG-14: uyarı, engel değil)
        onaylandı_mı = request.form.get("onaylandı_mı") == "1"

        if not onaylandı_mı:
            süre_koşulu = (Kalıp.süre_gün == süre_gün) if süre_gün is not None else Kalıp.süre_gün.is_(None)
            eşleşen_kalıp = db.session.execute(
                db.select(Kalıp).where(
                    db.or_(Kalıp.sistem_kalıbı_mı.is_(True), Kalıp.sahip_kimlik == kimlik),
                    Kalıp.açık_uçlu_izinli_mi == açık_uçlu_izinli_mi,
                    Kalıp.evet_hayır_izinli_mi == evet_hayır_izinli_mi,
                    Kalıp.ölçek_izinli_mi == ölçek_izinli_mi,
                    Kalıp.çoktan_seçmeli_izinli_mi == çoktan_seçmeli_izinli_mi,
                    Kalıp.anonim_mi == anonim_mi,
                    Kalıp.herkese_açık_mı == herkese_açık_mı,
                    süre_koşulu,
                )
            ).scalars().first()

            if eşleşen_kalıp:
                return render_template(
                    "kalip_yeni.html",
                    uyarı=f"Dikkat: Bu özellik kümesi '{eşleşen_kalıp.ad}' adlı kalıp ile birebir aynıdır. Yine de kaydetmek istiyorsanız 'Kaydet' butonuna tekrar tıklayınız.",
                    form=request.form,
                    onay_gerekiyor=True,
                )

        yeni_kalıp = Kalıp(
            sahip_kimlik=kimlik,
            ad=ad,
            sistem_kalıbı_mı=False,
            açık_uçlu_izinli_mi=açık_uçlu_izinli_mi,
            evet_hayır_izinli_mi=evet_hayır_izinli_mi,
            ölçek_izinli_mi=ölçek_izinli_mi,
            çoktan_seçmeli_izinli_mi=çoktan_seçmeli_izinli_mi,
            anonim_mi=anonim_mi,
            herkese_açık_mı=herkese_açık_mı,
            süre_gün=süre_gün,
        )
        db.session.add(yeni_kalıp)
        db.session.commit()
        return redirect(url_for("kalıp_listesi"))

    return render_template("kalip_yeni.html")


@uygulama.route("/kalip/<int:kalip_kimlik>/duzenle", methods=["GET", "POST"])
def kalıp_düzenleme(kalip_kimlik):
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    kalıp = db.session.get(Kalıp, kalip_kimlik)
    if not kalıp:
        abort(404)

    # İG-13: Sistem kalıbı düzenlenemez, yalnızca sahip düzenleyebilir
    if kalıp.sistem_kalıbı_mı or kalıp.sahip_kimlik != kimlik:
        abort(403)

    if request.method == "POST":
        ad = request.form.get("ad", "").strip()
        if not ad:
            return render_template("kalip_duzenle.html", kalıp=kalıp, hata="Kalıp adı boş bırakılamaz", form=request.form)

        # Ad değiştiyse çakışma denetimleri
        if ad != kalıp.ad:
            sistemde_var = db.session.execute(
                db.select(Kalıp).where(Kalıp.sistem_kalıbı_mı.is_(True), Kalıp.ad == ad)
            ).scalar_one_or_none()
            if sistemde_var:
                return render_template(
                    "kalip_duzenle.html",
                    kalıp=kalıp,
                    hata="Sistem kalıbı ile aynı ada sahip kalıp oluşturulamaz",
                    form=request.form,
                )

            kullanıcıda_var = db.session.execute(
                db.select(Kalıp).where(
                    Kalıp.sahip_kimlik == kimlik,
                    Kalıp.ad == ad,
                    Kalıp.kimlik != kalıp.kimlik,
                )
            ).scalar_one_or_none()
            if kullanıcıda_var:
                return render_template(
                    "kalip_duzenle.html",
                    kalıp=kalıp,
                    hata="Bu ada sahip bir kalıbınız zaten bulunmaktadır",
                    form=request.form,
                )

        açık_uçlu_izinli_mi = "açık_uçlu_izinli_mi" in request.form
        evet_hayır_izinli_mi = "evet_hayır_izinli_mi" in request.form
        ölçek_izinli_mi = "ölçek_izinli_mi" in request.form
        çoktan_seçmeli_izinli_mi = "çoktan_seçmeli_izinli_mi" in request.form
        anonim_mi = "anonim_mi" in request.form
        herkese_açık_mı = "herkese_açık_mı" in request.form

        süre_gün_metni = request.form.get("süre_gün", "").strip()
        süre_gün = None
        if süre_gün_metni:
            try:
                süre_gün = int(süre_gün_metni)
                if süre_gün <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                return render_template(
                    "kalip_duzenle.html",
                    kalıp=kalıp,
                    hata="Süre pozitif bir gün sayısı olmalıdır",
                    form=request.form,
                )

        # İG-14: Aynı özellik kümesi uyarısı
        onaylandı_mı = request.form.get("onaylandı_mı") == "1"
        if not onaylandı_mı:
            süre_koşulu = (Kalıp.süre_gün == süre_gün) if süre_gün is not None else Kalıp.süre_gün.is_(None)
            eşleşen_kalıp = db.session.execute(
                db.select(Kalıp).where(
                    db.or_(Kalıp.sistem_kalıbı_mı.is_(True), Kalıp.sahip_kimlik == kimlik),
                    Kalıp.kimlik != kalıp.kimlik,
                    Kalıp.açık_uçlu_izinli_mi == açık_uçlu_izinli_mi,
                    Kalıp.evet_hayır_izinli_mi == evet_hayır_izinli_mi,
                    Kalıp.ölçek_izinli_mi == ölçek_izinli_mi,
                    Kalıp.çoktan_seçmeli_izinli_mi == çoktan_seçmeli_izinli_mi,
                    Kalıp.anonim_mi == anonim_mi,
                    Kalıp.herkese_açık_mı == herkese_açık_mı,
                    süre_koşulu,
                )
            ).scalars().first()

            if eşleşen_kalıp:
                return render_template(
                    "kalip_duzenle.html",
                    kalıp=kalıp,
                    uyarı=f"Dikkat: Bu özellik kümesi '{eşleşen_kalıp.ad}' adlı kalıp ile birebir aynıdır. Yine de güncellemek istiyorsanız 'Güncelle' butonuna tekrar tıklayınız.",
                    form=request.form,
                    onay_gerekiyor=True,
                )

        kalıp.ad = ad
        kalıp.açık_uçlu_izinli_mi = açık_uçlu_izinli_mi
        kalıp.evet_hayır_izinli_mi = evet_hayır_izinli_mi
        kalıp.ölçek_izinli_mi = ölçek_izinli_mi
        kalıp.çoktan_seçmeli_izinli_mi = çoktan_seçmeli_izinli_mi
        kalıp.anonim_mi = anonim_mi
        kalıp.herkese_açık_mı = herkese_açık_mı
        kalıp.süre_gün = süre_gün

        db.session.commit()
        return redirect(url_for("kalıp_listesi"))

    return render_template("kalip_duzenle.html", kalıp=kalıp)


@uygulama.route("/kalip/<int:kalip_kimlik>/sil", methods=["POST"])
def kalıp_silme(kalip_kimlik):
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    kalıp = db.session.get(Kalıp, kalip_kimlik)
    if not kalıp:
        abort(404)

    # İG-13: Sistem kalıbı silinemez, yalnızca sahip silebilir
    if kalıp.sistem_kalıbı_mı or kalıp.sahip_kimlik != kimlik:
        abort(403)

    db.session.delete(kalıp)
    db.session.commit()
    return redirect(url_for("kalıp_listesi"))


@uygulama.route("/anket/yeni", methods=["GET", "POST"])
def anket_oluşturma():
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    kalıplar = db.session.execute(
        db.select(Kalıp).where(
            db.or_(Kalıp.sistem_kalıbı_mı.is_(True), Kalıp.sahip_kimlik == kimlik)
        ).order_by(Kalıp.ad)
    ).scalars().all()

    seçilen_kalıp_kimlik = None
    kalıp_kimlik_parametresi = request.args.get("kalip_kimlik")
    if kalıp_kimlik_parametresi:
        try:
            seçilen_kalıp_kimlik = int(kalıp_kimlik_parametresi)
        except (ValueError, TypeError):
            pass

    seçilen_kalıp = None
    if seçilen_kalıp_kimlik:
        seçilen_kalıp = next((k for k in kalıplar if k.kimlik == seçilen_kalıp_kimlik), None)

    if request.method == "POST":
        başlık = request.form.get("başlık", "").strip()
        açıklama = request.form.get("açıklama", "")
        if not başlık:
            return render_template(
                "anket_yeni.html",
                hata="Başlık boş bırakılamaz",
                kalıplar=kalıplar,
                seçilen_kalıp_kimlik=seçilen_kalıp_kimlik,
                seçilen_kalıp=seçilen_kalıp,
            )

        kalıp_seçimi = request.form.get("kalıp_kimlik", "").strip()
        kalıp = None
        if kalıp_seçimi:
            try:
                kalıp_kimliği = int(kalıp_seçimi)
                kalıp = next((k for k in kalıplar if k.kimlik == kalıp_kimliği), None)
            except (ValueError, TypeError):
                pass

        if kalıp:
            # İG-18: Kalıp kuralları ankete kopyalanır, bağ kalmaz
            anket = Anket(
                başlık=başlık,
                açıklama=açıklama,
                sahip_kimlik=kimlik,
                anonim_mi=kalıp.anonim_mi,
                herkese_açık_mı=kalıp.herkese_açık_mı,
                açık_uçlu_izinli_mi=kalıp.açık_uçlu_izinli_mi,
                evet_hayır_izinli_mi=kalıp.evet_hayır_izinli_mi,
                ölçek_izinli_mi=kalıp.ölçek_izinli_mi,
                çoktan_seçmeli_izinli_mi=kalıp.çoktan_seçmeli_izinli_mi,
                süre_gün=kalıp.süre_gün,
            )
        else:
            anonim_mi = "anonim_mi" in request.form
            herkese_açık_mı = "herkese_açık_mı" in request.form
            anket = Anket(
                başlık=başlık,
                açıklama=açıklama,
                anonim_mi=anonim_mi,
                herkese_açık_mı=herkese_açık_mı,
                sahip_kimlik=kimlik,
            )

        db.session.add(anket)
        db.session.commit()
        return redirect(url_for("ana_sayfa"))

    return render_template(
        "anket_yeni.html",
        kalıplar=kalıplar,
        seçilen_kalıp_kimlik=seçilen_kalıp_kimlik,
        seçilen_kalıp=seçilen_kalıp,
    )


@uygulama.route("/anket/<int:anket_kimlik>/kalip-turet", methods=["GET", "POST"])
def anketten_kalıp_türetme(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "sahip")
    kimlik = session.get("kullanıcı_kimlik")

    # İG-15: Sorusuz ankette soru tipi bulunmadığından kalıp türetme engellenir
    if not anket.sorular:
        return anket_duzenle_goster(anket, hata="Soru içermeyen anketten kalıp türetilemez")

    # Ankette kullanılan soru tipleri çıkarılır, kalıp yalnızca o tiplere izin verir
    kullanılan_tipler = {s.tip for s in anket.sorular}
    açık_uçlu_izinli_mi = "açık uçlu" in kullanılan_tipler
    evet_hayır_izinli_mi = "evet/hayır" in kullanılan_tipler
    ölçek_izinli_mi = "ölçek" in kullanılan_tipler
    çoktan_seçmeli_izinli_mi = "çoktan seçmeli" in kullanılan_tipler

    anonim_mi = anket.anonim_mi
    herkese_açık_mı = anket.herkese_açık_mı
    süre_gün = anket.süre_gün

    kurallar = {
        "açık_uçlu_izinli_mi": açık_uçlu_izinli_mi,
        "evet_hayır_izinli_mi": evet_hayır_izinli_mi,
        "ölçek_izinli_mi": ölçek_izinli_mi,
        "çoktan_seçmeli_izinli_mi": çoktan_seçmeli_izinli_mi,
        "anonim_mi": anonim_mi,
        "herkese_açık_mı": herkese_açık_mı,
        "süre_gün": süre_gün,
    }


    varsayılan_ad = f"{anket.başlık} Kalıbı"

    if request.method == "POST":
        ad = request.form.get("ad", "").strip()
        if not ad:
            return render_template(
                "anket_kalip_turet.html",
                anket=anket,
                kurallar=kurallar,
                varsayılan_ad=varsayılan_ad,
                hata="Kalıp adı boş bırakılamaz",
            )

        # 1. Sistem kalıbı adı ile çakışma denetimi
        sistemde_var = db.session.execute(
            db.select(Kalıp).where(Kalıp.sistem_kalıbı_mı.is_(True), Kalıp.ad == ad)
        ).scalar_one_or_none()
        if sistemde_var:
            return render_template(
                "anket_kalip_turet.html",
                anket=anket,
                kurallar=kurallar,
                varsayılan_ad=ad,
                hata="Sistem kalıbı ile aynı ada sahip kalıp oluşturulamaz",
            )

        # 2. Kullanıcıda tekillik denetimi
        kullanıcıda_var = db.session.execute(
            db.select(Kalıp).where(Kalıp.sahip_kimlik == kimlik, Kalıp.ad == ad)
        ).scalar_one_or_none()
        if kullanıcıda_var:
            return render_template(
                "anket_kalip_turet.html",
                anket=anket,
                kurallar=kurallar,
                varsayılan_ad=ad,
                hata="Bu ada sahip bir kalıbınız zaten bulunmaktadır",
            )

        # 3. İG-14: Aynı özellik kümesi uyarısı
        onaylandı_mı = request.form.get("onaylandı_mı") == "1"
        if not onaylandı_mı:
            süre_koşulu = (Kalıp.süre_gün == süre_gün) if süre_gün is not None else Kalıp.süre_gün.is_(None)
            eşleşen_kalıp = db.session.execute(
                db.select(Kalıp).where(
                    db.or_(Kalıp.sistem_kalıbı_mı.is_(True), Kalıp.sahip_kimlik == kimlik),
                    Kalıp.açık_uçlu_izinli_mi == açık_uçlu_izinli_mi,
                    Kalıp.evet_hayır_izinli_mi == evet_hayır_izinli_mi,
                    Kalıp.ölçek_izinli_mi == ölçek_izinli_mi,
                    Kalıp.çoktan_seçmeli_izinli_mi == çoktan_seçmeli_izinli_mi,
                    Kalıp.anonim_mi == anonim_mi,
                    Kalıp.herkese_açık_mı == herkese_açık_mı,
                    süre_koşulu,
                )
            ).scalars().first()

            if eşleşen_kalıp:
                return render_template(
                    "anket_kalip_turet.html",
                    anket=anket,
                    kurallar=kurallar,
                    varsayılan_ad=ad,
                    uyarı=f"Dikkat: Bu özellik kümesi '{eşleşen_kalıp.ad}' adlı kalıp ile birebir aynıdır. Yine de kaydetmek istiyorsanız 'Kalıp Olarak Kaydet' butonuna tekrar tıklayınız.",
                    onay_gerekiyor=True,
                )

        yeni_kalıp = Kalıp(
            sahip_kimlik=kimlik,
            ad=ad,
            sistem_kalıbı_mı=False,
            açık_uçlu_izinli_mi=açık_uçlu_izinli_mi,
            evet_hayır_izinli_mi=evet_hayır_izinli_mi,
            ölçek_izinli_mi=ölçek_izinli_mi,
            çoktan_seçmeli_izinli_mi=çoktan_seçmeli_izinli_mi,
            anonim_mi=anonim_mi,
            herkese_açık_mı=herkese_açık_mı,
            süre_gün=süre_gün,
        )
        db.session.add(yeni_kalıp)
        db.session.commit()
        return redirect(url_for("kalıp_listesi"))

    return render_template(
        "anket_kalip_turet.html",
        anket=anket,
        kurallar=kurallar,
        varsayılan_ad=varsayılan_ad,
    )


@uygulama.route("/anket/<int:anket_kimlik>/duzenle")
def anket_duzenle(anket_kimlik):
    anket = anketi_getir(anket_kimlik)
    return anket_duzenle_goster(anket)

@uygulama.route("/anket/<int:anket_kimlik>/ayarlar", methods=["GET", "POST"])
def anket_ayarları(anket_kimlik):
    anket = anketi_getir(anket_kimlik, ("içerik_düzenleme_mi", "yayın_yönetimi_mi"))
    kimlik = session.get("kullanıcı_kimlik")
    sahip_mi = (anket.sahip_kimlik == kimlik)
    yetki = yetkiyi_getir(anket, kimlik)

    içerik_yetkisi = sahip_mi or (yetki and (yetki.yöneticilik_mi or yetki.içerik_düzenleme_mi))
    yayın_yetkisi = sahip_mi or (yetki and (yetki.yöneticilik_mi or yetki.yayın_yönetimi_mi))

    if request.method == "POST":
        if not yayın_yetkisi and any(k in request.form for k in ("herkese_açık_mı", "anonim_mi", "süre_tipi", "son_tarih", "süre_gün", "değerlendirilebilir_mi", "değerlendirme_alt_sınırı", "değerlendirme_üst_sınırı")):
            return render_template(
                "anket_ayarlar.html",
                anket=anket,
                hata="Erişim politikası ve süre ayarlarını değiştirme yetkiniz yoktur",
                içerik_yetkisi=içerik_yetkisi,
                yayın_yetkisi=yayın_yetkisi,
                sahip_mi=sahip_mi,
            )

        if not içerik_yetkisi and any(k in request.form for k in ("başlık", "açıklama", "açık_uçlu_izinli_mi", "evet_hayır_izinli_mi", "ölçek_izinli_mi", "çoktan_seçmeli_izinli_mi")):
            return render_template(
                "anket_ayarlar.html",
                anket=anket,
                hata="İçerik ayarlarını değiştirme yetkiniz yoktur",
                içerik_yetkisi=içerik_yetkisi,
                yayın_yetkisi=yayın_yetkisi,
                sahip_mi=sahip_mi,
            )

        if içerik_yetkisi:
            başlık = request.form.get("başlık", "").strip()
            if not başlık:
                return render_template("anket_ayarlar.html", anket=anket, hata="Başlık boş bırakılamaz",
                                       içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)
            anket.başlık = başlık
            anket.açıklama = request.form.get("açıklama", "")
            anket.açık_uçlu_izinli_mi = "açık_uçlu_izinli_mi" in request.form
            anket.evet_hayır_izinli_mi = "evet_hayır_izinli_mi" in request.form
            anket.ölçek_izinli_mi = "ölçek_izinli_mi" in request.form
            anket.çoktan_seçmeli_izinli_mi = "çoktan_seçmeli_izinli_mi" in request.form

        if yayın_yetkisi:
            anonim_mi = "anonim_mi" in request.form
            if anonim_mi != anket.anonim_mi:
                yanıt_var = db.session.execute(
                    db.select(db.func.count()).select_from(Yanıt).where(Yanıt.anket_kimlik == anket_kimlik)
                ).scalar() > 0
                if yanıt_var:
                    return render_template("anket_ayarlar.html", anket=anket, hata="Yanıt almış bir anketin anonimlik ayarı değiştirilemez",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)
                anket.anonim_mi = anonim_mi

            anket.herkese_açık_mı = "herkese_açık_mı" in request.form

            süre_tipi = request.form.get("süre_tipi", "süre_yok")
            if süre_tipi == "son_tarih":
                son_tarih_metni = request.form.get("son_tarih", "").strip()
                if not son_tarih_metni:
                    return render_template("anket_ayarlar.html", anket=anket, hata="Son tarih belirtilmelidir",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)
                try:
                    yeni_son_tarih = datetime.fromisoformat(son_tarih_metni)
                except ValueError:
                    return render_template("anket_ayarlar.html", anket=anket, hata="Geçersiz tarih formatı",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)
                if yeni_son_tarih <= datetime.now():
                    return render_template("anket_ayarlar.html", anket=anket, hata="Son tarih gelecekte bir zaman olmalıdır",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)
                anket.son_tarih = yeni_son_tarih
                anket.süre_gün = None
            elif süre_tipi == "süre_gün":
                süre_gün_metni = request.form.get("süre_gün", "").strip()
                try:
                    yeni_süre_gün = int(süre_gün_metni)
                    if yeni_süre_gün <= 0:
                        raise ValueError()
                except (ValueError, TypeError):
                    return render_template("anket_ayarlar.html", anket=anket, hata="Süre pozitif bir gün sayısı olmalıdır",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)
                anket.süre_gün = yeni_süre_gün
            else:
                anket.son_tarih = None
                anket.süre_gün = None

            # İG-22 / İG-58: Değerlendirme puanı ayarları
            değerlendirilebilir_mi = "değerlendirilebilir_mi" in request.form
            if değerlendirilebilir_mi:
                alt_metni = request.form.get("değerlendirme_alt_sınırı", "").strip()
                üst_metni = request.form.get("değerlendirme_üst_sınırı", "").strip()
                try:
                    alt_sınır = int(alt_metni) if alt_metni else 0
                    üst_sınır = int(üst_metni) if üst_metni else 10
                except (ValueError, TypeError):
                    return render_template("anket_ayarlar.html", anket=anket, hata="Geçersiz değerlendirme puanı sınırı",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)

                if alt_sınır < -5:
                    return render_template("anket_ayarlar.html", anket=anket, hata="Alt sınır -5'ten küçük olamaz",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)
                if üst_sınır > 10:
                    return render_template("anket_ayarlar.html", anket=anket, hata="Üst sınır 10'dan büyük olamaz",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)
                if alt_sınır >= üst_sınır:
                    return render_template("anket_ayarlar.html", anket=anket, hata="Alt sınır üst sınırdan küçük olmalıdır",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)
                if (üst_sınır - alt_sınır) > 10:
                    return render_template("anket_ayarlar.html", anket=anket, hata="Aralık genişliği 10'u aşamaz",
                                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)

                anket.değerlendirilebilir_mi = True
                anket.değerlendirme_alt_sınırı = alt_sınır
                anket.değerlendirme_üst_sınırı = üst_sınır
            else:
                anket.değerlendirilebilir_mi = False

        db.session.commit()
        return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

    return render_template("anket_ayarlar.html", anket=anket,
                           içerik_yetkisi=içerik_yetkisi, yayın_yetkisi=yayın_yetkisi, sahip_mi=sahip_mi)


@uygulama.route("/anket/<int:anket_kimlik>/soru/yeni", methods=["GET", "POST"])
def soru_ekleme(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "içerik_düzenleme_mi")
    if anket.yayında_mı:
        return anket_duzenle_goster(anket, hata="Yayındaki ankete soru eklenemez")
    if request.method == "POST":
        metin = request.form["metin"]
        tip = request.form["tip"]
        if tip not in TİP_İZİN_ALANI:
            return anket_duzenle_goster(anket, hata="Geçersiz soru tipi")
        if not getattr(anket, TİP_İZİN_ALANI[tip]):
            return anket_duzenle_goster(anket, hata="Bu soru tipine izin verilmiyor")
        zorunlu_mu = "zorunlu_mu" in request.form

        if not metin.strip():
            return anket_duzenle_goster(anket, hata="Metin boş bırakılamaz")

        ölçek_alt_sınırı = None
        ölçek_üst_sınırı = None
        if tip == "ölçek":
            alt_metni = request.form.get("ölçek_alt_sınırı", "").strip()
            üst_metni = request.form.get("ölçek_üst_sınırı", "").strip()

            try:
                ölçek_alt_sınırı = int(alt_metni) if alt_metni else 0
                ölçek_üst_sınırı = int(üst_metni) if üst_metni else 10
            except (ValueError, TypeError):
                return anket_duzenle_goster(anket, hata="Geçersiz ölçek sınırı")

            if ölçek_alt_sınırı < -5:
                return anket_duzenle_goster(anket, hata="Alt sınır -5'ten küçük olamaz")

            if ölçek_üst_sınırı > 10:
                return anket_duzenle_goster(anket, hata="Üst sınır 10'dan büyük olamaz")

            if ölçek_alt_sınırı >= ölçek_üst_sınırı:
                return anket_duzenle_goster(anket, hata="Alt sınır üst sınırdan küçük olmalıdır")

            if (ölçek_üst_sınırı - ölçek_alt_sınırı) > 10:
                return anket_duzenle_goster(anket, hata="Ölçek aralık genişliği 10'u aşamaz")

        seçenekler = []
        if tip == "çoktan seçmeli":
            seçenekler = [s.strip() for s in request.form.getlist("seçenek") if s.strip()]
            if len(seçenekler) < 2:
                return anket_duzenle_goster(anket, hata="Seçenek en az 2 olmalıdır")

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
    return anket_duzenle_goster(anket)

@uygulama.route("/anket/<int:anket_kimlik>/soru/<int:soru_kimlik>/sil", methods=["POST"])
def soru_silme(anket_kimlik, soru_kimlik):
    anket = anketi_getir(anket_kimlik, "içerik_düzenleme_mi")
    if anket.yayında_mı:
        return anket_duzenle_goster(anket, hata="Yayındaki anketin soruları silinemez")

    soru = db.session.get(Soru, soru_kimlik)
    if soru is None or soru.anket_kimlik != anket_kimlik:
        abort(404)

    db.session.delete(soru)
    kalan_sorular = [s for s in anket.sorular if s.kimlik != soru.kimlik]
    for yeni_sıra, s in enumerate(sorted(kalan_sorular, key=lambda x: x.sıra), start=1):
        s.sıra = yeni_sıra

    db.session.commit()
    return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))


@uygulama.route("/anket/<int:anket_kimlik>/soru/<int:soru_kimlik>/duzenle", methods=["GET", "POST"])
def soru_düzenleme(anket_kimlik, soru_kimlik):
    anket = anketi_getir(anket_kimlik, "içerik_düzenleme_mi")
    if anket.yayında_mı:
        return anket_duzenle_goster(anket, hata="Yayındaki anketin soruları düzenlenemez")

    soru = db.session.get(Soru, soru_kimlik)
    if soru is None or soru.anket_kimlik != anket_kimlik:
        abort(404)

    if request.method == "POST":
        metin = request.form.get("metin", "").strip()
        tip = request.form.get("tip")
        if tip not in TİP_İZİN_ALANI:
            return render_template("soru_duzenle.html", anket=anket, soru=soru, hata="Geçersiz soru tipi")
        if not getattr(anket, TİP_İZİN_ALANI[tip]):
            return render_template("soru_duzenle.html", anket=anket, soru=soru, hata="Bu soru tipine izin verilmiyor")
        zorunlu_mu = "zorunlu_mu" in request.form

        if not metin:
            return render_template("soru_duzenle.html", anket=anket, soru=soru, hata="Metin boş bırakılamaz")

        ölçek_alt_sınırı = None
        ölçek_üst_sınırı = None
        if tip == "ölçek":
            alt_metni = request.form.get("ölçek_alt_sınırı", "").strip()
            üst_metni = request.form.get("ölçek_üst_sınırı", "").strip()

            try:
                ölçek_alt_sınırı = int(alt_metni) if alt_metni else 0
                ölçek_üst_sınırı = int(üst_metni) if üst_metni else 10
            except (ValueError, TypeError):
                return render_template("soru_duzenle.html", anket=anket, soru=soru, hata="Geçersiz ölçek sınırı")

            if ölçek_alt_sınırı < -5:
                return render_template("soru_duzenle.html", anket=anket, soru=soru, hata="Alt sınır -5'ten küçük olamaz")

            if ölçek_üst_sınırı > 10:
                return render_template("soru_duzenle.html", anket=anket, soru=soru, hata="Üst sınır 10'dan büyük olamaz")

            if ölçek_alt_sınırı >= ölçek_üst_sınırı:
                return render_template("soru_duzenle.html", anket=anket, soru=soru, hata="Alt sınır üst sınırdan küçük olmalıdır")

            if (ölçek_üst_sınırı - ölçek_alt_sınırı) > 10:
                return render_template("soru_duzenle.html", anket=anket, soru=soru, hata="Ölçek aralık genişliği 10'u aşamaz")

        seçenekler = []
        if tip == "çoktan seçmeli":
            seçenekler = [s.strip() for s in request.form.getlist("seçenek") if s.strip()]
            if len(seçenekler) < 2:
                return render_template("soru_duzenle.html", anket=anket, soru=soru, hata="Seçenek en az 2 olmalıdır")

        # İG-25: Soru metni, soru tipi veya çoktan seçmeli sorunun seçenekleri değiştiğinde cevaplar silinir.
        # Sıra veya zorunluluk ayarının değişmesi cevapları etkilemez.
        eski_metin = soru.metin
        eski_tip = soru.tip
        eski_seçenekler = [s.metin for s in soru.seçenekler]

        cevapları_sil = False
        if eski_metin != metin:
            cevapları_sil = True
        elif eski_tip != tip:
            cevapları_sil = True
        elif tip == "çoktan seçmeli":
            if eski_seçenekler != seçenekler:
                cevapları_sil = True

        if cevapları_sil:
            db.session.execute(db.delete(Cevap).where(Cevap.soru_kimlik == soru.kimlik))
            db.session.flush()

        soru.metin = metin
        soru.tip = tip
        soru.zorunlu_mu = zorunlu_mu
        soru.ölçek_alt_sınırı = ölçek_alt_sınırı
        soru.ölçek_üst_sınırı = ölçek_üst_sınırı

        if tip == "çoktan seçmeli":
            if eski_seçenekler != seçenekler:
                soru.seçenekler.clear()
                for sıra, seçenek_metni in enumerate(seçenekler, start=1):
                    soru.seçenekler.append(Seçenek(metin=seçenek_metni, sıra=sıra))
        else:
            if soru.seçenekler:
                soru.seçenekler.clear()

        db.session.commit()
        return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

    return render_template("soru_duzenle.html", anket=anket, soru=soru)


@uygulama.route("/anket/<int:anket_kimlik>/soru/<int:soru_kimlik>/tasi", methods=["POST"])
def soru_sıralama(anket_kimlik, soru_kimlik):
    anket = anketi_getir(anket_kimlik, "içerik_düzenleme_mi")
    if anket.yayında_mı:
        return anket_duzenle_goster(anket, hata="Yayındaki anketin soru sırası değiştirilemez")

    soru = db.session.get(Soru, soru_kimlik)
    if soru is None or soru.anket_kimlik != anket_kimlik:
        abort(404)

    yön = request.form.get("yön")
    if yön not in ("yukarı", "aşağı"):
        return anket_duzenle_goster(anket, hata="Geçersiz taşıma yönü")

    sorular = sorted(anket.sorular, key=lambda s: (s.sıra, s.kimlik))
    konum = next((i for i, s in enumerate(sorular) if s.kimlik == soru.kimlik), None)

    if konum is not None:
        if yön == "yukarı" and konum > 0:
            sorular[konum], sorular[konum - 1] = sorular[konum - 1], sorular[konum]
            for i, s in enumerate(sorular, start=1):
                s.sıra = i
            db.session.commit()
        elif yön == "aşağı" and konum < len(sorular) - 1:
            sorular[konum], sorular[konum + 1] = sorular[konum + 1], sorular[konum]
            for i, s in enumerate(sorular, start=1):
                s.sıra = i
            db.session.commit()

    return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))


@uygulama.route("/anket/<int:anket_kimlik>/yayinla", methods=["POST"])
def anket_yayınlama(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "yayın_yönetimi_mi")
    if not anket.sorular:
        return anket_duzenle_goster(anket, hata="Boş anket yayınlanamaz")
    for soru in anket.sorular:
        alan = TİP_İZİN_ALANI.get(soru.tip)
        if alan and not getattr(anket, alan):
            return anket_duzenle_goster(anket, hata=f"İzinsiz tipte soru ({soru.tip}) içerdiği için anket yayınlanamaz")
    if anket.süre_gün:
        anket.son_tarih = datetime.now() + timedelta(days=anket.süre_gün)
    anket.yayında_mı = True
    db.session.commit()

    return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

@uygulama.route("/anket/<int:anket_kimlik>/yayindan-al", methods=["POST"])
def anket_yayından_alma(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "yayın_yönetimi_mi")
    anket.yayında_mı = False
    db.session.commit()
    return redirect(url_for("anket_duzenle", anket_kimlik=anket_kimlik))

@uygulama.route("/anket/<int:anket_kimlik>/sil", methods=["POST"])
def anket_silme(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "sahip")

    db.session.delete(anket)
    db.session.commit()
    return redirect(url_for("ana_sayfa"))


@uygulama.route("/anket/<int:anket_kimlik>/uyeler", methods=["GET", "POST"])
def anket_üyeleri(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "yöneticilik_mi")
    kimlik = session.get("kullanıcı_kimlik")
    sahip_mi = (anket.sahip_kimlik == kimlik)

    if request.method == "POST":
        e_posta = request.form.get("e_posta", "").strip()
        if not e_posta:
            return render_template("anket_uyeler.html", anket=anket, üyelikler=anket.yetkiler, sahip_mi=sahip_mi, hata="E-posta adresi boş bırakılamaz")

        hedef_kullanıcı = db.session.execute(
            db.select(Kullanıcı).where(Kullanıcı.e_posta == e_posta)
        ).scalar_one_or_none()

        if not hedef_kullanıcı:
            return render_template("anket_uyeler.html", anket=anket, üyelikler=anket.yetkiler, sahip_mi=sahip_mi, hata="Bu e-posta adresine sahip kullanıcı bulunamadı")

        if hedef_kullanıcı.kimlik == anket.sahip_kimlik:
            return render_template("anket_uyeler.html", anket=anket, üyelikler=anket.yetkiler, sahip_mi=sahip_mi, hata="Anket sahibi üye olarak eklenemez")

        if hedef_kullanıcı.kimlik == kimlik:
            return render_template("anket_uyeler.html", anket=anket, üyelikler=anket.yetkiler, sahip_mi=sahip_mi, hata="Kendi yetkilerinizi değiştiremezsiniz")

        içerik_düzenleme_mi = "içerik_düzenleme_mi" in request.form
        yayın_yönetimi_mi = "yayın_yönetimi_mi" in request.form
        yanıtları_görme_mi = "yanıtları_görme_mi" in request.form
        kullanıcı_tanımlama_mı = "kullanıcı_tanımlama_mı" in request.form
        # Yöneticilik iznini yalnızca birincil sahip verebilir
        yöneticilik_mi = ("yöneticilik_mi" in request.form) if sahip_mi else False

        mevcut_yetki = yetkiyi_getir(anket, hedef_kullanıcı.kimlik)

        if mevcut_yetki:
            mevcut_yetki.içerik_düzenleme_mi = içerik_düzenleme_mi
            mevcut_yetki.yayın_yönetimi_mi = yayın_yönetimi_mi
            mevcut_yetki.yanıtları_görme_mi = yanıtları_görme_mi
            mevcut_yetki.kullanıcı_tanımlama_mı = kullanıcı_tanımlama_mı
            if sahip_mi:
                mevcut_yetki.yöneticilik_mi = yöneticilik_mi
            else:
                mevcut_yetki.yöneticilik_mi = False
        else:
            yeni_yetki = AnketYetki(
                anket_kimlik=anket_kimlik,
                kullanıcı_kimlik=hedef_kullanıcı.kimlik,
                içerik_düzenleme_mi=içerik_düzenleme_mi,
                yayın_yönetimi_mi=yayın_yönetimi_mi,
                yanıtları_görme_mi=yanıtları_görme_mi,
                kullanıcı_tanımlama_mı=kullanıcı_tanımlama_mı,
                yöneticilik_mi=yöneticilik_mi,
            )
            db.session.add(yeni_yetki)

        db.session.commit()
        return redirect(url_for("anket_üyeleri", anket_kimlik=anket_kimlik))

    return render_template("anket_uyeler.html", anket=anket, üyelikler=anket.yetkiler, sahip_mi=sahip_mi)


@uygulama.route("/anket/<int:anket_kimlik>/uye/<int:kullanici_kimlik>/cikar", methods=["POST"])
def anket_üye_çıkarma(anket_kimlik, kullanici_kimlik):
    anket = db.session.get(Anket, anket_kimlik)
    if anket is None:
        abort(404)
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        abort(403)

    # Kendi üyeliğinden ayrılma durumu
    if kullanici_kimlik == kimlik:
        yetki = yetkiyi_getir(anket, kimlik)
        if not yetki:
            abort(404)
        db.session.delete(yetki)
        db.session.commit()
        return redirect(url_for("ana_sayfa"))

    # Başka bir üyeyi çıkarma (yöneticilik veya sahiplik gerekir)
    anket = anketi_getir(anket_kimlik, "yöneticilik_mi")
    if kullanici_kimlik == anket.sahip_kimlik:
        abort(403)

    yetki = yetkiyi_getir(anket, kullanici_kimlik)
    if not yetki:
        abort(404)

    db.session.delete(yetki)
    db.session.commit()
    return redirect(url_for("anket_üyeleri", anket_kimlik=anket_kimlik))


@uygulama.route("/anket/<int:anket_kimlik>/tanimlamalar", methods=["GET", "POST"])
def anket_tanımlamaları(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "kullanıcı_tanımlama_mı")

    if request.method == "POST":
        e_posta = request.form.get("e_posta", "").strip()
        if not e_posta:
            return render_template("anket_tanimlamalar.html", anket=anket, tanımlamalar=anket.tanımlamalar, hata="E-posta adresi boş bırakılamaz")

        hedef_kullanıcı = db.session.execute(
            db.select(Kullanıcı).where(Kullanıcı.e_posta == e_posta)
        ).scalar_one_or_none()

        if not hedef_kullanıcı:
            return render_template("anket_tanimlamalar.html", anket=anket, tanımlamalar=anket.tanımlamalar, hata="Bu e-posta adresine sahip kullanıcı bulunamadı")

        mevcut_tanımlama = db.session.execute(
            db.select(AnketTanımlama).where(
                AnketTanımlama.anket_kimlik == anket_kimlik,
                AnketTanımlama.kullanıcı_kimlik == hedef_kullanıcı.kimlik,
            )
        ).scalar_one_or_none()

        if mevcut_tanımlama:
            return render_template("anket_tanimlamalar.html", anket=anket, tanımlamalar=anket.tanımlamalar, hata="Bu kullanıcı zaten tanımlanmış")

        zorunlu_mu = "zorunlu_mu" in request.form
        yeni_tanımlama = AnketTanımlama(
            anket_kimlik=anket_kimlik,
            kullanıcı_kimlik=hedef_kullanıcı.kimlik,
            zorunlu_mu=zorunlu_mu,
        )
        db.session.add(yeni_tanımlama)
        db.session.commit()
        return redirect(url_for("anket_tanımlamaları", anket_kimlik=anket_kimlik))

    return render_template("anket_tanimlamalar.html", anket=anket, tanımlamalar=anket.tanımlamalar)


@uygulama.route("/anket/<int:anket_kimlik>/tanimlama/<int:kullanici_kimlik>/cikar", methods=["POST"])
def anket_tanımlama_çıkarma(anket_kimlik, kullanici_kimlik):
    anket = anketi_getir(anket_kimlik, "kullanıcı_tanımlama_mı")

    tanımlama = db.session.execute(
        db.select(AnketTanımlama).where(
            AnketTanımlama.anket_kimlik == anket_kimlik,
            AnketTanımlama.kullanıcı_kimlik == kullanici_kimlik,
        )
    ).scalar_one_or_none()
    if not tanımlama:
        abort(404)

    db.session.delete(tanımlama)
    db.session.commit()
    return redirect(url_for("anket_tanımlamaları", anket_kimlik=anket_kimlik))


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
        .where(
            Anket.yayında_mı.is_(True),
            db.or_(
                Anket.herkese_açık_mı.is_(True),
                Anket.kimlik.in_(
                    db.select(AnketTanımlama.anket_kimlik).where(AnketTanımlama.kullanıcı_kimlik == kimlik)
                )
            ),
            db.or_(Anket.son_tarih.is_(None), Anket.son_tarih > datetime.now())
        )
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

    if not anket.herkese_açık_mı:
        tanımlı = db.session.execute(
            db.select(AnketTanımlama).where(
                AnketTanımlama.anket_kimlik == anket_kimlik,
                AnketTanımlama.kullanıcı_kimlik == kimlik,
            )
        ).scalar_one_or_none()
        if not tanımlı:
            abort(403)

    # İG-47: Bekleyen zorunlu tanımlaması olan kullanıcı başka bir anketi yanıtlayamaz
    bekleyenler = bekleyen_zorunlu_tanımlama(kimlik)
    if bekleyenler and anket not in bekleyenler:
        anket_bilgisi = ", ".join(f"'{a.başlık}' (ID: {a.kimlik})" for a in bekleyenler)
        hata = f"Öncelikle tamamlamanız gereken zorunlu anketler bulunmaktadır: {anket_bilgisi}"
        return render_template("anket_yanitla.html", anket=anket, hata=hata, bekleyenler=bekleyenler), 403

    yanıt = db.session.execute(
        db.select(Yanıt).where(
            Yanıt.anket_kimlik == anket_kimlik,
            Yanıt.yanıtlayan_kimlik == kimlik,
        )
    ).scalar_one_or_none()
    if yanıt and yanıt.gönderildi_mi:
        if request.method == "POST":
            return render_template("anket_yanitla.html", anket=anket, hata="Gönderilmiş yanıt değiştirilemez")
        return redirect(url_for("yanıt_sayfası", anket_kimlik=anket_kimlik))

    if anket.son_tarih and anket.son_tarih < datetime.now():
        return render_template("anket_yanitla.html", anket=anket, hata="Bu anketin süresi dolmuştur")

    güncel_soru_imzası = ",".join(str(s.kimlik) for s in sorted(anket.sorular, key=lambda x: x.sıra))
    mevcut_cevaplar = {c.soru_kimlik: c for c in yanıt.cevaplar} if yanıt else {}

    # İG-55: Yarım kalan ankete yeniden girildiğinde soru kümesi değişmişse kullanıcı bilgilendirilir
    cevap_soru_kimlikleri = {c.soru_kimlik for c in yanıt.cevaplar} if yanıt else set()
    güncel_soru_kimlikleri = {s.kimlik for s in anket.sorular}
    uyarı = "Anketteki sorular değiştiği için daha önce verdiğiniz bazı cevaplar güncel anketle uyuşmuyor olabilir." if (cevap_soru_kimlikleri and (cevap_soru_kimlikleri - güncel_soru_kimlikleri)) else None

    if request.method == "POST":
        eylem = request.form.get("eylem")
        gönderim_mi = (eylem == "gönder")

        # İG-55 ve İG-56: Soru kümesi değişmişse kullanıcıyı uyarma ve işlemi reddetme
        form_soru_imzası = request.form.get("soru_imzası")
        if form_soru_imzası is not None and form_soru_imzası != güncel_soru_imzası:
            return render_template(
                "anket_yanitla.html",
                anket=anket,
                cevaplar=mevcut_cevaplar,
                soru_imzası=güncel_soru_imzası,
                hata="Anketin soru kümesi değiştiği için işleminiz tamamlanamadı. Lütfen soruları kontrol edip tekrar deneyiniz."
            )

        yeni_cevap_verileri = {}
        for soru in anket.sorular:
            değer = request.form.get("soru_" + str(soru.kimlik))

            if not değer or not değer.strip():
                # İG-54a: Zorunlu soru denetimi yalnızca gönderim anında çalışır, kaydetmede değil
                if gönderim_mi and soru.zorunlu_mu:
                    return render_template(
                        "anket_yanitla.html",
                        anket=anket,
                        cevaplar=mevcut_cevaplar,
                        soru_imzası=güncel_soru_imzası,
                        hata=f"'{soru.metin}' sorusu zorunludur"
                    )
                yeni_cevap_verileri[soru.kimlik] = None
                continue

            değer = değer.strip()
            veri = {}

            if soru.tip == "açık uçlu":
                veri["metin_değeri"] = değer
            elif soru.tip == "evet/hayır":
                veri["evet_hayır_değeri"] = (değer == "evet")
            elif soru.tip == "ölçek":
                try:
                    sayısal = int(değer)
                except ValueError:
                    return render_template(
                        "anket_yanitla.html",
                        anket=anket,
                        cevaplar=mevcut_cevaplar,
                        soru_imzası=güncel_soru_imzası,
                        hata=f"'{soru.metin}' için geçerli bir sayı giriniz"
                    )
                if (soru.ölçek_alt_sınırı is not None and sayısal < soru.ölçek_alt_sınırı) or \
                   (soru.ölçek_üst_sınırı is not None and sayısal > soru.ölçek_üst_sınırı):
                    return render_template(
                        "anket_yanitla.html",
                        anket=anket,
                        cevaplar=mevcut_cevaplar,
                        soru_imzası=güncel_soru_imzası,
                        hata=f"'{soru.metin}' için değer {soru.ölçek_alt_sınırı} ile {soru.ölçek_üst_sınırı} arasında olmalıdır"
                    )
                veri["sayısal_değer"] = sayısal
            elif soru.tip == "çoktan seçmeli":
                try:
                    seçilen_kimlik = int(değer)
                except ValueError:
                    return render_template(
                        "anket_yanitla.html",
                        anket=anket,
                        cevaplar=mevcut_cevaplar,
                        soru_imzası=güncel_soru_imzası,
                        hata="Geçersiz seçenek"
                    )
                if not any(seçenek.kimlik == seçilen_kimlik for seçenek in soru.seçenekler):
                    return render_template(
                        "anket_yanitla.html",
                        anket=anket,
                        cevaplar=mevcut_cevaplar,
                        soru_imzası=güncel_soru_imzası,
                        hata="Geçersiz seçenek"
                    )
                veri["seçilen_seçenek_kimlik"] = seçilen_kimlik

            yeni_cevap_verileri[soru.kimlik] = veri

        # İG-58: Değerlendirme puanı yalnızca gönderim_mi ise okunur ve yazılır
        değerlendirme_puanı_değeri = None
        if gönderim_mi and anket.değerlendirilebilir_mi:
            puan_metni = request.form.get("değerlendirme_puanı", "").strip()
            if puan_metni:
                try:
                    puan = int(puan_metni)
                except (ValueError, TypeError):
                    return render_template(
                        "anket_yanitla.html",
                        anket=anket,
                        cevaplar=mevcut_cevaplar,
                        soru_imzası=güncel_soru_imzası,
                        hata="Geçersiz değerlendirme puanı",
                    )
                alt = anket.değerlendirme_alt_sınırı if anket.değerlendirme_alt_sınırı is not None else 0
                üst = anket.değerlendirme_üst_sınırı if anket.değerlendirme_üst_sınırı is not None else 10
                if puan < alt or puan > üst:
                    return render_template(
                        "anket_yanitla.html",
                        anket=anket,
                        cevaplar=mevcut_cevaplar,
                        soru_imzası=güncel_soru_imzası,
                        hata=f"Değerlendirme puanı {alt} ile {üst} arasında olmalıdır",
                    )
                değerlendirme_puanı_değeri = puan

        # Tüm doğrulamalar başarılı, yanıt kaydı ve cevapları yaz
        if yanıt is None:
            yanıt = Yanıt(anket_kimlik=anket_kimlik, yanıtlayan_kimlik=kimlik, oluşturma_zamanı=datetime.now())
            db.session.add(yanıt)
            db.session.flush()

        for soru_kimlik, veri in yeni_cevap_verileri.items():
            if veri is None:
                if soru_kimlik in mevcut_cevaplar:
                    db.session.delete(mevcut_cevaplar[soru_kimlik])
            else:
                if soru_kimlik in mevcut_cevaplar:
                    c = mevcut_cevaplar[soru_kimlik]
                    c.metin_değeri = veri.get("metin_değeri")
                    c.sayısal_değer = veri.get("sayısal_değer")
                    c.evet_hayır_değeri = veri.get("evet_hayır_değeri")
                    c.seçilen_seçenek_kimlik = veri.get("seçilen_seçenek_kimlik")
                else:
                    c = Cevap(
                        soru_kimlik=soru_kimlik,
                        metin_değeri=veri.get("metin_değeri"),
                        sayısal_değer=veri.get("sayısal_değer"),
                        evet_hayır_değeri=veri.get("evet_hayır_değeri"),
                        seçilen_seçenek_kimlik=veri.get("seçilen_seçenek_kimlik"),
                    )
                    yanıt.cevaplar.append(c)

        if gönderim_mi:
            yanıt.gönderildi_mi = True
            yanıt.gönderim_zamanı = datetime.now()
            if anket.değerlendirilebilir_mi:
                yanıt.değerlendirme_puanı = değerlendirme_puanı_değeri

        db.session.commit()
        return redirect(url_for("yanıt_sayfası", anket_kimlik=anket_kimlik))

    return render_template(
        "anket_yanitla.html",
        anket=anket,
        cevaplar=mevcut_cevaplar,
        soru_imzası=güncel_soru_imzası,
        uyarı=uyarı,
    )

@uygulama.route("/anket/<int:anket_kimlik>/yanitim")
def yanıt_sayfası(anket_kimlik):
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    anket = db.session.get(Anket, anket_kimlik)
    if anket is None:
        abort(404)

    yanıt = db.session.execute(
        db.select(Yanıt).where(
            Yanıt.anket_kimlik == anket_kimlik,
            Yanıt.yanıtlayan_kimlik == kimlik,
        )
    ).scalar_one_or_none()
    if not yanıt:
        return redirect(url_for("anket_yanıtlama", anket_kimlik=anket_kimlik))

    cevaplar = {c.soru_kimlik: c for c in yanıt.cevaplar}
    return render_template("anket_yanitim.html", anket=anket, yanıt=yanıt, cevaplar=cevaplar)


@uygulama.route("/anket/<int:anket_kimlik>/yanit/sil", methods=["POST"])
def yanıt_silme(anket_kimlik):
    kimlik = session.get("kullanıcı_kimlik")
    if not kimlik:
        return redirect(url_for("giriş_ekranı"))

    yanıt = db.session.execute(
        db.select(Yanıt).where(
            Yanıt.anket_kimlik == anket_kimlik,
            Yanıt.yanıtlayan_kimlik == kimlik,
        )
    ).scalar_one_or_none()

    if not yanıt:
        abort(404)

    # İG-54: Yalnızca gönderilmemiş (taslak) yanıtlar silinebilir
    if yanıt.gönderildi_mi:
        abort(403)

    db.session.delete(yanıt)
    db.session.commit()
    return redirect(url_for("ana_sayfa"))


@uygulama.route("/anket/<int:anket_kimlik>/yanitlar")
def anket_yanıtları(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "yanıtları_görme_mi")

    # İG-54b, İG-62, İG-65: Numara, gönderilmiş yanıtların kayıt kimliğine göre sıralanmasından hesaplanır
    kimlik_sıralı_yanıtlar = db.session.execute(
        db.select(Yanıt).where(
            Yanıt.anket_kimlik == anket_kimlik,
            Yanıt.gönderildi_mi.is_(True),
        ).order_by(Yanıt.kimlik.asc())
    ).scalars().all()

    numaralar = {y.kimlik: sıra for sıra, y in enumerate(kimlik_sıralı_yanıtlar, start=1)}

    # İG-62a: Gönderim zamanına veya değerlendirme puanına göre sıralanabilir.
    # Anonim ankette gönderim zamanı gösterilmez ve o ölçüte göre sıralama sunulmaz.
    sıralama = (request.args.get("sıralama") or request.args.get("sirala") or "").strip().lower()

    if anket.anonim_mi:
        yanıtlayanlar = {y.kimlik: f"Anonim {numaralar[y.kimlik]}" for y in kimlik_sıralı_yanıtlar}
        if sıralama in ("puan", "değerlendirme_puanı", "puan_azalan"):
            yanıtlar = sorted(
                kimlik_sıralı_yanıtlar,
                key=lambda y: (y.değerlendirme_puanı is not None, y.değerlendirme_puanı if y.değerlendirme_puanı is not None else 0),
                reverse=True
            )
        elif sıralama == "puan_artan":
            yanıtlar = sorted(
                kimlik_sıralı_yanıtlar,
                key=lambda y: (y.değerlendirme_puanı is None, y.değerlendirme_puanı if y.değerlendirme_puanı is not None else 0, y.kimlik)
            )
        else:
            # Anonim ankette gönderim zamanı sıralaması sunulmaz; varsayılan numara (kimlik) sırasıdır
            yanıtlar = kimlik_sıralı_yanıtlar
    else:
        yanıtlayanlar = {
            y.kimlik: (y.yanıtlayan.e_posta if y.yanıtlayan else "Silinmiş kullanıcı")
            for y in kimlik_sıralı_yanıtlar
        }
        if sıralama in ("puan", "değerlendirme_puanı", "puan_azalan"):
            yanıtlar = sorted(
                kimlik_sıralı_yanıtlar,
                key=lambda y: (y.değerlendirme_puanı is not None, y.değerlendirme_puanı if y.değerlendirme_puanı is not None else 0),
                reverse=True
            )
        elif sıralama == "puan_artan":
            yanıtlar = sorted(
                kimlik_sıralı_yanıtlar,
                key=lambda y: (y.değerlendirme_puanı is None, y.değerlendirme_puanı if y.değerlendirme_puanı is not None else 0, y.kimlik)
            )
        else:
            # Normal ankette varsayılan: gönderim zamanı sırası
            yanıtlar = sorted(kimlik_sıralı_yanıtlar, key=lambda y: (y.gönderim_zamanı or datetime.min, y.kimlik))

    return render_template(
        "anket_yanitlar.html",
        anket=anket,
        yanıtlar=yanıtlar,
        yanıtlayanlar=yanıtlayanlar,
        numaralar=numaralar,
    )

@uygulama.route("/anket/<int:anket_kimlik>/ozet")
def anket_özeti(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "yanıtları_görme_mi")

    # İG-54b, İG-63: Yalnızca gönderilmiş yanıtlar özete dahil edilir
    yanıtlar = db.session.execute(
        db.select(Yanıt).where(
            Yanıt.anket_kimlik == anket_kimlik,
            Yanıt.gönderildi_mi.is_(True),
        )
    ).scalars().all()
    toplam_yanıt = len(yanıtlar)

    özetler = {}
    for soru in anket.sorular:
        cevaplar = [c for y in yanıtlar for c in y.cevaplar if c.soru_kimlik == soru.kimlik]

        if soru.tip == "açık uçlu":
            metinler = [c.metin_değeri for c in cevaplar if c.metin_değeri and c.metin_değeri.strip()]
            özetler[soru.kimlik] = {
                "cevap_sayısı": len(metinler),
                "boş_sayısı": toplam_yanıt - len(metinler),
                "metinler": metinler,
            }
        elif soru.tip == "evet/hayır":
            evet_sayısı = sum(1 for c in cevaplar if c.evet_hayır_değeri is True)
            hayır_sayısı = sum(1 for c in cevaplar if c.evet_hayır_değeri is False)
            cevap_sayısı = evet_sayısı + hayır_sayısı
            özetler[soru.kimlik] = {
                "cevap_sayısı": cevap_sayısı,
                "boş_sayısı": toplam_yanıt - cevap_sayısı,
                "evet_sayısı": evet_sayısı,
                "hayır_sayısı": hayır_sayısı,
                "evet_yüzde": round((evet_sayısı / toplam_yanıt) * 100, 1) if toplam_yanıt > 0 else 0,
                "hayır_yüzde": round((hayır_sayısı / toplam_yanıt) * 100, 1) if toplam_yanıt > 0 else 0,
            }
        elif soru.tip == "ölçek":
            değerler = [c.sayısal_değer for c in cevaplar if c.sayısal_değer is not None]
            ortalama = round(sum(değerler) / len(değerler), 2) if değerler else None
            alt_sınır = soru.ölçek_alt_sınırı if soru.ölçek_alt_sınırı is not None else 0
            üst_sınır = soru.ölçek_üst_sınırı if soru.ölçek_üst_sınırı is not None else 10
            dağılım = []
            for değer in range(alt_sınır, üst_sınır + 1):
                adet = değerler.count(değer)
                yüzde = round((adet / toplam_yanıt) * 100, 1) if toplam_yanıt > 0 else 0
                dağılım.append({"değer": değer, "adet": adet, "yüzde": yüzde})
            özetler[soru.kimlik] = {
                "cevap_sayısı": len(değerler),
                "boş_sayısı": toplam_yanıt - len(değerler),
                "ortalama": ortalama,
                "dağılım": dağılım,
            }
        elif soru.tip == "çoktan seçmeli":
            seçilenler = [c.seçilen_seçenek_kimlik for c in cevaplar if c.seçilen_seçenek_kimlik is not None]
            dağılım = []
            for seçenek in soru.seçenekler:
                adet = seçilenler.count(seçenek.kimlik)
                yüzde = round((adet / toplam_yanıt) * 100, 1) if toplam_yanıt > 0 else 0
                dağılım.append({"seçenek": seçenek, "adet": adet, "yüzde": yüzde})
            özetler[soru.kimlik] = {
                "cevap_sayısı": len(seçilenler),
                "boş_sayısı": toplam_yanıt - len(seçilenler),
                "dağılım": dağılım,
            }

    # İG-60, İG-63a: Değerlendirme puanı dağılımı, ortalaması ve puan vermeyenlerin oranı
    değerlendirme_özeti = None
    if anket.değerlendirilebilir_mi:
        puanlar = [y.değerlendirme_puanı for y in yanıtlar if y.değerlendirme_puanı is not None]
        puan_veren_sayısı = len(puanlar)
        puan_vermeyen_sayısı = toplam_yanıt - puan_veren_sayısı
        puan_vermeyen_oranı = round((puan_vermeyen_sayısı / toplam_yanıt) * 100, 1) if toplam_yanıt > 0 else 0
        ortalama = round(sum(puanlar) / puan_veren_sayısı, 2) if puan_veren_sayısı > 0 else None

        alt = anket.değerlendirme_alt_sınırı if anket.değerlendirme_alt_sınırı is not None else 0
        üst = anket.değerlendirme_üst_sınırı if anket.değerlendirme_üst_sınırı is not None else 10
        dağılım = []
        for değer in range(alt, üst + 1):
            adet = puanlar.count(değer)
            yüzde = round((adet / toplam_yanıt) * 100, 1) if toplam_yanıt > 0 else 0
            dağılım.append({"değer": değer, "adet": adet, "yüzde": yüzde})

        değerlendirme_özeti = {
            "puan_veren_sayısı": puan_veren_sayısı,
            "puan_vermeyen_sayısı": puan_vermeyen_sayısı,
            "puan_vermeyen_oranı": puan_vermeyen_oranı,
            "ortalama": ortalama,
            "dağılım": dağılım,
            "alt_sınır": alt,
            "üst_sınır": üst,
        }

    kimlik = session.get("kullanıcı_kimlik")
    sahip_mi = (anket.sahip_kimlik == kimlik)

    return render_template(
        "anket_ozet.html",
        anket=anket,
        toplam_yanıt=toplam_yanıt,
        özetler=özetler,
        değerlendirme_özeti=değerlendirme_özeti,
        sahip_mi=sahip_mi,
    )


@uygulama.route("/anket/<int:anket_kimlik>/puanlari-sil", methods=["POST"])
def puanları_silme(anket_kimlik):
    anket = anketi_getir(anket_kimlik, "sahip")
    for y in anket.yanıtlar:
        y.değerlendirme_puanı = None
    db.session.commit()
    return redirect(url_for("anket_özeti", anket_kimlik=anket_kimlik))

uygulama.add_url_rule("/anket/<int:anket_kimlik>/puanlari-sil", endpoint="değerlendirme_puanlarını_silme", view_func=puanları_silme, methods=["POST"])
değerlendirme_puanlarını_silme = puanları_silme