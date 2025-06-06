import pymysql
import os
from werkzeug.utils import secure_filename
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, DateField
from wtforms.validators import DataRequired
from werkzeug.utils import secure_filename
from datetime import datetime
from flask import request, flash, redirect, url_for, session, current_app
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import boto3
import os
from dotenv import load_dotenv
load_dotenv()

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'jpg', 'jpeg', 'png', 'gif', 'bmp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app = Flask(__name__)
app.secret_key = 'your_secret_key'


# Konfigurasi database
def get_db_connection():
    return pymysql.connect(
        host=os.getenv('RDS_HOST'),
        user=os.getenv('RDS_USER'),
        password=os.getenv('RDS_PASS'),
        db=os.getenv('RDS_DB'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


def upload_file_to_s3(file, filename):
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('S3_REGION')
    bucket = os.getenv('S3_BUCKET_NAME')
    cdn_domain = os.getenv('CDN_DOMAIN')  # ✅ ambil dari .env

    if not all([access_key, secret_key, region, bucket, cdn_domain]):
        raise Exception("❌ AWS credentials or config missing!")

    print("AWS_ACCESS_KEY_ID:", access_key)
    print("S3_BUCKET_NAME:", bucket)
    print("CDN_DOMAIN:", cdn_domain)

    s3 = boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )

    s3.upload_fileobj(file, bucket, filename)

    # ✅ Gunakan CloudFront URL
    return f"https://{cdn_domain}/{filename}"




# Fungsi bantu untuk simpan file dan beri nama unik
def save_file_to_s3(file, folder_name=''):
    if file and file.filename:
        filename = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4()}_{filename}"

        # Gabungkan folder jika diberikan
        if folder_name:
            s3_filename = f"{folder_name}/{unique_name}"
        else:
            s3_filename = unique_name

        return upload_file_to_s3(file, s3_filename)
    return None

def delete_file_from_s3(file_url):
    import boto3
    from urllib.parse import urlparse
    import os

    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('S3_REGION')
    bucket_name = os.getenv('S3_BUCKET_NAME')

    if not all([access_key, secret_key, region, bucket_name]):
        raise Exception("❌ AWS credentials or config missing!")

    s3 = boto3.client('s3',
                      aws_access_key_id=access_key,
                      aws_secret_access_key=secret_key,
                      region_name=region)

    parsed_url = urlparse(file_url)
    file_key = parsed_url.path.lstrip('/')  # hapus "/" paling depan

    try:
        s3.delete_object(Bucket=bucket_name, Key=file_key)
    except Exception as e:
        print(f"Gagal menghapus file dari S3: {e}")



@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        conn = get_db_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Cek user berdasarkan email
                sql_user = "SELECT * FROM users WHERE email = %s"
                cursor.execute(sql_user, (email,))
                user = cursor.fetchone()

                if user and check_password_hash(user['password'], password):
                    if user['status_akun'] == 'approved':
                        session['user_id'] = user['user_id']
                        session['email'] = user['email']
                        session['nama_lengkap'] = user['nama_lengkap']
                        session['role'] = 'user'
                        return redirect(url_for('dashboard'))
                    else:
                        error = 'Akun Anda belum diverifikasi oleh admin.'
                else:
                    # Jika tidak ditemukan di users, cek admins
                    sql_admin = "SELECT * FROM admins WHERE email = %s"
                    cursor.execute(sql_admin, (email,))
                    admin = cursor.fetchone()

                    if admin and check_password_hash(admin['password'], password):
                        session['admin_id'] = admin['admin_id']
                        session['email'] = admin['email']
                        session['nama'] = admin['nama']
                        session['role'] = 'admin'
                        return redirect(url_for('admin_dashboard'))
                    else:
                        error = 'Email atau password salah.'
        finally:
            conn.close()
    return render_template('login.html', error=error)


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    success = None

    if request.method == 'POST':
        # Ambil data dari form
        form_data = {field: request.form.get(field) for field in [
            'email', 'password', 'nama_lengkap', 'nik', 'tempat_lahir', 'tanggal_lahir', 'jenis_kelamin',
            'alamat_jalan', 'rt_rw', 'desa', 'kecamatan', 'kabupaten', 'provinsi', 'agama',
            'status_perkawinan', 'pekerjaan'
        ]}

        # Ambil file dari form
        foto_profil = request.files.get('foto_profil')
        foto_ktp = request.files.get('foto_ktp')
        foto_kk = request.files.get('foto_kk')

        # Upload ke S3
# Upload ke S3 dengan folder khusus
        profil_url = save_file_to_s3(foto_profil, folder_name='profile/foto_profil')
        ktp_url = save_file_to_s3(foto_ktp, folder_name='profile/ktp')
        kk_url = save_file_to_s3(foto_kk, folder_name='profile/kk')


        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO users (
                    email, password, nama_lengkap, nik, tempat_lahir, tanggal_lahir, jenis_kelamin,
                    alamat_jalan, rt_rw, desa, kecamatan, kabupaten, provinsi, agama, status_perkawinan,
                    pekerjaan, foto_profil, foto_ktp, foto_kk, status_akun, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """
                now = datetime.now()
                cursor.execute(sql, (
                    form_data['email'], generate_password_hash(form_data['password']), form_data['nama_lengkap'], form_data['nik'],
                    form_data['tempat_lahir'], form_data['tanggal_lahir'], form_data['jenis_kelamin'],
                    form_data['alamat_jalan'], form_data['rt_rw'], form_data['desa'], form_data['kecamatan'],
                    form_data['kabupaten'], form_data['provinsi'], form_data['agama'], form_data['status_perkawinan'],
                    form_data['pekerjaan'], profil_url, ktp_url, kk_url,
                    'pending', now, now
                ))
                conn.commit()
                success = "Pendaftaran berhasil! Menunggu verifikasi admin."
        except Exception as e:
            conn.rollback()
            error = f"Gagal mendaftar: {str(e)}"
        finally:
            conn.close()

    return render_template('register.html', error=error, success=success)


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor: 
            # Ambil data pengumuman
            cursor.execute("SELECT * FROM pengumuman ORDER BY created_at DESC")
            pengumuman = cursor.fetchall()

            # Ambil data user (termasuk foto_profil)
            cursor.execute("SELECT nama_lengkap, email, foto_profil FROM users WHERE user_id = %s", (session['user_id'],))
            user = cursor.fetchone()

    finally:
        conn.close()

    return render_template('dashboard.html', pengumuman=pengumuman, user=user)

@app.route('/pengajuan-surat', methods=['GET', 'POST'])
@app.route('/pengajuan-surat/<int:pengajuan_id>', methods=['GET', 'POST'])
def pengajuan_surat(pengajuan_id=None):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    daftar_pengajuan, jenis_surat, kategori_surat, pengajuan = [], [], [], None

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT nama_lengkap, email, foto_profil FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()

            if request.method == 'POST':
                data = {k: request.form.get(k) for k in [
                    'pengajuan_id', 'kategori_id', 'jenis_surat_id', 'nama_pemohon', 'nik_pemohon',
                    'tempat_lahir', 'tanggal_lahir', 'alamat_lengkap', 'jenis_kelamin', 'agama',
                    'status_perkawinan', 'kewarganegaraan', 'no_kk', 'pekerjaan', 'instansi', 'keperluan'
                ]}

                lampiran = request.files.get('lampiran')
                lampiran_url = save_file_to_s3(lampiran) if lampiran else None

                id_ = data.get('pengajuan_id') or pengajuan_id
                if id_:
                    cursor.execute('SELECT created_at FROM pengajuan_surat WHERE pengajuan_id=%s AND user_id=%s', (id_, user_id))
                    row = cursor.fetchone()
                    if row and (datetime.now() - row['created_at']) <= timedelta(minutes=30):
                        query = '''UPDATE pengajuan_surat SET kategori_id=%s, jenis_surat_id=%s, nama_pemohon=%s, nik_pemohon=%s,
                            tempat_lahir=%s, tanggal_lahir=%s, alamat_lengkap=%s, jenis_kelamin=%s, agama=%s, status_perkawinan=%s,
                            kewarganegaraan=%s, no_kk=%s, pekerjaan=%s, instansi=%s, keperluan=%s, updated_at=NOW()'''
                        params = [
                            data['kategori_id'], data['jenis_surat_id'], data['nama_pemohon'], data['nik_pemohon'],
                            data['tempat_lahir'], data['tanggal_lahir'], data['alamat_lengkap'], data['jenis_kelamin'],
                            data['agama'], data['status_perkawinan'], data['kewarganegaraan'], data['no_kk'],
                            data['pekerjaan'], data['instansi'], data['keperluan']
                        ]
                        if lampiran_url:
                            query += ", lampiran_url=%s"
                            params.append(lampiran_url)

                        query += " WHERE pengajuan_id=%s AND user_id=%s"
                        params += [id_, user_id]
                        cursor.execute(query, tuple(params))
                        flash('Pengajuan berhasil diperbarui.', 'success')
                    else:
                        flash('Tidak bisa edit, pengajuan tidak ditemukan atau lewat 30 menit.', 'danger')
                else:
                    cursor.execute('''INSERT INTO pengajuan_surat (
                        user_id, kategori_id, jenis_surat_id, nama_pemohon, nik_pemohon,
                        tempat_lahir, tanggal_lahir, alamat_lengkap, jenis_kelamin, agama,
                        status_perkawinan, kewarganegaraan, no_kk, pekerjaan, instansi,
                        keperluan, lampiran_url, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    )''', (
                        user_id, data['kategori_id'], data['jenis_surat_id'], data['nama_pemohon'], data['nik_pemohon'],
                        data['tempat_lahir'], data['tanggal_lahir'], data['alamat_lengkap'], data['jenis_kelamin'],
                        data['agama'], data['status_perkawinan'], data['kewarganegaraan'], data['no_kk'],
                        data['pekerjaan'], data['instansi'], data['keperluan'], lampiran_url
                    ))

                    flash('Pengajuan baru berhasil dikirim.', 'success')

                conn.commit()
                return redirect(url_for('pengajuan_surat'))

            if pengajuan_id:
                cursor.execute('''SELECT ps.*, js.nama_jenis, ks.nama_kategori FROM pengajuan_surat ps 
                    JOIN jenis_surat js ON ps.jenis_surat_id=js.jenis_surat_id 
                    JOIN kategori_surat ks ON ps.kategori_id=ks.kategori_id 
                    WHERE ps.pengajuan_id=%s AND ps.user_id=%s''', (pengajuan_id, user_id))
                pengajuan = cursor.fetchone()
                if not pengajuan:
                    flash('Pengajuan tidak ditemukan.', 'danger')
                    return redirect(url_for('pengajuan_surat'))

                if (datetime.now() - pengajuan['created_at']) > timedelta(minutes=30):
                    flash('Pengajuan tidak bisa diedit karena sudah lewat 30 menit.', 'danger')
                    return redirect(url_for('pengajuan_surat'))

            cursor.execute('''SELECT ps.*, js.nama_jenis, ks.nama_kategori FROM pengajuan_surat ps 
                JOIN jenis_surat js ON ps.jenis_surat_id=js.jenis_surat_id 
                JOIN kategori_surat ks ON ps.kategori_id=ks.kategori_id 
                WHERE ps.user_id=%s ORDER BY ps.created_at DESC''', (user_id,))
            daftar_pengajuan = cursor.fetchall()

            cursor.execute('SELECT * FROM jenis_surat')
            jenis_surat = cursor.fetchall()

            cursor.execute('SELECT * FROM kategori_surat')
            kategori_surat = cursor.fetchall()

    except pymysql.MySQLError as e:
        conn.rollback()
        flash(f'Terjadi kesalahan database: {e}', 'danger')
    finally:
        conn.close()

    return render_template(
        'pengajuan_surat.html',
        daftar_pengajuan=daftar_pengajuan,
        jenis_surat=jenis_surat,
        kategori_surat=kategori_surat,
        pengajuan_edit=pengajuan,
        now=datetime.now(),
        user=user
    )



@app.route('/legalisir', methods=['GET', 'POST'])
def legalisir():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Ambil data user
            cursor.execute("SELECT nama_lengkap, email, foto_profil FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()

            if request.method == 'POST':
                nama_dokumen = request.form.get('nama_dokumen')
                keperluan = request.form.get('keperluan')
                jadwal_temu = request.form.get('jadwal_temu')
                jam_temu = request.form.get('jam_temu')
                file = request.files.get('file_dokumen')

                # Validasi file
                if not file or file.filename == '' or not allowed_file(file.filename):
                    flash('File dokumen harus diunggah dengan format yang diizinkan.', 'danger')
                    return redirect(url_for('legalisir'))

                # Validasi tanggal
                if not jadwal_temu:
                    flash('Tanggal jadwal temu harus diisi.', 'danger')
                    return redirect(url_for('legalisir'))
                try:
                    jadwal_temu_obj = datetime.strptime(jadwal_temu, '%Y-%m-%d').date()
                except ValueError:
                    flash('Format tanggal tidak valid. Gunakan format YYYY-MM-DD.', 'danger')
                    return redirect(url_for('legalisir'))

                # Validasi jam
                if not jam_temu:
                    flash('Jam temu harus diisi.', 'danger')
                    return redirect(url_for('legalisir'))
                try:
                    jam_temu_obj = datetime.strptime(jam_temu, '%H:%M').time()
                except ValueError:
                    flash('Format jam tidak valid. Gunakan format HH:MM (24 jam).', 'danger')
                    return redirect(url_for('legalisir'))

                # Upload file ke S3
                try:
                    file_url = save_file_to_s3(file, folder_name='legalisir')
                except Exception as e:
                    flash(f'Gagal mengupload file: {e}', 'danger')
                    return redirect(url_for('legalisir'))

                # Simpan ke database
                try:
                    cursor.execute("""INSERT INTO legalisir 
                        (user_id, nama_dokumen, keperluan, jadwal_temu, jam_temu, file_dokumen, status, created_at) 
                        VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())""",
                        (user_id, nama_dokumen, keperluan, jadwal_temu_obj, jam_temu_obj, file_url))
                    conn.commit()
                    flash('Pengajuan legalisir berhasil dikirim.', 'success')
                    return redirect(url_for('legalisir'))
                except Exception as e:
                    conn.rollback()
                    flash(f'Terjadi kesalahan saat mengirim pengajuan legalisir. Silakan coba lagi. {e}', 'danger')
                    return redirect(url_for('legalisir'))

            # Ambil daftar legalisir user (terbaru dulu)
            cursor.execute("""SELECT *, TIMESTAMPDIFF(MINUTE, created_at, NOW()) AS menit_selisih,
                CASE WHEN TIMESTAMPDIFF(MINUTE, created_at, NOW()) <= 30 THEN 1 ELSE 0 END AS can_edit
                FROM legalisir WHERE user_id = %s ORDER BY created_at DESC""", (user_id,))
            daftar_legalisir = cursor.fetchall()

    finally:
        conn.close()

    return render_template('legalisir.html', daftar_legalisir=daftar_legalisir, current_time=datetime.utcnow(), user=user)

@app.route('/pengaduan', methods=['GET', 'POST'])
def pengaduan():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT nama_lengkap, email, foto_profil FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()

            if request.method == 'POST':
                nama_pengadu = request.form.get('nama_pengadu')
                email_pengadu = request.form.get('email_pengadu')
                kategori = request.form.get('kategori')
                sub_kategori = request.form.get('sub_kategori')
                judul_pengaduan = request.form.get('judul_pengaduan')
                deskripsi = request.form.get('deskripsi')
                tanggal_kejadian = request.form.get('tanggal_kejadian')
                alamat = request.form.get('alamat')
                file = request.files.get('lampiran')
                lampiran_url = None

                # Validasi wajib semua field
                if not (nama_pengadu and email_pengadu and kategori and sub_kategori and judul_pengaduan and deskripsi and tanggal_kejadian and alamat):
                    flash('Semua field harus diisi.', 'danger')
                    return redirect(url_for('pengaduan'))

                # Upload file ke S3 jika ada file
                if file and file.filename != '':
                    try:
                        lampiran_url = save_file_to_s3(file, folder_name='pengaduan')
                    except Exception as e:
                        flash(f'Gagal mengunggah file lampiran: {str(e)}', 'danger')
                        return redirect(url_for('pengaduan'))

                try:
                    sql = """
                        INSERT INTO pengaduan 
                        (user_id, nama_pengadu, email_pengadu, kategori, sub_kategori, judul_pengaduan, deskripsi, tanggal_kejadian, alamat, lampiran, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'terkirim')
                    """
                    cursor.execute(sql, (
                        user_id,
                        nama_pengadu,
                        email_pengadu,
                        kategori,
                        sub_kategori,
                        judul_pengaduan,
                        deskripsi,
                        tanggal_kejadian,
                        alamat,
                        lampiran_url
                    ))
                    conn.commit()
                    flash('Pengaduan berhasil dikirim! Tim kami akan segera menindaklanjuti.', 'success')
                except Exception as e:
                    conn.rollback()
                    flash(f'Terjadi kesalahan saat mengirim pengaduan. Silakan coba lagi. {str(e)}', 'danger')
                return redirect(url_for('pengaduan'))

            cursor.execute('''
                SELECT * FROM pengaduan
                WHERE user_id = %s
                ORDER BY created_at ASC
            ''', (user_id,))
            daftar_pengaduan = cursor.fetchall()
    finally:
        conn.close()
    return render_template('pengaduan.html', daftar_pengaduan=daftar_pengaduan, user=user)



@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    conn = get_db_connection()

    daftar_feedback = []
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT nama_lengkap, email, foto_profil FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()

            if request.method == 'POST':
                email = request.form.get('email')
                kategori = request.form.get('kategori')
                sub_kategori = request.form.get('sub_kategori')
                penilaian = request.form.get('penilaian')
                komentar = request.form.get('komentar')

                if not email or not kategori or not penilaian:
                    flash('Email, kategori, dan penilaian wajib diisi.', 'warning')
                    return redirect(url_for('feedback'))

                try:
                    penilaian = int(penilaian)
                    if penilaian < 1 or penilaian > 5:
                        raise ValueError
                except (ValueError, TypeError):
                    flash('Penilaian harus berupa angka antara 1 sampai 5.', 'warning')
                    return redirect(url_for('feedback'))

                if kategori == 'Proses Pembuatan Surat' and not sub_kategori:
                    flash('Sub-Kategori wajib diisi untuk kategori Proses Pembuatan Surat.', 'warning')
                    return redirect(url_for('feedback'))

                uploaded_file = request.files.get('lampiran')
                lampiran_url = None
                if uploaded_file and uploaded_file.filename != '':
                    allowed_extensions = {'.jpg', '.jpeg', '.png', '.pdf', '.doc', '.docx'}
                    ext = os.path.splitext(uploaded_file.filename)[1].lower()
                    if ext not in allowed_extensions:
                        flash('Format file tidak didukung.', 'warning')
                        return redirect(url_for('feedback'))

                    try:
                        lampiran_url = save_file_to_s3(uploaded_file, folder_name='feedback')
                    except Exception as e:
                        flash(f'Gagal upload file: {str(e)}', 'danger')
                        return redirect(url_for('feedback'))

                sql = '''
                    INSERT INTO feedback (user_id, email, kategori, sub_kategori, penilaian, komentar, lampiran)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                '''
                cursor.execute(sql, (user_id, email, kategori, sub_kategori, penilaian, komentar, lampiran_url))
                conn.commit()

                flash('Feedback berhasil dikirim!', 'success')
                return redirect(url_for('feedback'))

            cursor.execute('''
                SELECT * FROM feedback
                WHERE user_id = %s
                ORDER BY created_at ASC
            ''', (user_id,))
            daftar_feedback = cursor.fetchall()
    finally:
        conn.close()

    return render_template('feedback.html', daftar_feedback=daftar_feedback, user=user)



@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:

            if request.method == 'POST':
                f = request.form.get
                email = f('email')
                password = f('password')
                nama_lengkap = f('nama_lengkap')
                nik = f('nik')
                tempat_lahir = f('tempat_lahir')
                tanggal_lahir = f('tanggal_lahir')
                jenis_kelamin = f('jenis_kelamin')
                alamat_jalan = f('alamat_jalan')
                rt_rw = f('rt_rw')
                desa = f('desa')
                kecamatan = f('kecamatan')
                kabupaten = f('kabupaten')
                provinsi = f('provinsi')
                agama = f('agama')
                status_perkawinan = f('status_perkawinan')
                pekerjaan = f('pekerjaan')

                # Fungsi simpan ke S3
                def simpan_file_s3(field, folder_name):
                    file = request.files.get(field)
                    if file and file.filename:
                        return save_file_to_s3(file, folder_name=f'profile/{folder_name}')
                    return None

                # Upload ke S3
                foto_profil = simpan_file_s3('foto_profil', 'foto_profil')
                foto_ktp = simpan_file_s3('foto_ktp', 'ktp')
                foto_kk = simpan_file_s3('foto_kk', 'kk')

                # Ambil data lama
                cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
                user_lama = cursor.fetchone()

                foto_profil = foto_profil or user_lama['foto_profil']
                foto_ktp = foto_ktp or user_lama['foto_ktp']
                foto_kk = foto_kk or user_lama['foto_kk']

                # Update data
                cursor.execute('''
                    UPDATE users SET 
                        email=%s, 
                        password=%s, 
                        nama_lengkap=%s, 
                        nik=%s,
                        tempat_lahir=%s, 
                        tanggal_lahir=%s, 
                        jenis_kelamin=%s, 
                        alamat_jalan=%s,
                        rt_rw=%s, 
                        desa=%s, 
                        kecamatan=%s, 
                        kabupaten=%s, 
                        provinsi=%s,
                        agama=%s, 
                        status_perkawinan=%s, 
                        pekerjaan=%s,
                        foto_profil=%s, 
                        foto_ktp=%s, 
                        foto_kk=%s 
                    WHERE user_id=%s
                ''', (
                    email, password, nama_lengkap, nik, tempat_lahir, tanggal_lahir,
                    jenis_kelamin, alamat_jalan, rt_rw, desa, kecamatan, kabupaten,
                    provinsi, agama, status_perkawinan, pekerjaan,
                    foto_profil, foto_ktp, foto_kk, user_id
                ))

                conn.commit()
                flash('Profil berhasil diperbarui.', 'success')

            # Ambil data user untuk ditampilkan
            cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
            user = cursor.fetchone()

    finally:
        conn.close()

    return render_template('profile.html', user=user)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ----------------------------------ADMIN---------------------------------------------------=---------------------------------------_______________----------
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Ambil data pengumuman
            cursor.execute("SELECT * FROM pengumuman ORDER BY created_at DESC")
            pengumuman = cursor.fetchall()

            # Ambil data admin dari tabel 'admins'
            cursor.execute("SELECT nama, email, foto_admin FROM admins WHERE admin_id = %s", (session['admin_id'],))
            admin = cursor.fetchone()

    finally:
        conn.close()

    return render_template('admin_dashboard.html', pengumuman=pengumuman, admin=admin)

# -------------------------------------------------------------------------------------------------------------------------
@app.route('/admin/pengumuman', methods=['GET', 'POST'])
def admin_pengumuman():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    admin_id = session['admin_id']
    conn = get_db_connection()

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Ambil data pengumuman
            cursor.execute("SELECT * FROM pengumuman ORDER BY created_at DESC")
            pengumuman = cursor.fetchall()

            # Ambil data admin sesuai session
            cursor.execute("SELECT nama, foto_admin FROM admins WHERE admin_id = %s", (admin_id,))
            admin = cursor.fetchone()

            if not admin:
                flash("Admin tidak ditemukan, silakan login ulang.", "danger")
                return redirect(url_for('login'))

    finally:
        conn.close()

    return render_template(
        'admin_pengumuman.html',
        pengumuman=pengumuman,
        admin=admin,
        action=None,
        data=None
    )


def allowed_file(filename):
    # Terima semua file yang memiliki ekstensi
    return '.' in filename and filename.rsplit('.', 1)[1] != ''


@app.route('/admin/pengumuman/tambah', methods=['POST'])
def admin_pengumuman_tambah():
    judul = request.form['judul']
    isi = request.form['isi']
    admin_id = session.get('admin_id', 1)

    uploaded_file = request.files.get('file_lampiran')
    filename_db = None

    if uploaded_file and uploaded_file.filename != '':
        try:
            # Upload file ke S3, misal di folder 'pengumuman_files'
            filename_db = save_file_to_s3(uploaded_file, folder_name='pengumuman')
        except Exception as e:
            flash(f'Gagal mengupload file ke S3: {e}', 'danger')
            return redirect(url_for('admin_pengumuman'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO pengumuman (judul, isi, file_lampiran, admin_id, created_at, updated_at) VALUES (%s,%s,%s,%s,NOW(),NOW())",
            (judul, isi, filename_db, admin_id))
        conn.commit()
    conn.close()
    flash('Pengumuman berhasil ditambah!', 'success')
    return redirect(url_for('admin_pengumuman'))


@app.route('/admin/pengumuman/edit/<int:id>', methods=['GET', 'POST'])
def admin_pengumuman_edit(id):
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        if request.method == 'POST':
            judul = request.form['judul']
            isi = request.form['isi']
            uploaded_file = request.files.get('file_lampiran')

            cursor.execute("SELECT file_lampiran FROM pengumuman WHERE pengumuman_id = %s", (id,))
            old_data = cursor.fetchone()

            filename_db = old_data['file_lampiran'] if old_data else None

            if uploaded_file and uploaded_file.filename != '':
                filename_secure = secure_filename(uploaded_file.filename)
                ext = os.path.splitext(filename_secure)[1]
                filename_unique = f"{uuid.uuid4().hex}{ext}"
                upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'pengumuman_files')
                os.makedirs(upload_folder, exist_ok=True)
                file_path = os.path.join(upload_folder, filename_unique)

                uploaded_file.save(file_path)
                filename_db = os.path.join('uploads', 'pengumuman_files', filename_unique)

                if old_data and old_data['file_lampiran']:
                    try:
                        old_file_path = os.path.join(app.root_path, 'static', old_data['file_lampiran'])
                        if os.path.exists(old_file_path):
                            os.remove(old_file_path)
                    except Exception as e:
                        print("Gagal hapus file lama:", e)

            cursor.execute(
                "UPDATE pengumuman SET judul=%s, isi=%s, file_lampiran=%s, updated_at=NOW() WHERE pengumuman_id=%s",
                (judul, isi, filename_db, id))
            conn.commit()
            flash('Pengumuman berhasil diedit!', 'success')
            return redirect(url_for('admin_pengumuman'))
        else:
            cursor.execute("SELECT * FROM pengumuman WHERE pengumuman_id=%s", (id,))
            data = cursor.fetchone()
            if not data:
                flash('Data pengumuman tidak ditemukan', 'danger')
                return redirect(url_for('admin_pengumuman'))

            cursor.execute("SELECT * FROM pengumuman ORDER BY created_at DESC")
            pengumuman = cursor.fetchall()

            return render_template('admin_pengumuman.html', pengumuman=pengumuman, action='edit', data=data)
    finally:
        cursor.close()
        conn.close()

@app.route('/download/pengumuman/<path:filename>')
def download_pengumuman(filename):
    return redirect(filename)



@app.route('/admin/pengumuman/hapus/<int:id>', methods=['POST'])
def admin_pengumuman_hapus(id):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Ambil URL file dari DB jika ada
            cursor.execute("SELECT file_url FROM pengumuman WHERE pengumuman_id=%s", (id,))
            data = cursor.fetchone()
            file_url = data['file_url'] if data else None

            # Hapus file dari S3
            if file_url:
                delete_file_from_s3(file_url)

            # Hapus data dari database
            cursor.execute("DELETE FROM pengumuman WHERE pengumuman_id=%s", (id,))
            conn.commit()

        flash('Pengumuman berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin_pengumuman'))

# Route untuk halaman admin pengaduan - --------------------------------------------------------------
# 📂 Read (List data pengaduan)
@app.route('/admin/pengaduan')
def admin_pengaduan():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    admin_id = session['admin_id']
    conn = get_db_connection()

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute('SELECT nama, foto_admin FROM admins WHERE admin_id = %s', (admin_id,))
            admin_data = cursor.fetchone()

            cursor.execute("SELECT * FROM pengaduan ORDER BY tanggal_kejadian DESC")
            pengaduan_data = cursor.fetchall()

            if not admin_data:
                flash('Admin tidak ditemukan. Silakan login ulang.', 'danger')
                return redirect(url_for('login'))

    finally:
        conn.close()

    subkategori_dict = {
        "Infrastruktur Desa": ["Jalan Rusak", "Jembatan Rusak", "Saluran Air / Drainase Tersumbat", "Penerangan Jalan Umum Mati", "Fasilitas Umum Rusak (Posyandu, Balai Desa)"],
        "Pelayanan Administrasi": ["Keterlambatan Pengurusan Surat", "Kesalahan Data Administrasi", "Informasi Pelayanan Tidak Jelas", "Penolakan Pengajuan Surat Tanpa Alasan"],
        "Pengelolaan Lingkungan": ["Sampah Menumpuk", "Pencemaran Lingkungan", "Pengelolaan Air Bersih", "Perizinan Limbah Rumah Tangga"],
        "Sosial dan Kemasyarakatan": ["Bantuan Sosial Tidak Tepat Sasaran", "Konflik Antar Warga", "Pengaduan Kekerasan atau KDRT", "Penyalahgunaan Dana Desa"],
        "Pertanian dan Perkebunan": ["Bantuan Pertanian Tidak Tepat", "Kerusakan Irigasi", "Hama Penyakit Tanaman", "Kelangkaan Bibit atau Pupuk"],
        "Keamanan dan Ketertiban": ["Gangguan Keamanan (Maling, Tawuran)", "Ketertiban Umum", "Penegakan Peraturan Desa", "Laporan Tindak Kriminal"],
        "Pendidikan dan Kesehatan": ["Fasilitas Pendidikan Tidak Memadai", "Bantuan Kesehatan Tidak Terlayani", "Pelayanan Posyandu Kurang Optimal", "Kurangnya Informasi Program Kesehatan"],
        "Lain-lain": ["Keluhan Umum yang Tidak Termasuk Kategori di Atas"]
    }

    kategori_list = list(subkategori_dict.keys())

    return render_template(
        "admin_pengaduan.html",
        pengaduan=pengaduan_data,
        kategori_list=kategori_list,
        subkategori_list=subkategori_dict[kategori_list[0]],
        subkategori_dict=subkategori_dict,
        admin=admin_data
    )

# ➕ Create (Tambah pengaduan)
@app.route('/admin/pengaduan/tambah', methods=['POST'])
def tambah_pengaduan():
    user_id = request.form['user_id']
    nama_pengadu = request.form['nama_pengadu']
    email_pengadu = request.form['email_pengadu']
    kategori = request.form['kategori']
    sub_kategori = request.form['sub_kategori']
    judul_pengaduan = request.form['judul_pengaduan']
    deskripsi = request.form['deskripsi']
    tanggal_kejadian = request.form['tanggal_kejadian']
    alamat = request.form['alamat']
    status = request.form['status']
    keterangan = request.form['keterangan']

    file = request.files.get('lampiran')
    filename = None
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        folder = os.path.join(app.root_path, 'static', 'uploads')
        os.makedirs(folder, exist_ok=True)
        file.save(os.path.join(folder, filename))

    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO pengaduan (user_id, nama_pengadu, email_pengadu, kategori, sub_kategori,
            judul_pengaduan, deskripsi, tanggal_kejadian, alamat, lampiran, status, keterangan, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, nama_pengadu, email_pengadu, kategori, sub_kategori,
              judul_pengaduan, deskripsi, tanggal_kejadian, alamat, filename, status, keterangan))
        conn.commit()
    conn.close()
    flash('Data pengaduan berhasil ditambahkan')
    return redirect(url_for('admin_pengaduan'))

# ✏️ Update
@app.route('/edit_pengaduan/<int:id>', methods=['POST'])
def edit_pengaduan(id):
    status = request.form['status']
    keterangan = request.form.get('keterangan', '')

    conn = get_db_connection()
    with conn.cursor() as cursor:
        sql = "UPDATE pengaduan SET status=%s, keterangan=%s WHERE pengaduan_id=%s"
        cursor.execute(sql, (status, keterangan, id))
        conn.commit()
    conn.close()

    flash('Data pengaduan berhasil diperbarui', 'success')
    return redirect(url_for('admin_pengaduan'))



# 🗑 Delete
@app.route('/admin/pengaduan/hapus/<int:id>')
def hapus_pengaduan(id):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Ambil file dari database (misalnya kolom bernama 'file_lampiran')
            cur.execute("SELECT file_lampiran FROM pengaduan WHERE pengaduan_id=%s", (id,))
            data = cur.fetchone()
            file_url = data['file_lampiran'] if data else None

            # Hapus file dari S3 jika ada
            if file_url:
                delete_file_from_s3(file_url)

            # Hapus data dari database
            cur.execute("DELETE FROM pengaduan WHERE pengaduan_id=%s", (id,))
            conn.commit()

        flash('Data pengaduan berhasil dihapus')
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin_pengaduan'))


# Route untuk halaman admin feedback ------------------------------------------------------------------------------------
@app.route('/admin/feedback', methods=['GET', 'POST'])
def admin_feedback():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    
    admin_id = session['admin_id']
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # Ambil data admin
    cursor.execute('SELECT nama, foto_admin FROM admins WHERE admin_id = %s', (admin_id,))
    admin_data = cursor.fetchone()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            cursor.execute("""
                INSERT INTO feedback (user_id, email, kategori, sub_kategori, penilaian, komentar, lampiran, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                request.form['user_id'], request.form['email'], request.form['kategori'],
                request.form['sub_kategori'], request.form['penilaian'], request.form['komentar'],
                request.form['lampiran']
            ))
            conn.commit()
            flash('Feedback berhasil ditambahkan.')

        elif action == 'edit':
            cursor.execute("""
                UPDATE feedback SET user_id=%s, email=%s, kategori=%s, sub_kategori=%s, penilaian=%s, komentar=%s, lampiran=%s
                WHERE feedback_id=%s
            """, (
                request.form['user_id'], request.form['email'], request.form['kategori'],
                request.form['sub_kategori'], request.form['penilaian'], request.form['komentar'],
                request.form['lampiran'], request.form['feedback_id']
            ))
            conn.commit()
            flash('Feedback berhasil diupdate.')

        cursor.close()
        conn.close()
        return redirect(url_for('admin_feedback'))

    # GET: ambil data feedback
    cursor.execute("SELECT * FROM feedback ORDER BY created_at DESC")
    feedbacks = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('admin_feedback.html', feedbacks=feedbacks, admin=admin_data)

# Menambah data feedback
@app.route('/admin/feedback/add', methods=['GET', 'POST'])
def add_feedback():
    if request.method == 'POST':
        user_id = request.form['user_id']
        email = request.form['email']
        kategori = request.form['kategori']
        sub_kategori = request.form['sub_kategori']
        penilaian = request.form['penilaian']
        komentar = request.form['komentar']
        lampiran = request.form['lampiran']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback (user_id, email, kategori, sub_kategori, penilaian, komentar, lampiran, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, email, kategori, sub_kategori, penilaian, komentar, lampiran))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Feedback berhasil ditambahkan.')
        return redirect(url_for('admin_feedback'))
    return render_template('add_feedback.html')

# Mengedit data feedback
@app.route('/admin/feedback/edit/<int:feedback_id>', methods=['GET', 'POST'])
def edit_feedback(feedback_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM feedback WHERE feedback_id = %s", (feedback_id,))
    feedback = cursor.fetchone()
    if request.method == 'POST':
        user_id = request.form['user_id']
        email = request.form['email']
        kategori = request.form['kategori']
        sub_kategori = request.form['sub_kategori']
        penilaian = request.form['penilaian']
        komentar = request.form['komentar']
        lampiran = request.form['lampiran']

        cursor.execute("""
            UPDATE feedback
            SET user_id=%s, email=%s, kategori=%s, sub_kategori=%s, penilaian=%s, komentar=%s, lampiran=%s
            WHERE feedback_id=%s
        """, (user_id, email, kategori, sub_kategori, penilaian, komentar, lampiran, feedback_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Feedback berhasil diupdate.')
        return redirect(url_for('admin_feedback'))
    cursor.close()
    conn.close()
    return render_template('edit_feedback.html', feedback=feedback)

# Menghapus data feedback
@app.route('/admin/feedback/delete/<int:feedback_id>', methods=['POST'])
def delete_feedback(feedback_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM feedback WHERE feedback_id = %s", (feedback_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Feedback berhasil dihapus.')
    return redirect(url_for('admin_feedback'))

@app.route('/download_attachment/<int:feedback_id>')
def download_attachment(feedback_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT lampiran FROM feedback WHERE feedback_id = %s", (feedback_id,))
            result = cursor.fetchone()
            if result and result['lampiran']:
                return redirect(result['lampiran'])  # langsung arahkan ke S3
            else:
                flash("Lampiran tidak ditemukan.", "warning")
                return redirect(url_for('admin_feedback'))  # sesuaikan rute
    finally:
        conn.close()
# Route untuk halaman admin legalisir -----------------------------------------------------------------------------------------------
# 📂 Read (List data legalisir)
@app.route('/admin/legalisir')
def admin_legalisir():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    admin_id = session['admin_id']
    conn = get_db_connection()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        # Ambil data admin
        cur.execute('SELECT nama, foto_admin FROM admins WHERE admin_id = %s', (admin_id,))
        admin_data = cur.fetchone()

        # Ambil data legalisir
        cur.execute("SELECT * FROM legalisir ORDER BY created_at DESC")
        legalisir_data = cur.fetchall() 
    from datetime import time, datetime

    # Proses data: konversi waktu dan siapkan URL file
    for item in legalisir_data:
        # Konversi jam_temu (jika berupa timedelta)
        if item.get('jam_temu') and hasattr(item['jam_temu'], 'total_seconds'):
            total_seconds = int(item['jam_temu'].total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            item['jam_temu'] = time(hour=hours, minute=minutes)

        # Konversi jadwal_temu dari string ke date jika perlu
        if item.get('jadwal_temu') and isinstance(item['jadwal_temu'], str):
            try:
                item['jadwal_temu'] = datetime.strptime(item['jadwal_temu'], '%Y-%m-%d').date()
            except ValueError:
                pass  # Jika gagal, biarkan apa adanya

        # Pastikan file_dokumen adalah link
        if item.get('file_dokumen') and item['file_dokumen'].startswith('http'):
            item['file_url'] = item['file_dokumen']
        else:
            item['file_url'] = None  # Atau tambahkan domain jika pakai relative path

    return render_template('admin_legalisir.html', legalisir=legalisir_data, admin=admin_data)



# ➕ Create (Tambah data legalisir)
@app.route('/admin/legalisir/tambah', methods=['POST'])
def tambah_legalisir():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    try:
        user_id = request.form['user_id']
        nama_dokumen = request.form['nama_dokumen']
        keperluan = request.form['keperluan']
        jadwal_temu = request.form['jadwal_temu']
        jam_temu = request.form['jam_temu']
        status = request.form['status']

        file = request.files.get('file_dokumen')
        filename = None

        # Validasi dan upload file
        if file and allowed_file(file.filename):
            file_url = save_file_to_s3(file, folder_name='legalisir')
        else:
            flash('File tidak valid atau tidak ada file diunggah. Format yang diizinkan: PDF, DOCX', 'error')
            return redirect(url_for('admin_legalisir'))


        # Insert data ke database
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO legalisir 
                (user_id, nama_dokumen, keperluan, jadwal_temu, jam_temu, file_dokumen, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, "pending", NOW(), NOW())
            """, (user_id, nama_dokumen, keperluan, jadwal_temu, jam_temu, file_url, status))
            conn.commit()
        conn.close()
        
        flash('Data legalisir berhasil ditambahkan!', 'success')
    
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
    
    return redirect(url_for('admin_legalisir'))


# ✏️ Update (Edit data legalisir)
@app.route('/admin/legalisir/edit/<int:id>', methods=['POST'])
def edit_legalisir(id):
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    try:
        user_id = request.form['user_id']
        nama_dokumen = request.form['nama_dokumen']
        keperluan = request.form['keperluan']
        jadwal_temu = request.form['jadwal_temu']
        jam_temu = request.form['jam_temu']
        status = request.form['status']

        # Ambil file lama (URL S3) dari form hidden input
        file_dokumen = request.form.get('file_lama', '')

        # Cek apakah ada file baru yang diupload
        file = request.files.get('file_dokumen')
        if file and file.filename and allowed_file(file.filename):
            # Upload file baru ke S3
            file_url = save_file_to_s3(file, folder_name='legalisir')
            file_dokumen = file_url  # ganti dengan URL S3 yang baru

            # Opsional: jika mau hapus file lama dari S3,
            # bisa tambahkan kode boto3 untuk hapus file lama berdasarkan URL
            # tapi jika tidak, bisa dilewatkan

        # Update data di database
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE legalisir 
                SET user_id=%s, nama_dokumen=%s, keperluan=%s, jadwal_temu=%s, 
                    jam_temu=%s, file_dokumen=%s, status=%s, updated_at=NOW()
                WHERE legalisir_id=%s
            """, (user_id, nama_dokumen, keperluan, jadwal_temu, jam_temu, file_dokumen, status, id))
            conn.commit()
        conn.close()

        flash('Data legalisir berhasil diupdate!', 'success')

    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')

    return redirect(url_for('admin_legalisir'))

@app.route('/admin/legalisir/hapus/<int:id>')
def hapus_legalisir(id):
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Ambil URL file dari database
            cur.execute("SELECT file_dokumen FROM legalisir WHERE legalisir_id=%s", (id,))
            data = cur.fetchone()
            file_url = data['file_dokumen'] if data else None

            # Hapus data dari database
            cur.execute("DELETE FROM legalisir WHERE legalisir_id=%s", (id,))
            conn.commit()

            # Hapus file dari S3 jika URL tersedia
            if file_url:
                delete_file_from_s3(file_url)

        conn.close()
        flash('Data legalisir berhasil dihapus!', 'success')

    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')

    return redirect(url_for('admin_legalisir'))

    
@app.route('/admin/legalisir/download/<int:id>')
def download_legalisir(id):
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("SELECT file_dokumen FROM legalisir WHERE legalisir_id = %s", (id,))
        data = cur.fetchone()
    conn.close()
    if data and data['file_dokumen']:
        return redirect(data['file_dokumen'])
    else:
        flash('File tidak ditemukan.', 'error')
        return redirect(url_for('admin_legalisir'))



# 🧾 Route untuk download file dokumen
@app.route('/admin/legalisir/download/<path:filename>')
def download_file(filename):
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    
    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        return send_from_directory(upload_folder, filename, as_attachment=True)
    except Exception as e:
        flash(f'File tidak ditemukan: {str(e)}', 'error')
        return redirect(url_for('admin_legalisir'))


# Helper function untuk validasi file
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Helper function untuk konversi timedelta ke string
def format_time_value(time_value):
    """Konversi timedelta atau datetime.time ke format HH:MM"""
    if time_value is None:
        return ''
    
    if hasattr(time_value, 'total_seconds'):
        # Ini adalah timedelta
        total_seconds = int(time_value.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    elif hasattr(time_value, 'strftime'):
        # Ini adalah datetime.time
        return time_value.strftime('%H:%M')
    else:
        # Fallback ke string
        return str(time_value)

# Route untuk halaman admin users------------------------------------------------------------------------------------------------------
# TAMPILKAN USERS
@app.route('/admin/users')
def admin_users():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    admin_id = session['admin_id']
    conn = get_db_connection()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        # Ambil data admin
        cur.execute('SELECT nama, foto_admin FROM admins WHERE admin_id = %s', (admin_id,))
        admin_data = cur.fetchone()

        # Ambil data users
        cur.execute("""
            SELECT user_id, email, password, nama_lengkap, nik, tempat_lahir, tanggal_lahir, jenis_kelamin,
                   alamat_jalan, rt_rw, desa, kecamatan, kabupaten, provinsi, agama, status_perkawinan,
                   pekerjaan, foto_profil, foto_ktp, foto_kk, status_akun
            FROM users
        """)
        users = cur.fetchall()

    conn.close()
    return render_template('admin_users.html', users=users, admin=admin_data)

# TAMBAH USER
@app.route('/admin/users/tambah', methods=['GET', 'POST'])
def tambah_user():
    if request.method == 'POST':
        data = request.form
        foto_profil = request.files.get('foto_profil')

        foto_profil_url = None
        if foto_profil and allowed_file(foto_profil.filename):
            try:
                # Simpan ke folder S3 -> profile/foto_profil
                foto_profil_url = save_file_to_s3(foto_profil, folder_name='profile/foto_profil')
            except Exception as e:
                flash(f'Gagal upload foto profil: {e}', 'danger')
                return redirect(request.url)

        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (
                    email, password, nama_lengkap, nik, tempat_lahir, tanggal_lahir,
                    jenis_kelamin, alamat_jalan, rt_rw, desa, kecamatan, kabupaten, provinsi,
                    agama, status_perkawinan, pekerjaan, foto_profil, foto_ktp, foto_kk, status_akun
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data['email'],
                data['password'],  # Pastikan hash password jika perlu!
                data['nama_lengkap'],
                data['nik'],
                data['tempat_lahir'],
                data['tanggal_lahir'],
                data['jenis_kelamin'],
                data['alamat_jalan'],
                data['rt_rw'],
                data['desa'],
                data['kecamatan'],
                data['kabupaten'],
                data['provinsi'],
                data['agama'],
                data['status_perkawinan'],
                data['pekerjaan'],
                foto_profil_url,   # URL dari S3
                data.get('foto_ktp'),  # Bisa dikembangkan seperti foto_profil
                data.get('foto_kk'),   # Bisa dikembangkan juga
                data['status_akun']
            ))
            conn.commit()
        conn.close()
        flash('User berhasil ditambahkan.', 'success')
        return redirect(url_for('admin_users'))

    return render_template('admin_users.html', u=None)



# EDIT USER
from werkzeug.security import generate_password_hash

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    conn = get_db_connection()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        if request.method == 'POST':
            data = request.form
            foto_profil = request.files.get('foto_profil')
            foto_ktp = request.files.get('foto_ktp')
            foto_kk = request.files.get('foto_kk')

            # Ambil password lama
            cur.execute("SELECT password, foto_profil, foto_ktp, foto_kk FROM users WHERE user_id = %s", (user_id,))
            user_lama = cur.fetchone()
            password_lama = user_lama['password'] if user_lama else ''
            old_foto_profil = user_lama['foto_profil'] if user_lama else None
            old_foto_ktp = user_lama['foto_ktp'] if user_lama else None
            old_foto_kk = user_lama['foto_kk'] if user_lama else None

            # Hash password baru jika diisi
            password_baru = data['password'].strip()
            password_to_save = generate_password_hash(password_baru) if password_baru else password_lama

            # Upload foto ke S3 atau pakai yang lama jika kosong
            filename_profil = save_file_to_s3(foto_profil, folder_name='profile/foto_profil') if foto_profil and allowed_file(foto_profil.filename) else old_foto_profil
            filename_ktp = save_file_to_s3(foto_ktp, folder_name='profile/foto_ktp') if foto_ktp and allowed_file(foto_ktp.filename) else old_foto_ktp
            filename_kk = save_file_to_s3(foto_kk, folder_name='profile/foto_kk') if foto_kk and allowed_file(foto_kk.filename) else old_foto_kk

            # Update database
            cur.execute("""
                UPDATE users SET
                email=%s, password=%s, nama_lengkap=%s, nik=%s, tempat_lahir=%s, tanggal_lahir=%s, jenis_kelamin=%s,
                alamat_jalan=%s, rt_rw=%s, desa=%s, kecamatan=%s, kabupaten=%s, provinsi=%s,
                agama=%s, status_perkawinan=%s, pekerjaan=%s,
                foto_profil=%s, foto_ktp=%s, foto_kk=%s, status_akun=%s
                WHERE user_id=%s
            """, (
                data['email'], password_to_save, data['nama_lengkap'], data['nik'],
                data['tempat_lahir'], data['tanggal_lahir'], data['jenis_kelamin'],
                data['alamat_jalan'], data['rt_rw'], data['desa'], data['kecamatan'],
                data['kabupaten'], data['provinsi'], data['agama'], data['status_perkawinan'],
                data['pekerjaan'], filename_profil, filename_ktp, filename_kk,
                data['status_akun'], user_id
            ))
            conn.commit()
            flash('User berhasil diperbarui.', 'success')
            return redirect(url_for('admin_users'))
        else:
            cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
            user = cur.fetchone()
    conn.close()
    return render_template('admin_users.html', u=user)

# HAPUS USER
@app.route('/admin/users/hapus/<int:user_id>')
def hapus_user(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Ambil URL file yang terkait
            cur.execute("SELECT foto_profil, foto_ktp, foto_kk FROM users WHERE user_id=%s", (user_id,))
            data = cur.fetchone()

            # Hapus file dari S3 jika ada
            if data:
                for file_url in [data.get('foto_profil'), data.get('foto_ktp'), data.get('foto_kk')]:
                    if file_url:
                        delete_file_from_s3(file_url)

            # Hapus user dari database
            cur.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
            conn.commit()

        flash('User berhasil dihapus.')
    except Exception as e:
        flash(f'Terjadi kesalahan saat menghapus user: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin_users'))


# Route untuk halaman admin profile-----------------------------------------------------------------------------------------------
@app.route('/admin_profile', methods=['GET', 'POST'])
def admin_profile():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    admin_id = session['admin_id']
    conn = get_db_connection()
    UPLOAD_FOLDER = 'static/uploads'

    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if request.method == 'POST':
                email = request.form.get('email')
                password = request.form.get('password')
                nama = request.form.get('nama')
                role = request.form.get('role')
                status = request.form.get('status') 

                def simpan_file(field):
                    file = request.files.get(field)
                    if file and file.filename:
                        filename = secure_filename(file.filename)
                        path = os.path.join(UPLOAD_FOLDER, filename)
                        file.save(path)
                        return filename
                    return None

                foto_admin = simpan_file('foto_admin')

                # Ambil data admin lama dari DB
                cursor.execute('SELECT * FROM admins WHERE admin_id = %s', (admin_id,))
                admin_lama = cursor.fetchone()

                # Jika foto_admin baru tidak ada, pakai foto lama
                foto_admin = foto_admin or admin_lama['foto_admin']

                # Jika password diisi, hash baru, jika kosong pakai password lama
                hashed_password = generate_password_hash(password) if password else admin_lama['password']

                # Jika status kosong, pakai status lama
                status = status or admin_lama.get('status_akun', admin_lama.get('status'))

                # Update data admin
                cursor.execute('''
                    UPDATE admins
                    SET email=%s, password=%s, nama=%s, role=%s, foto_admin=%s, status=%s
                    WHERE admin_id=%s
                ''', (email, hashed_password, nama, role, foto_admin, status, admin_id))

                conn.commit()
                flash('Profil berhasil diperbarui.', 'success')

            # Ambil data admin terbaru untuk ditampilkan
            cursor.execute('SELECT * FROM admins WHERE admin_id = %s', (admin_id,))
            admin = cursor.fetchone()

    finally:
        conn.close()

    return render_template('admin_profile.html', admin=admin)

# ------------------------------------------------------pengajuan surat
# 🌟 TAMPILKAN SEMUA PENGAJUAN SURAT
@app.route('/admin/pengajuan_surat')
def admin_pengajuan_surat():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    admin_id = session['admin_id']
    conn = get_db_connection()
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        # Ambil data admin
        cursor.execute('SELECT nama, foto_admin FROM admins WHERE admin_id = %s', (admin_id,))
        admin_data = cursor.fetchone()

        # Ambil data pengajuan surat beserta kategori dan jenis
        cursor.execute("""
            SELECT 
                p.*, 
                k.nama_kategori, 
                j.nama_jenis
            FROM pengajuan_surat p
            LEFT JOIN kategori_surat k ON p.kategori_id = k.kategori_id
            LEFT JOIN jenis_surat j ON p.jenis_surat_id = j.jenis_surat_id
        """)
        pengajuan_list = cursor.fetchall()

    conn.close()
    return render_template('admin_pengajuan_surat.html', pengajuan_list=pengajuan_list, admin=admin_data)

@app.route('/admin/pengajuan_surat/tambah', methods=['GET', 'POST'])
def tambah_pengajuan_surat():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()

        data = (
            request.form['user_id'],
            request.form['kategori_id'],
            request.form['jenis_surat_id'],
            request.form['nama_pemohon'],
            request.form['nik_pemohon'],
            request.form['tempat_lahir'],
            request.form['tanggal_lahir'],
            request.form['alamat_lengkap'],
            request.form['jenis_kelamin'],
            request.form['agama'],
            request.form['status_perkawinan'],
            request.form['kewarganegaraan'],
            request.form['no_kk'],
            request.form['pekerjaan'],
            request.form['instansi'],
            request.form['keperluan'],
            'proses'
        )
        query = """
        INSERT INTO pengajuan_surat (
            user_id, kategori_id, jenis_surat_id, nama_pemohon, nik_pemohon, tempat_lahir, tanggal_lahir, alamat_lengkap,
            jenis_kelamin, agama, status_perkawinan, kewarganegaraan, no_kk, pekerjaan, instansi, keperluan, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, data)
        conn.commit()
        cursor.close()
        conn.close()
        flash('Pengajuan surat berhasil ditambahkan.', 'success')
        return redirect(url_for('admin_pengajuan_surat'))

    return render_template(
    'admin_pengajuan_surat.html',
    pengajuan_edit=None
)



#  EDIT PENGAJUAN SURAT
@app.route('/admin/pengajuan_surat/edit/<int:pengajuan_id>', methods=['GET', 'POST'])
def edit_pengajuan_surat(pengajuan_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        data = (
            request.form['user_id'],
            request.form['kategori_id'],
            request.form['jenis_surat_id'],
            request.form['nama_pemohon'],
            request.form['nik_pemohon'],
            request.form['tempat_lahir'],
            request.form['tanggal_lahir'],
            request.form['alamat_lengkap'],
            request.form['jenis_kelamin'],
            request.form['agama'],
            request.form['status_perkawinan'],
            request.form['kewarganegaraan'],
            request.form['no_kk'],
            request.form['pekerjaan'],
            request.form['instansi'],
            request.form['keperluan'],
            request.form['status'],
            pengajuan_id
        )
        query = """
        UPDATE pengajuan_surat SET
            user_id=%s, kategori_id=%s, jenis_surat_id=%s, nama_pemohon=%s, nik_pemohon=%s, tempat_lahir=%s, tanggal_lahir=%s, alamat_lengkap=%s,
            jenis_kelamin=%s, agama=%s, status_perkawinan=%s, kewarganegaraan=%s, no_kk=%s, pekerjaan=%s, instansi=%s, keperluan=%s, status=%s, updated_at=NOW()
        WHERE pengajuan_id=%s
        """
        cursor.execute(query, data)
        conn.commit()
        cursor.close()
        conn.close()
        flash('Pengajuan surat berhasil diperbarui.')
        return redirect(url_for('admin_pengajuan_surat'))

    # Ambil data pengajuan yang akan diedit
    cursor.execute("SELECT * FROM pengajuan_surat WHERE pengajuan_id=%s", (pengajuan_id,))
    pengajuan = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('admin_pengajuan_surat.html', pengajuan=pengajuan)

# 🌟 HAPUS PENGAJUAN SURAT
@app.route('/admin/pengajuan_surat/hapus/<int:pengajuan_id>', methods=['POST'])
def hapus_pengajuan_surat(pengajuan_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Ambil file dokumen (jika ada)
        cursor.execute("SELECT file_dokumen FROM pengajuan_surat WHERE pengajuan_id=%s", (pengajuan_id,))
        data = cursor.fetchone()

        # Hapus dari S3 jika file ada
        if data and data['file_dokumen']:
            delete_file_from_s3(data['file_dokumen'])

        # Hapus dari database
        cursor.execute("DELETE FROM pengajuan_surat WHERE pengajuan_id=%s", (pengajuan_id,))
        conn.commit()
        flash('Pengajuan surat berhasil dihapus.')
    except Exception as e:
        flash(f'Terjadi kesalahan saat menghapus pengajuan surat: {str(e)}', 'error')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_pengajuan_surat'))



#if __name__ == '__main__':
#    app.run(debug=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
