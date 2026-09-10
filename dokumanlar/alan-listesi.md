#kullanıcı
#   kimlik (int, PK)
#   e_posta (string, UK)
#   parola_özeti (string(255))
#   oluşturma_zamanı (datetime)

#anket
#   kimlik (int, PK)
#   sahip_kimlik (int, FK -> kullanici.kimlik)
#   başlık (string)
#   açıklama (string, boş olabilir)
#   anonim_mi (boolean)
#   yayında_mı (boolean)
#   oluşturma_zamanı (datetime)

#soru
#   kimlik (int, PK)
#   anket_kimlik (int, FK -> anket.kimlik)
#   metin (string)
#   tip (string)
#   sıra (int)
#   zorunlu_mu (boolean)
#   ölçek_üst_sınırı (int, boş olabilir)

#seçenek
#   kimlik (int, PK)
#   soru_kimlik (int, FK -> soru.kimlik)
#   metin (string)
#   sıra (int)

#yanıt
#   kimlik (int, PK)
#   anket_kimlik (int, FK -> anket.kimlik)
#   yanıtlayan_kimlik (int, FK -> kullanici.kimlik)
#   oluşturma_zamanı (datetime)
#   değerlendirme_puanı (int, boş olabilir)
#   UK: anket_kimlik + yanıtlayan_kimlik

#cevap
#   kimlik (int, PK)
#   yanıt_kimlik (int, FK -> yanıt.kimlik)
#   soru_kimlik (int, FK -> soru.kimlik)
#   metin_değeri (string, boş olabilir)
#   sayısal_değer (int, boş olabilir)
#   evet_hayır_değeri (boolean, boş olabilir)
#   seçilen_seçenek_kimlik (int, FK -> seçenek.kimlik, boş olabilir)
#   UK: yanıt_kimlik + soru_kimlik
