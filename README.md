# 🔀 USDT Hop Bot

> **Bilingual / دو زبانه** — [English](#english) | [فارسی](#فارسی)

---

## 🚀 Try It Without Running Your Own Bot

**Don't want to host it yourself?** The bot is live and ready to use under **[@IraniExchange](https://t.me/IraniExchange)** on Telegram!

> 🔗 **[t.me/IraniExchange](https://t.me/IraniExchange)**

Just open the link, press Start, and follow the instructions — no setup required.

---

<a name="english"></a>
## 🇬🇧 English

A Telegram bot that routes USDT through multiple intermediate wallets on the **BSC (BNB Smart Chain)** network using **PancakeSwap V3** swaps (USDT ↔ DAI), making the transaction trail harder to follow.

### ✨ Features

- 🔁 **Multi-hop routing** — 2–10 configurable hops per cycle
- 🔄 **USDT ↔ DAI swap mixing** — each hop converts between USDT and DAI via PancakeSwap V3, breaking the token trail
- 🗝️ **HD wallet generation** — fresh 24-word BIP44 wallets per cycle; private keys sent to user at start
- ⏱️ **Expiry timer** — configurable 30 min–8 hr deposit window with inline extend (+1 hr) button
- ♻️ **Cycle recovery** — active cycles auto-resume on bot restart
- 👥 **Multi-user** — any Telegram user can start cycles; master wallet is admin-controlled
- 👮 **Multi-admin** — comma-separated `ADMIN_IDS` in `.env`
- 🔒 **Encrypted key storage** — intermediate wallet private keys encrypted with Fernet before saving to MongoDB
- 🌐 **Bilingual UI** — Persian (default) and English, toggle per user
- 🛠️ **Admin panel** — view all/active/failed cycles, cancel cycles, set master wallet

---

### 🧰 Tech Stack

| Component | Version |
|-----------|---------|
| 🐍 Python | 3.10+ |
| 🤖 aiogram | 3.28.2 |
| 🌐 web3 | 7.16.0 |
| 🗄️ motor (MongoDB async) | 3.7.1 |
| 🔑 py_crypto_hd_wallet | 1.3.3 |
| 🔐 cryptography (Fernet) | 48.0.0 |
| 🍃 MongoDB | 7.0 |

---

### 💸 Fee Structure

`0.5 USDT × number of hops` is collected as service fee at the final hop. Cycles with deposits ≤ total fee are rejected before any gas is spent.

---

### ⚡ Quick Install (Automated — Ubuntu/Debian)

```bash
# 1. Clone the repository
git clone https://github.com/AghaFarokh/UsdtHopBot.git
cd UsdtHopBot

# 2. Run the installer as root
sudo bash install.sh
```

The script will automatically:
- ✅ Install Python 3 and MongoDB 7.0
- ✅ Create a Python virtual environment
- ✅ Install all dependencies
- ✅ Generate a Fernet encryption key
- ✅ Prompt you for your Telegram bot token and admin ID(s)
- ✅ Create `/root/iraniexchange/.env`
- ✅ Create and enable a `systemd` service that starts on boot

---

### 🔧 Manual Installation

#### 📋 Prerequisites

- Ubuntu 20.04+ or Debian 11+ (amd64/arm64)
- Python 3.10 or newer
- MongoDB 7.0
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your Telegram user ID (get it from [@userinfobot](https://t.me/userinfobot))

#### Step 1 — Install MongoDB

```bash
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc \
    | sudo gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg

echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] \
https://repo.mongodb.org/apt/ubuntu $(lsb_release -cs)/mongodb-org/7.0 multiverse" \
    | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

sudo apt-get update
sudo apt-get install -y mongodb-org
sudo systemctl enable mongod --now
```

#### Step 2 — Set Up Project

```bash
# Create directory and copy files
sudo mkdir -p /root/iraniexchange
sudo cp main.py lang.py requirements.txt /root/iraniexchange/
cd /root/iraniexchange

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 3 — Generate Encryption Key

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> 📋 Copy the output — you'll need it in the next step.

#### Step 4 — Create `.env`

```bash
nano /root/iraniexchange/.env
```

Paste and fill in:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
MONGO_URI=mongodb://localhost:27017
ENCRYPTION_KEY=paste_generated_key_here
ADMIN_IDS=123456789,987654321
```

Secure the file:

```bash
chmod 600 /root/iraniexchange/.env
```

#### Step 5 — Create Systemd Service

```bash
sudo nano /etc/systemd/system/iraniexchange.service
```

Paste:

```ini
[Unit]
Description=USDT Hop Bot
After=network.target mongod.service
Requires=mongod.service

[Service]
Type=simple
WorkingDirectory=/root/iraniexchange
ExecStart=/root/iraniexchange/venv/bin/python /root/iraniexchange/main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

#### Step 6 — Start the Bot

```bash
sudo systemctl daemon-reload
sudo systemctl enable iraniexchange
sudo systemctl start iraniexchange

# ✅ Check it's running
sudo systemctl status iraniexchange

# 📜 Live logs
sudo journalctl -u iraniexchange -f
```

#### Step 7 — Set Master Wallet (in Telegram)

1. Start a chat with your bot and press **🔑 Admin Panel**
2. Tap **⚙️ Set Master Wallet**
3. Send the BSC wallet address that will receive fees and provide gas
4. Send its private key

> ⚠️ **Important:** The master wallet must hold enough BNB to fund gas for each hop.

---

### 🛡️ Admin Commands

| Command | Description |
|---------|-------------|
| `/start` | Open main panel |
| `/cycles` | List all cycles |
| `/cycles active` | List active cycles |
| `/cycle <id>` | View cycle details + hop keys |
| `/cancelcycle <id>` | Force-cancel a cycle |
| `/setupmaster <address> <key>` | Set master wallet via command |

---

### 🔐 Security Notes

- 🔒 Hop wallet private keys are encrypted with Fernet before being stored in MongoDB
- 🙈 The `.env` file and `temp_key.pem` are excluded from version control via `.gitignore`
- ⛔ **Never share your `.env`, bot token, or master wallet private key**
- 🔄 Each cycle generates completely fresh wallets that are used once and discarded

---

<a name="فارسی"></a>
## 🇮🇷 فارسی

<div dir="rtl">

### 🚀 بدون نیاز به راه‌اندازی — همین الان استفاده کن!

**نمی‌خوای سرور خودت رو راه بیندازی؟** ربات به صورت زنده و آماده زیر آیدی **[@IraniExchange](https://t.me/IraniExchange)** در دسترسه!

> 🔗 **[t.me/IraniExchange](https://t.me/IraniExchange)**

فقط لینک رو باز کن، Start بزن و دستورالعمل‌ها رو دنبال کن — هیچ نصبی لازم نیست.

---

ربات تلگرامی که USDT را از طریق چندین کیف پول میانی در شبکه **BSC (BNB Smart Chain)** منتقل می‌کند. در این مسیر از سوآپ **PancakeSwap V3** بین USDT و DAI استفاده می‌شود تا ردیابی تراکنش‌ها سخت‌تر شود.

### ✨ امکانات

- 🔁 **چرخه چند‌مرحله‌ای** — ۲ تا ۱۰ چرخه قابل تنظیم
- 🔄 **سوآپ USDT ↔ DAI** — هر چرخه توکن را تبدیل می‌کند تا ردیابی شکسته شود
- 🗝️ **تولید کیف پول HD** — کیف پول‌های ۲۴ کلمه‌ای BIP44 برای هر چرخه جداگانه ساخته می‌شود
- ⏱️ **تایمر انقضا** — پنجره واریز ۳۰ دقیقه تا ۸ ساعت با دکمه تمدید (+۱ ساعت)
- ♻️ **بازیابی خودکار** — چرخه‌های فعال پس از ری‌استارت ربات ادامه می‌یابند
- 👥 **چند کاربره** — هر کاربر تلگرام می‌تواند چرخه شروع کند
- 👮 **چند ادمین** — با تنظیم `ADMIN_IDS` در فایل `.env`
- 🔒 **ذخیره‌سازی رمزنگاری‌شده** — کلیدهای خصوصی با Fernet رمزنگاری می‌شوند
- 🌐 **رابط دو زبانه** — فارسی (پیش‌فرض) و انگلیسی، قابل تغییر برای هر کاربر
- 🛠️ **پنل ادمین** — مشاهده و مدیریت چرخه‌ها، تنظیم کیف پول اصلی

---

### ⚡ نصب سریع (خودکار — اوبونتو/دبیان)

```bash
# ۱. کلون مخزن
git clone https://github.com/AghaFarokh/UsdtHopBot.git
cd UsdtHopBot

# ۲. اجرای اسکریپت نصب به عنوان root
sudo bash install.sh
```

اسکریپت به صورت خودکار:
- ✅ Python 3 و MongoDB 7.0 نصب می‌کند
- ✅ محیط مجازی Python می‌سازد
- ✅ تمام وابستگی‌ها را نصب می‌کند
- ✅ کلید رمزنگاری Fernet تولید می‌کند
- ✅ توکن ربات و شناسه ادمین را از شما می‌خواهد
- ✅ فایل `.env` می‌سازد
- ✅ سرویس `systemd` ایجاد و فعال می‌کند

---

### 🔧 نصب دستی

#### 📋 پیش‌نیازها

- اوبونتو ۲۰.۰۴+ یا دبیان ۱۱+
- Python 3.10 یا بالاتر
- MongoDB 7.0
- توکن ربات از [@BotFather](https://t.me/BotFather)
- شناسه تلگرامی شما (از [@userinfobot](https://t.me/userinfobot) دریافت کنید)

#### مرحله ۱ — نصب MongoDB

```bash
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc \
    | sudo gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg

echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] \
https://repo.mongodb.org/apt/ubuntu $(lsb_release -cs)/mongodb-org/7.0 multiverse" \
    | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

sudo apt-get update
sudo apt-get install -y mongodb-org
sudo systemctl enable mongod --now
```

#### مرحله ۲ — آماده‌سازی پروژه

```bash
sudo mkdir -p /root/iraniexchange
sudo cp main.py lang.py requirements.txt /root/iraniexchange/
cd /root/iraniexchange

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

#### مرحله ۳ — تولید کلید رمزنگاری

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> 📋 خروجی را کپی کنید.

#### مرحله ۴ — ساخت فایل `.env`

```bash
nano /root/iraniexchange/.env
```

محتوا را وارد کنید:

```env
TELEGRAM_BOT_TOKEN=توکن_ربات_شما
MONGO_URI=mongodb://localhost:27017
ENCRYPTION_KEY=کلید_رمزنگاری_تولید_شده
ADMIN_IDS=123456789,987654321
```

```bash
chmod 600 /root/iraniexchange/.env
```

#### مرحله ۵ — ساخت سرویس Systemd

```bash
sudo nano /etc/systemd/system/iraniexchange.service
```

محتوا:

```ini
[Unit]
Description=USDT Hop Bot
After=network.target mongod.service
Requires=mongod.service

[Service]
Type=simple
WorkingDirectory=/root/iraniexchange
ExecStart=/root/iraniexchange/venv/bin/python /root/iraniexchange/main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

#### مرحله ۶ — راه‌اندازی ربات

```bash
sudo systemctl daemon-reload
sudo systemctl enable iraniexchange
sudo systemctl start iraniexchange

# ✅ بررسی وضعیت
sudo systemctl status iraniexchange

# 📜 مشاهده لاگ زنده
sudo journalctl -u iraniexchange -f
```

#### مرحله ۷ — تنظیم کیف پول اصلی در تلگرام

۱. با ربات چت را شروع کنید و **🔑 پنل مدیر** را بزنید
۲. روی **⚙️ Set Master Wallet** کلیک کنید
۳. آدرس BSC کیف پول اصلی را ارسال کنید
۴. کلید خصوصی آن را ارسال کنید

> ⚠️ **مهم:** کیف پول اصلی باید BNB کافی برای تأمین گس هر چرخه داشته باشد.

---

### 🛡️ دستورات ادمین

| دستور | توضیح |
|-------|-------|
| `/start` | باز کردن پنل اصلی |
| `/cycles` | مشاهده همه چرخه‌ها |
| `/cycles active` | چرخه‌های فعال |
| `/cycle <id>` | جزئیات چرخه + کلیدهای هاپ |
| `/cancelcycle <id>` | لغو اجباری چرخه |
| `/setupmaster <address> <key>` | تنظیم کیف پول اصلی با دستور |

---

### 🔐 نکات امنیتی

- 🔒 کلیدهای خصوصی کیف پول‌های میانی قبل از ذخیره در MongoDB با Fernet رمزنگاری می‌شوند
- 🙈 فایل `.env` و فایل‌های `*.pem` از طریق `.gitignore` از مخزن خارج هستند
- ⛔ **هرگز فایل `.env`، توکن ربات یا کلید خصوصی کیف پول اصلی را با کسی به اشتراک نگذارید**
- 🔄 هر چرخه کیف پول‌های کاملاً جدیدی تولید می‌کند که فقط یک‌بار استفاده می‌شوند

</div>
